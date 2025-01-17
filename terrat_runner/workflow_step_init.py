import logging
import os
import shutil

import cmd
import repo_config
import retry

import workflow_step_run
import workflow_step_terraform

TRIES = 3
INITIAL_SLEEP = 1
BACKOFF = 1.5


def run_tf(state, config):
    original_config = config
    config = original_config.copy()
    config['args'] = ['init']

    # If there is already a .terraform dir, delete it
    terraform_path = os.path.join(state.working_dir, '.terraform')
    if os.path.exists(terraform_path):
        shutil.rmtree(terraform_path)

    result = retry.run(
        lambda: workflow_step_terraform.run(state, config),
        retry.finite_tries(TRIES, lambda result: result.success),
        retry.betwixt_sleep_with_backoff(INITIAL_SLEEP, BACKOFF))

    if not result.success:
        return result._replace(step='tf/init')

    create_and_select_workspace = repo_config.get_create_and_select_workspace(state.repo_config,
                                                                              state.path)

    logging.info(
        ('WORKFLOW_STEP_INIT : '
         'CREATE_AND_SELECT_WORKSPACE : %s : '
         'engine=%s : create_and_select_workspace=%r'),
        result.state.path,
        state.workflow['engine']['name'],
        create_and_select_workspace)

    if state.workflow['engine']['name'] in ['terraform', 'tofu'] and create_and_select_workspace:
        config = original_config.copy()
        config['cmd'] = ['${TERRATEAM_TF_CMD}', 'workspace', 'select', state.workspace]
        proc = cmd.run(state, config)

        if proc.returncode != 0:
            # TODO: Is this safe?!
            config['cmd'] = ['${TERRATEAM_TF_CMD}', 'workspace', 'new', state.workspace]
            proc = cmd.run(state, config)

            return result._replace(success=(proc.returncode == 0))

    return result._replace(step='tf/init')


def run_pulumi(state, config):
    logging.info('WORKFLOW_STEP_INIT : engine=%s',
                 state.workflow['engine']['name'])

    result = workflow_step_run.run(
        state,
        {
            'cmd': (['pulumi', 'login'] + config.get('extra_args', []))
        })._replace(step='pulumi/init')

    if not result.success:
        return result

    result = workflow_step_run.run(
        state,
        {
            'cmd': ['pulumi', 'stack', 'select', state.workspace],
        })._replace(step='pulumi/init')

    return result


def run(state, config):
    if state.env['TERRATEAM_ENGINE_NAME'] == 'pulumi':
        return run_pulumi(state, config)
    else:
        return run_tf(state, config)
