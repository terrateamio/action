import workflow_step_terraform


def run(state, config):
    original_config = config
    config = original_config.copy()
    config['args'] = ['init']
    config['output_key'] = 'init'

    result = workflow_step_terraform.run(state, config)

    return result._replace(workflow_step={'type': 'init'})
