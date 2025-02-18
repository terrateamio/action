import base64
import hashlib
import json
import logging
import string
import time

import cmd
import repo_config as rc
import requests_retry

import workflow_step_run
import workflow_step_terraform


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


def run_plan(state, config, targets=None):
    config = config.copy()
    config['args'] = ['plan', '-detailed-exitcode', '-out', '$TERRATEAM_PLAN_FILE']

    if targets:
        config['args'].extend(['-target=' + addr for addr in targets])

    result = workflow_step_terraform.run(state, config)

    if (not result.success and (
            'exit_code' not in result.payload
            or result.payload['exit_code'] == 1)):
        return result._replace(step='tf/plan')

    return result._replace(step='tf/plan')


def plan_fast_and_loose(state, config):
    config = config.copy()
    config['args'] = ['plan', '-detailed-exitcode', '-json', '-refresh=false']

    result = workflow_step_terraform.run(state, config)

    if (not result.success and (
            'exit_code' not in result.payload
            or result.payload['exit_code'] == 1)):
        return result._replace(step='tf/plan')

    output = result.payload['text']

    targets = []

    for line in output.splitlines():
        line = json.loads(line)

        if line.get('type') in ['planned_change', 'resource_drift']:
            targets.append(line['change']['resource']['addr'])

    return run_plan(state, config, targets)


def run_tf(state, config):
    if config.get('mode') == 'fast-and-loose':
        result = plan_fast_and_loose(state, config)
    else:
        result = run_plan(state, config)

    if (not result.success and (
            'exit_code' not in result.payload
            or result.payload['exit_code'] == 1)):
        return result._replace(step='tf/plan')

    # The terraform CLI has an exit code of 2 if the plan contains changes.
    has_changes = result.payload.get('exit_code') == 2

    payload = result.payload.copy()

    # Grab just the plan output.  If running the plan succeded, we want to just
    # show the plan text.  If it failed above, we want to be able to show the
    # user the entire terminal output.
    config = {
        'args': ['show', '$TERRATEAM_PLAN_FILE'],
    }

    result = workflow_step_terraform.run(state, config)

    if not result.success:
        return result._replace(step='tf/plan')

    payload['plan'] = result.payload['text']
    payload['has_changes'] = has_changes

    plan_storage = rc.get_plan_storage(state.repo_config)

    (success, output) = _store_plan(state,
                                    plan_storage,
                                    state.work_token,
                                    state.api_base_url,
                                    state.env['TERRATEAM_DIR'],
                                    state.env['TERRATEAM_WORKSPACE'],
                                    state.env['TERRATEAM_PLAN_FILE'],
                                    has_changes)

    if success:
        result = result._replace(success=success)
    else:
        logging.error('PLAN_STORE_FAILED : %s : %s : %s',
                      state.env['TERRATEAM_DIR'],
                      state.env['TERRATEAM_WORKSPACE'],
                      output)
        result = result._replace(success=False)
        payload = {'text': 'Could not store plan file, with the following error:\n\n' + output}

    return result._replace(payload=payload, step='tf/plan')


def run_pulumi(state, config):
    logging.info('WORKFLOW_STEP_PLAN : engine=%s',
                 state.workflow['engine']['name'])

    result = workflow_step_run.run(
        state,
        {
            'cmd': ['pulumi', 'preview']
        })

    if not result.success:
        return result._replace(step='pulumi/plan')

    has_changes = True

    payload = result.payload
    payload['plan'] = result.payload['text']
    payload['has_changes'] = has_changes

    with open(state.env['TERRATEAM_PLAN_FILE'], 'w') as f:
        f.write('{}')

    plan_storage = rc.get_plan_storage(state.repo_config)

    (success, output) = _store_plan(state,
                                    plan_storage,
                                    state.work_token,
                                    state.api_base_url,
                                    state.env['TERRATEAM_DIR'],
                                    state.env['TERRATEAM_WORKSPACE'],
                                    state.env['TERRATEAM_PLAN_FILE'],
                                    has_changes)

    if success:
        result = result._replace(success=success)
    else:
        logging.error('PLAN_STORE_FAILED : %s : %s : %s',
                      state.env['TERRATEAM_DIR'],
                      state.env['TERRATEAM_WORKSPACE'],
                      output)
        result = result._replace(success=False)
        payload = {'text': 'Could not store plan file, with the following error:\n\n' + output}

    return result._replace(payload=payload, step='pulumi/plan')


def run(state, config):
    if state.env['TERRATEAM_ENGINE_NAME'] == 'pulumi':
        return run_pulumi(state, config)
    else:
        return run_tf(state, config)
