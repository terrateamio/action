import re

import workflow_step_terraform


def run(state, config):
    config = config.copy()
    config['args'] = ['plan', '-out', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'plan'
    (failed, state) = workflow_step_terraform.run(state, config)

    if failed:
        return (failed, state)

    # Grab just the plan output.  If running the plan succeded, we want to just
    # show the plan text.  If it failed above, we want to be able to show the
    # user the entire terminal output.
    config['args'] = ['show', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'plan_text'

    (failed, state) = workflow_step_terraform.run(state, config)

    if failed:
        return (failed, state)

    # Do a little translation to make it match diff syntax
    plan_diff = state.output['plan_text'].decode('utf-8')
    plan_diff = re.sub(r'^( +)([-+~])', r'\2\1', plan_diff, flags=re.MULTILINE)
    plan_diff = re.sub(r'^~', r'!', plan_diff, flags=re.MULTILINE)

    state.output['plan_diff'] = plan_diff.encode('utf-8')

    return (failed, state)
