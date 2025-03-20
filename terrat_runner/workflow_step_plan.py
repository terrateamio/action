import base64
import hashlib
import json
import logging
import string
import time

import cmd
import repo_config as rc
import requests_retry

import workflow


ACCESS_KEY_ID = 'access_key_id'
SECRET_ACCESS_KEY = 'secret_access_key'


def _store_plan_data(plan_data, work_token, api_base_url, dir_path, workspace, has_changes):
    plan_data = base64.b64encode(json.dumps(plan_data).encode('utf-8')).decode('utf-8')

    res = requests_retry.post(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
                              json={
                                  'path': dir_path,
                                  'workspace': workspace,
                                  'plan_data': plan_data,
                                  'has_changes': has_changes
                              })

    return (res.status_code == 200, res.text)


def _store_plan_terrateam(work_token, api_base_url, dir_path, workspace, plan_path, has_changes):
    try:
        with open(plan_path, 'rb') as f:
            plan_data_raw = f.read()
            plan_data_encoded = base64.b64encode(plan_data_raw).decode('utf-8')
            plan_data = {
                'data': plan_data_encoded,
                'method': 'terrateam',
                'version': 1
            }

        logging.debug('PLAN : STORE_PLAN : dir_path=%s : workspace=%s : md5=%s',
                      dir_path,
                      workspace,
                      hashlib.md5(plan_data_raw).hexdigest())

        return _store_plan_data(plan_data,
                                work_token,
                                api_base_url,
                                dir_path,
                                workspace,
                                has_changes)
    except Exception as exn:
        logging.exception('Failed')
        return (False, str(exn))


def _store_plan_cmd(state,
                    plan_storage,
                    work_token,
                    api_base_url,
                    dir_path,
                    workspace,
                    plan_path,
                    has_changes):
    tmpl_vars = {
        'date': time.strftime('%Y-%m-%d'),
        'dir': dir_path,
        'plan_path': plan_path,
        'time': time.strftime('%H%M%S'),
        'token': work_token,
        'workspace': workspace,
    }
    plan_data = {
        'delete': [string.Template(s).safe_substitute(tmpl_vars) for s in plan_storage.get('delete', [])],
        'fetch': [string.Template(s).safe_substitute(tmpl_vars) for s in plan_storage['fetch']],
        'method': 'cmd',
        'version': 1,
    }
    store_cmd = [string.Template(s).safe_substitute(tmpl_vars) for s in plan_storage['store']]
    (proc, stdout, stderr) = cmd.run_with_output(state, {'cmd': store_cmd})
    if proc.returncode == 0:
        return _store_plan_data(plan_data, work_token, api_base_url, dir_path, workspace, has_changes)
    else:
        return (False, '\n'.join([stderr, stdout]))


def _store_plan_s3(state, plan_storage, work_token, api_base_url, dir_path, workspace, plan_path, has_changes):
    s3_path = plan_storage.get('path', 'terrateam/plans/$dir/$workspace/$date-$time-$token')
    url = 's3://' + plan_storage['bucket'] + '/' + s3_path

    cmd_prefix = []
    if ACCESS_KEY_ID in plan_storage or SECRET_ACCESS_KEY in plan_storage:
        cmd_prefix += ['env']
        if ACCESS_KEY_ID in plan_storage:
            cmd_prefix += ['AWS_ACCESS_KEY_ID=' + plan_storage[ACCESS_KEY_ID]]
        if SECRET_ACCESS_KEY in plan_storage:
            cmd_prefix += ['AWS_SECRET_ACCESS_KEY=' + plan_storage[SECRET_ACCESS_KEY]]

    store_extra_args = plan_storage.get('store_extra_args', [])
    fetch_extra_args = plan_storage.get('fetch_extra_args', [])
    delete_extra_args = plan_storage.get('delete_extra_args', [])

    if plan_storage.get('delete_used_plans', True):
        delete_cmd = cmd_prefix + ['aws', 's3', 'rm'] + delete_extra_args + [url, '--region', plan_storage['region']]
    else:
        delete_cmd = []

    fetch_cmd = (cmd_prefix +
                 ['aws', 's3', 'cp'] +
                 fetch_extra_args +
                 [url, '$plan_dst_path', '--region', plan_storage['region']])
    store_cmd = (cmd_prefix +
                 ['aws', 's3', 'cp'] +
                 store_extra_args +
                 ['$plan_path', url, '--region', plan_storage['region']])

    return _store_plan_cmd(
        state,
        {
            'delete': delete_cmd,
            'fetch': fetch_cmd,
            'store': store_cmd,
        },
        work_token,
        api_base_url,
        dir_path,
        workspace,
        plan_path,
        has_changes)


def _store_plan(state, plan_storage, work_token, api_base_url, dir_path, workspace, plan_path, has_changes):
    method = plan_storage['method']
    if method == 'terrateam':
        return _store_plan_terrateam(work_token, api_base_url, dir_path, workspace, plan_path, has_changes)
    elif method == 'cmd':
        return _store_plan_cmd(state,
                               plan_storage,
                               work_token,
                               api_base_url,
                               dir_path,
                               workspace,
                               plan_path,
                               has_changes)
    elif method == 's3':
        return _store_plan_s3(state,
                              plan_storage,
                              work_token,
                              api_base_url,
                              dir_path,
                              workspace,
                              plan_path,
                              has_changes)
    else:
        raise Exception('Unknown method')


def run(state, config):
    (success, has_changes, stdout, stderr) = state.engine.plan(state, config)

    if not success:
        return workflow.Result2(
            payload={
                'text': '\n'.join([stderr, stdout]),
                'visible_on': 'always',
            },
            state=state,
            step=state.engine.name + '/plan',
            success=success)

    res = state.engine.diff(state, config)

    if res:
        (success, diff_stdout, diff_stderr) = res
    else:
        success = True
        diff_stdout = ''
        diff_stderr = ''

    if not success:
        return workflow.Result2(
            payload={
                'text': '\n'.join([diff_stderr, diff_stdout]),
                'visible_on': 'always',
            },
            state=state,
            step=state.engine.name + '/plan',
            success=success)

    plan_storage = rc.get_plan_storage(state.repo_config)

    (success, output) = _store_plan(state,
                                    plan_storage,
                                    state.work_token,
                                    state.api_base_url,
                                    state.env['TERRATEAM_DIR'],
                                    state.env['TERRATEAM_WORKSPACE'],
                                    state.env['TERRATEAM_PLAN_FILE'],
                                    has_changes)

    if not success:
        logging.error('PLAN_STORE_FAILED : %s : %s : %s',
                      state.env['TERRATEAM_DIR'],
                      state.env['TERRATEAM_WORKSPACE'],
                      output)
        return workflow.Result2(
            payload={
                'text': 'Could not store plan file, with the following error:\n\n' + output,
                'visible_on': 'always',
            },
            state=state,
            step=state.engine.name + '/plan',
            success=success)

    return workflow.Result2(
        payload={
            'plan': diff_stdout,
            'has_changes': has_changes,
            'text': stdout,
            'visible_on': 'always',
        },
        state=state,
        step=state.engine.name + '/plan',
        success=True)
