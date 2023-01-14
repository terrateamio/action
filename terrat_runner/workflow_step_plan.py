import base64
import hashlib
import logging

import requests_retry
import workflow_step_terraform


def _store_plan(work_token, api_base_url, dir_path, workspace, plan_path):
    try:
        with open(plan_path, 'rb') as f:
            plan_raw_data = f.read()
            plan_data = base64.b64encode(plan_raw_data).decode('utf-8')

        logging.debug('PLAN : STORE_PLAN : dir_path=%s : workspace=%s : md5=%s',
                      dir_path,
                      workspace,
                      hashlib.md5(plan_raw_data).hexdigest())

        res = requests_retry.post(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
                                  json={
                                      'path': dir_path,
                                      'workspace': workspace,
                                      'plan_data': plan_data
                                  })

        return res.status_code == 200
    except Exception as exn:
        print('Failed: {}'.format(exn))
        return False


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
    config = {
        'args': ['show', '$TERRATEAM_PLAN_FILE'],
        'output_key': 'plan_text'
    }

    result = workflow_step_terraform.run(state, config)

    if result.failed:
        return result._replace(workflow_step={'type': 'plan'})

    outputs['plan_text'] = result.outputs['text']

    success = _store_plan(state.work_token,
                          state.api_base_url,
                          state.env['TERRATEAM_DIR'],
                          state.env['TERRATEAM_WORKSPACE'],
                          state.env['TERRATEAM_PLAN_FILE'])
    result = result._replace(failed=not success)

    return result._replace(workflow_step={'type': 'plan'},
                           outputs=outputs)
