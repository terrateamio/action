import logging
import os
import workflow


def run(state, config):
    logging.info('TF_CLOUD : SETUP')
    env = state.env
    terraformrc_path = os.path.expanduser('~') + "/.terraformrc"
    token = env['TF_API_TOKEN']
    with open(terraformrc_path, 'w') as f:
        f.write('credentials "app.terraform.io" {{ token = "{}" }}'.format(token))
    return workflow.make(
        payload={
            'text': 'Writing TF_API_TOKEN to ~/.terraformrc',
            'visible_on': 'error',
        },
        state=state,
        step='tf/tf_cloud_setup',
        success=True)
