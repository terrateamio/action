import json
import logging
import os
import re
import shutil
import tempfile

import cmd
import repo_config
import retry

TRIES = 3
INITIAL_SLEEP = 1
BACKOFF = 1.5


def format_diff(text):
    s = re.sub(r'^(\s+)([+\-~])', r'\2\1', text)
    if s and s[0] == '~':
        return '!' + s[1:]
    else:
        return s


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
                    ] + config.get('extra_args', []),
                    'tee': config['tee'],
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
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': [self.tf_cmd, 'workspace', 'select', state.workspace],
                    'tee': config['tee'],
                    'tee_append': True
                })

            if proc.returncode != 0:
                (proc, stdout, stderr) = cmd.run_with_output(
                    state,
                    {
                        'cmd': [self.tf_cmd, 'workspace', 'new', state.workspace],
                        'tee': config['tee'],
                        'tee_append': True
                    })

                if proc.returncode != 0:
                    return (False, stdout, stderr)

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
                        ] + config.get('extra_args', []) + ['${TERRATEAM_PLAN_FILE}'],
                'tee': config['tee']
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
                'cmd': [self.tf_cmd, 'show', '${TERRATEAM_PLAN_FILE}'],
                'tee': config['tee']
            })

        if proc.returncode == 0:
            with tempfile.NamedTemporaryFile(dir=os.path.dirname(stdout), delete=False) as fout:
                with open(stdout, 'r') as fin:
                    for l in fin:
                        fout.write(format_diff(l).encode('utf-8'))

                os.rename(fout.name, stdout)

        return (proc.returncode == 0, stdout, stderr)


    def diff_json(self, state, config):
        logging.info(
            'DIFF_JSON : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [self.tf_cmd, 'show', '-json', '${TERRATEAM_PLAN_FILE}'],
                'tee': config['tee']
            })

        if proc.returncode == 0:
                try:
                    with open(stdout) as fin:
                        json.loads(fin.read())
                    return (True, stdout)
                except json.JSONDecodeError as exn:
                    with open(stderr, 'a') as fout:
                        fout.write('\n' + str(exn) + '\n')
                    return (False, stdout, stderr)
        else:
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
                            ] + config.get('extra_args', []),
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
                ] + targets + config.get('extra_args', []),
                'tee': config['tee']
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
                        ] + config.get('extra_args', []) + ['${TERRATEAM_PLAN_FILE}'],
                'tee': config['tee']
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
