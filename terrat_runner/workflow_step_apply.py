import base64
import hashlib
import json
import logging
import os
import string

import cmd
import kv_store
import requests_retry
import ttm
import workflow


def _load_plan(state, work_token, api_base_url, dir_path, workspace, plan_path):
    res = requests_retry.get(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
                             params={'path': dir_path, 'workspace': workspace})

    if res.status_code != 200:
        return (False, 'Could not load plan from backend')

    plan_data = base64.b64decode(res.json()['data'])

    try:
        plan_data = json.loads(plan_data)

        if plan_data['method'] == 'terrateam' and plan_data['version'] == 1:
            plan_data_encoded = plan_data['data']
            plan_data_raw = base64.b64decode(plan_data_encoded)
            logging.debug('APPLY : LOAD_PLAN : dir_path=%s : workspace=%s : md5=%s',
                          dir_path,
                          workspace,
                          hashlib.md5(plan_data_raw).hexdigest())

            with open(plan_path, 'wb') as f:
                f.write(plan_data_raw)

            return (True, None)
        elif plan_data['method'] == 'terrateam' and plan_data['version'] == 2:
            logging.debug('APPLY : LOAD_PLAN : dir_path=%s : workspace=%s : key=%s',
                          dir_path,
                          workspace,
                          plan_data['data']['@plan_data'])

            ttm.kv_download(state,
                            state.work_manifest['api_base_url'],
                            state.work_manifest['installation_id'],
                            plan_data['data']['@plan_data'],
                            plan_path)

            ttm.kv_delete(state,
                          state.work_manifest['api_base_url'],
                          state.work_manifest['installation_id'],
                          plan_data['data']['@plan_data'])

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


def run(state, config):
    config = config.copy()
    (success, output) = _load_plan(state,
                                   state.work_token,
                                   state.api_base_url,
                                   state.path,
                                   state.workspace,
                                   state.env['TERRATEAM_PLAN_FILE'])

    if not success:
        return workflow.make(
            payload={
                'text': output,
                'visible_on': 'always',
            },
            state=state,
            step=state.engine.name + '/apply',
            success=False)

    config['tee'] = kv_store.gen_unique_key_path(
        state,
        lambda _: kv_store.mk_dirspace_key(state, 'apply'))
    (success, stdout_key, stderr_key) = state.engine.apply(state, config)

    if not success:
        return workflow.make(
            payload={
                '@text': os.path.basename(stdout_key),
                '@stderr': os.path.basename(stderr_key),
                'visible_on': 'always'
            },
            state=state,
            step=state.engine.name + '/apply',
            success=False)

    res = state.engine.outputs(state, config)

    if res:
        (success, outputs_stdout, outputs_stderr) = res
    else:
        success = True
        outputs_stdout = '{}'
        outputs_stderr = ''

    try:
        outputs = json.loads(outputs_stdout)
        if outputs:
            return workflow.Result2(
                payload={
                    '@text': os.path.join(stdout_key),
                    'outputs': outputs,
                    'visible_on': 'always',
                },
                state=state,
                step=state.engine.name + '/apply',
                success=True)
        else:
            return workflow.Result2(
                payload={
                    '@text': os.path.basename(stdout_key),
                    'visible_on': 'always',
                },
                state=state,
                step=state.engine.name + '/apply',
                success=True)
    except json.JSONDecodeError as exn:
        return workflow.Result2(
            payload={
                'text': '\n'.join([outputs_stderr, outputs_stdout]),
                'error': str(exn),
                'visible_on': 'always',
            },
            state=state,
            step=state.engine.name + '/apply',
            sucecss=False)
