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


def format_diff(text):
    return re.sub(r'^(\s+)([+\-~])', r'\2\1', text, flags=re.MULTILINE)


class Engine:
    def __init__(self, name, tf_cmd):
        self.name = name
        self.tf_cmd = tf_cmd

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


def make(tf_cmd='${TERRATEAM_TF_CMD}'):
    return Engine(name='tf', tf_cmd=tf_cmd)
