import logging

import repo_config
import workflow_step_terraform


def run(state, config):
    original_config = config
    config = original_config.copy()
    config['args'] = ['init']
    config['output_key'] = 'init'

    (failed, state) = workflow_step_terraform.run(state, config)
    if failed:
        return (failed, state)

    create_and_select_workspace = repo_config.get_create_and_select_workspace(state.repo_config,
                                                                              state.path)

    logging.info('WORKFLOW_STEP_INIT : CREATE_AND_SELECT_WORKSPACE : %s : %r',
                 state.path,
                 create_and_select_workspace)

    if create_and_select_workspace:
        env = state.env.copy()
        env['TF_WORKSPACE'] = state.workspace
        state = state._replace(env=env)

    return (False, state)
