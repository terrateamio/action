import workflow_step_terraform


def run(state, config):
    config = config.copy()
    config['args'] = ['apply', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'apply'
    return workflow_step_terraform.run(state, config)
