import json
import logging
import os
import re
import shutil

import cmd
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
    # When a heredoc string value changes, Terraform renders its body as a
    # line-by-line diff with a fixed 2-character gutter: changed lines carry a
    # +/- marker there, unchanged lines two spaces, and the value content always
    # begins two columns to the right of the gutter. We need that gutter column
    # so we can tell a real removal (`-` in the gutter) from a YAML list item
    # (`- x` at the content column or deeper). Returns the gutter column, or None
    # when the body carries no diff (so it should be emitted verbatim).
    #
    # A `+` only ever appears as a gutter marker -- YAML content never starts a
    # line with `+` -- so its column is the gutter directly, and this also
    # handles a body whose YAML root is a bare list (where every other line
    # starts with `-` and there is no plain content line to measure from).
    plus_indents = [
        _leading_spaces(line)
        for line in body
        if line.strip() and line.lstrip(' ')[0] == '+'
    ]
    if plus_indents:
        return min(plus_indents)
    # No additions: fall back to the content baseline -- the shallowest line that
    # is not itself a marker -- less the 2-char gutter width, and only when some
    # marker actually sits in that gutter (otherwise the body is unchanged).
    content_indents = [
        _leading_spaces(line)
        for line in body
        if line.strip() and line.lstrip(' ')[0] not in '+-~'
    ]
    if not content_indents:
        return None
    gutter = min(content_indents) - 2
    if gutter < 0:
        return None
    has_marker = any(
        line.strip() and line.lstrip(' ')[0] in '-~' and _leading_spaces(line) == gutter
        for line in body
    )
    return gutter if has_marker else None


def _format_heredoc_body(body):
    # Only promote markers that sit in Terraform's diff gutter; leave the YAML
    # content (including its `- ` list items) untouched.
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
        out.append(_format_diff_line(line))
        delim = m.group(1)
        i += 1
        # Collect the body up to (but not including) the closing delimiter line.
        body = []
        while i < len(lines) and lines[i].strip() != delim:
            body.append(lines[i])
            i += 1
        out.extend(_format_heredoc_body(body))
        # Emit the closing delimiter line verbatim, if present.
        if i < len(lines):
            out.append(lines[i])
            i += 1
    return '\n'.join(out)


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
                    ] + config.get('extra_args', [])
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
                    'cmd': [self.tf_cmd, 'workspace', 'select', state.workspace]
                })

            if proc.returncode != 0:
                (proc, new_stdout, new_stderr) = cmd.run_with_output(
                    state,
                    {
                        'cmd': [self.tf_cmd, 'workspace', 'new', state.workspace]
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
