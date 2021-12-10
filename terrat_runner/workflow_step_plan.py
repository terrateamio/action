import workflow_step_terraform


def run(state, config):
    config = config.copy()
    config['args'] = ['plan', '-out', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'plan'
    (failed, state) = workflow_step_terraform.run(state, config)

    if failed:
        return (failed, state)

    config['args'] = ['show', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'plan_text'

    return workflow_step_terraform.run(state, config)
