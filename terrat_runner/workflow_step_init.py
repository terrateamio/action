import workflow_step_terraform


def run(state, config):
    original_config = config
    config = original_config.copy()
    config['args'] = ['init']
    config['output_key'] = 'init'

    (failed, state) = workflow_step_terraform.run(state, config)
    if failed:
        return (failed, state)

    return (False, state)
