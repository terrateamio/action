import logging
import os
import shutil

import cmd
import repo_config
import retry
import workflow_step_terraform

TRIES = 3
INITIAL_SLEEP = 1
BACKOFF = 1.5


def run(state, config):
    original_config = config
    config = original_config.copy()
    config['args'] = ['init']
    config['output_key'] = 'init'

    # If there is already a .terraform dir, delete it
    terraform_path = os.path.join(state.working_dir, '.terraform')
    if os.path.exists(terraform_path):
        shutil.rmtree(terraform_path)

    result = retry.run(
        lambda: workflow_step_terraform.run(state, config),
        retry.finite_tries(TRIES, lambda result: not result.failed),
        retry.betwixt_sleep_with_backoff(INITIAL_SLEEP, BACKOFF))

    if result.failed:
        return result

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

            return result._replace(failed=proc.returncode != 0)

    return result
