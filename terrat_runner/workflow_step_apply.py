import workflow
import workflow_step_terraform


def run(state, config):
    config = config.copy()
    config['args'] = ['apply', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'apply'
    result = workflow_step_terraform.run(state, config)
    return workflow.Result(failed=result.failed,
                           state=result.state,
                           workflow_step={'type': 'apply'},
                           outputs=result.outputs)
