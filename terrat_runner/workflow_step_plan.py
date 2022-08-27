import workflow_step_terraform


def run(state, config):
    config = config.copy()
    config['args'] = ['plan', '-out', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'plan'

    outputs = {}

    result = workflow_step_terraform.run(state, config)

    if result.failed:
        return result._replace(workflow_step={'type': 'plan'})

    outputs['plan'] = result.outputs['text']

    # Grab just the plan output.  If running the plan succeded, we want to just
    # show the plan text.  If it failed above, we want to be able to show the
    # user the entire terminal output.
    config['args'] = ['show', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'plan_text'

    result = workflow_step_terraform.run(state, config)

    if result.failed:
        return result._replace(workflow_step={'type': 'plan'})

    outputs['plan_text'] = result.outputs['text']

    return result._replace(workflow_step={'type': 'plan'},
                           outputs=outputs)
