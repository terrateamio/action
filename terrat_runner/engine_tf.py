import json
import logging
import os
import re
import shutil

import cmd
import plugin_cache
import repo_config
import retry

TRIES = 3
INITIAL_SLEEP = 1
BACKOFF = 1.5


# Opens a Terraform heredoc string value, e.g. `foo = <<-EOT` or `foo =
# <<EOT`, capturing the delimiter so we can find the matching closing line.
# The delimiter is an arbitrary HCL identifier (EOT is just conventional).
_HEREDOC_OPEN = re.compile(r'<<-?"?([A-Za-z_][A-Za-z0-9_]*)')


def _leading_spaces(line):
    return len(line) - len(line.lstrip(' '))


def _format_diff_line(line):
    # Promote a leading +/-/~ marker (with its indentation) to column 0 so the
    # `diff` syntax highlighter colours the line, then turn a leading ~ (a
    # change) into !.
    line = re.sub(r'^(\s+)([+\-~])', r'\2\1', line)
    line = re.sub(r'^~', r'!', line)
    return line


def _heredoc_gutter(body):
    # When a heredoc string value changes, Terraform renders the whole body as a
    # line-by-line diff by prepending a gutter to every line: a +/-/~ marker for
    # changed lines, spaces for unchanged ones, followed by the original content.
    # Because the gutter comes *before* the content's own indentation, the marker
    # column is always strictly to the LEFT of every content line -- including a
    # YAML list item (`- x`), whose dash is part of the content and so lands at
    # the gutter column + 2 or deeper. So the gutter is simply the shallowest
    # indent in the body, and only genuine markers ever sit there.
    #
    # Returns the gutter column, or None when the body carries no diff (so it
    # should be emitted verbatim). Because the gutter is prepended to every line,
    # in a genuinely changed body no content line can sit at the shallowest
    # column -- that column belongs to the gutter. So the body is "changed" only
    # when the shallowest column holds a marker and holds NO bare content line;
    # if a content line (e.g. a map key, or a top-level YAML list item in an
    # unchanged value) sits at the shallowest column, there is no room for a
    # gutter to its left and the heredoc is shown unchanged.
    indents = [_leading_spaces(line) for line in body if line.strip()]
    if not indents:
        return None
    gutter = min(indents)
    marker_at_gutter = False
    content_at_gutter = False
    for line in body:
        if not line.strip() or _leading_spaces(line) != gutter:
            continue
        if line.lstrip(' ')[0] in '+-~':
            marker_at_gutter = True
        else:
            content_at_gutter = True
    return gutter if marker_at_gutter and not content_at_gutter else None


def _format_heredoc_body(body):
    # Only promote markers that sit in Terraform's diff gutter; leave the YAML
    # content (including its `- ` list items, which sit to the right of the
    # gutter) untouched.
    gutter = _heredoc_gutter(body)
    if gutter is None:
        return body
    out = []
    for line in body:
        stripped = line.lstrip(' ')
        if stripped and stripped[0] in '+-~' and _leading_spaces(line) == gutter:
            out.append(_format_diff_line(line))
        else:
            out.append(line)
    return out


def format_diff(text):
    # A heredoc body is an opaque string value (often YAML, whose `- ` list
    # items look exactly like removal markers), so it cannot be run through the
    # blanket marker promotion. Outside a heredoc every line is a real diff
    # line; inside one only the gutter markers are (see _format_heredoc_body).
    lines = text.split('\n')
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _HEREDOC_OPEN.search(line)
        if m is None:
            out.append(_format_diff_line(line))
            i += 1
            continue
        # The opening line itself (e.g. `~ values = <<-EOT`) is a real diff line.
        opener_marker = line.lstrip(' ')[0] if line.strip() else ' '
        out.append(_format_diff_line(line))
        delim = m.group(1)
        i += 1
        # Collect the body up to (but not including) the closing delimiter line.
        body = []
        while i < len(lines) and lines[i].strip() != delim:
            body.append(lines[i])
            i += 1
        # When the whole value is added or removed (`+`/`-` opener) the body is
        # emitted verbatim -- Terraform does not diff inside it, so its YAML
        # content carries no gutter and must not be touched. Only an in-place
        # change (`~` opener) renders the body as a line-by-line diff.
        if opener_marker in '+-':
            out.extend(body)
        else:
            out.extend(_format_heredoc_body(body))
        # Emit the closing delimiter line verbatim, if present.
        if i < len(lines):
            out.append(lines[i])
            i += 1
    return '\n'.join(out)


def _resource_summary_from_plan_json(plan_json):
    """Count per-resource changes from a `terraform show -json` plan.

    A replacement (['create', 'delete'] or ['delete', 'create']) counts in the
    'replaced' bucket only -- the four buckets are disjoint, unlike tofu's
    aggregate 'Plan: N to add, ...' line where a replacement counts in both
    add and destroy.  A plan with no resource changes (for example an
    output-only change) yields all zeros, which is a real result, not an
    absence of one.
    """
    summary = {'created': 0, 'updated': 0, 'deleted': 0, 'replaced': 0}
    if not isinstance(plan_json, dict):
        return None
    for resource_change in plan_json.get('resource_changes') or []:
        actions = (resource_change.get('change') or {}).get('actions') or []
        if actions == ['create']:
            summary['created'] += 1
        elif actions == ['update']:
            summary['updated'] += 1
        elif actions == ['delete']:
            summary['deleted'] += 1
        elif sorted(actions) == ['create', 'delete']:
            summary['replaced'] += 1
        # 'no-op', 'read', and anything unrecognized are not changes and are
        # ignored rather than guessed.
    return summary


class Engine:
    def __init__(self, name, override_tf_cmd, **options):
        self.name = name
        self.tf_cmd = override_tf_cmd

        # Outputs can sometimes be set to None, so we get it with a default and
        # if its None then set it to the default
        outputs = options.get('outputs', {})
        if outputs is None:
            outputs = {}
        self.__outputs = outputs

    def workspace_cmd(self, state, *args):
        return [self.tf_cmd, 'workspace'] + list(args)

    def init(self, state, config, create_and_select_workspace=None):
        # If there is already a .terraform dir, delete it
        terraform_path = os.path.join(state.working_dir, '.terraform')
        if os.path.exists(terraform_path):
            shutil.rmtree(terraform_path)

        (proc, stdout, stderr) = retry.run(
            lambda: cmd.run_with_output(
                state,
                {
                    'cmd': [
                        'flock',
                        '/tmp/tf-init.lock',
                        self.tf_cmd,
                        'init'
                    ] + config.get('extra_args', []),
                    # Set immediately before the init, and only for the init:
                    # the plugin cache is consulted when providers are
                    # installed and nowhere else.  The flock above is what
                    # keeps two dirspaces from installing into the cache at
                    # the same moment.
                    'env': plugin_cache.init_env(state.env)
                }),
            retry.finite_tries(TRIES, lambda result: result[0].returncode == 0),
            retry.betwixt_sleep_with_backoff(INITIAL_SLEEP, BACKOFF))

        if proc.returncode != 0:
            return (False, stdout, stderr)

        if create_and_select_workspace is None:
            create_and_select_workspace = repo_config.get_create_and_select_workspace(
                state.repo_config,
                state.path)

        logging.info(
            ('INIT : '
             'CREATE_AND_SELECT_WORKSPACE : %s : '
             'engine=%s : create_and_select_workspace=%r'),
            state.path,
            state.workflow['engine']['name'],
            create_and_select_workspace)

        if create_and_select_workspace:
            (proc, select_stdout, select_stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.workspace_cmd(state, 'select', state.workspace)
                })

            if proc.returncode != 0:
                (proc, new_stdout, new_stderr) = cmd.run_with_output(
                    state,
                    {
                        'cmd': self.workspace_cmd(state, 'new', state.workspace)
                    })

                if proc.returncode != 0:
                    return (False,
                            '\n'.join([select_stdout, new_stdout]),
                            '\n'.join([select_stderr, new_stderr]))

        return (proc.returncode == 0, stdout, stderr)

    def apply(self, state, config):
        logging.info(
            'APPLY : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [self.tf_cmd, 'apply'
                        ] + config.get('extra_args', []) + ['${TERRATEAM_PLAN_FILE}']
            })

        return (proc.returncode == 0, stdout, stderr)

    def apply_without_plan(self, state, config):
        logging.info(
            'APPLY_WITHOUT_PLAN : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [self.tf_cmd, 'apply', '-auto-approve'
                        ] + config.get('extra_args', [])
            })

        return (proc.returncode == 0, stdout, stderr)

    def diff(self, state, config):
        logging.info(
            'DIFF : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [self.tf_cmd, 'show', '${TERRATEAM_PLAN_FILE}']
            })

        if proc.returncode == 0:
            stdout = format_diff(stdout)

        return (proc.returncode == 0, stdout, stderr)


    def diff_json(self, state, config):
        logging.info(
            'DIFF_JSON : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [self.tf_cmd, 'show', '-json', '${TERRATEAM_PLAN_FILE}']
            })

        if proc.returncode == 0:
            try:
                return (True, json.loads(stdout))
            except json.JSONDecodeError as exn:
                return (False, stdout, str(exn))

        return (False, stdout, stderr)


    def resource_summary(self, state, config):
        logging.info(
            'RESOURCE_SUMMARY : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        res = self.diff_json(state, config)
        if not res:
            return None

        # diff_json returns (True, plan_json) on success and a 3-tuple
        # (False, stdout, stderr) on failure.
        (success, plan_json) = res if len(res) == 2 else (False, None)
        if not success:
            return None

        return _resource_summary_from_plan_json(plan_json)


    def plan(self, state, config):
        logging.info(
            'PLAN : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        if config.get('mode') == 'fast-and-loose':
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': [self.tf_cmd, 'plan', '-detailed-exitcode', '-json', '-refresh=false'
                            ] + config.get('extra_args', [])
                })

            targets = []

            if proc.returncode in [0, 2]:
                for line in stdout.splitlines():
                    line = json.loads(line)
                    if line.get('type') in ['planned_change', 'resource_drift']:
                        targets.append(line['change']['resource']['addr'])
            else:
                return (False, False, stdout, stderr)
        else:
            targets = []

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [
                    self.tf_cmd,
                    'plan',
                    '-detailed-exitcode',
                    '-out',
                    '${TERRATEAM_PLAN_FILE}'
                ] + targets + config.get('extra_args', [])
            })

        return (proc.returncode in [0, 2], proc.returncode == 2, stdout, stderr)

    def unsafe_apply(self, state, config):
        logging.info(
            'UNSAFE_APPLY : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [self.tf_cmd, 'apply', '-auto-approve'
                        ] + config.get('extra_args', []) + ['${TERRATEAM_PLAN_FILE}']
            })

        return (proc.returncode == 0, stdout, stderr)

    def outputs(self, state, config):
        if self.__outputs.get('collect', True):
            logging.info(
                'OUTPUTS : %s : engine=%s',
                state.path,
                state.workflow['engine']['name'])

            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': [self.tf_cmd, 'output', '-json']
                })

            return (proc.returncode == 0, stdout, stderr)
        else:
            logging.info(
                'OUTPUTS : %s : DISABLED',
                state.path)
            return None


def make(**options):
    options['name'] = 'tf'
    return Engine(**options)
