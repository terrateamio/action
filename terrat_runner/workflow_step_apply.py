import base64
import hashlib
import json
import logging
import string

import cmd
import repo_config as rc
import requests_retry
import retry
import workflow
import workflow_step_terraform


def _load_plan(state, work_token, api_base_url, dir_path, workspace, plan_path):
    res = requests_retry.get(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
                             params={'path': dir_path, 'workspace': workspace})

    if res.status_code != 200:
        return (False, 'Could not load plan from backend')

    plan_data = base64.b64decode(res.json()['data'])

    try:
        plan_data = json.loads(plan_data)

        if plan_data['method'] == 'terrateam':
            plan_data_encoded = plan_data['data']
            plan_data_raw = base64.b64decode(plan_data_encoded)
            logging.debug('APPLY : LOAD_PLAN : dir_path=%s : workspace=%s : md5=%s',
                          dir_path,
                          workspace,
                          hashlib.md5(plan_data_raw).hexdigest())

            with open(plan_path, 'wb') as f:
                f.write(plan_data_raw)

            return (True, None)
        elif plan_data['method'] == 'cmd':
            tmpl_vars = {
                'plan_dst_path': plan_path
            }
            fetch_cmd = [string.Template(s).safe_substitute(tmpl_vars) for s in plan_data['fetch']]
            proc = cmd.run(state, {'cmd': fetch_cmd})
            if proc.returncode != 0:
                return (False, 'Failed to fetch plan, see action logs for more details')
            if plan_data.get('delete'):
                cmd.run(state, {'cmd': plan_data['delete']})
                return (True, None)
        else:
            raise Exception('Unknown method')
    except json.JSONDecodeError:
        plan_data_raw = plan_data
        logging.debug('APPLY : LOAD_PLAN : dir_path=%s : workspace=%s : md5=%s',
                      dir_path,
                      workspace,
                      hashlib.md5(plan_data_raw).hexdigest())

        with open(plan_path, 'wb') as f:
            f.write(plan_data_raw)

        return (True, None)


def _test_success_update_config(config):
    def _f(ret):
        if not ret.success:
            config['args'] = ['apply', '-auto-approve']
        return ret.success

    return _f


def run(state, config):
    config = config.copy()
    config['args'] = ['apply', '$TERRATEAM_PLAN_FILE']

    (success, output) = _load_plan(state,
                                   state.work_token,
                                   state.api_base_url,
                                   state.path,
                                   state.workspace,
                                   state.env['TERRATEAM_PLAN_FILE'])

    if not success:
        return workflow.Result2(payload={'text': output},
                                state=state,
                                step='tf/apply',
                                success=False)

    retry_config = rc.get_retry(config)
    tries = retry_config['enabled'] and retry_config['tries'] or 1
    result = retry.run(
        lambda: workflow_step_terraform.run(state, config),
        retry.finite_tries(tries, _test_success_update_config(config)),
        retry.betwixt_sleep_with_backoff(retry_config['initial_sleep'],
                                         retry_config['backoff']))

    if result.success:
        result_output = workflow_step_terraform.run(state, {'args': ['output', '-json']})
        payload = result.payload
        if result_output.success:
            outputs = json.loads(result_output.payload['text'])
            if outputs:
                payload['outputs'] = outputs
                result = result._replace(payload=payload)

    return result._replace(step='tf/apply')
