import base64
import hashlib
import json
import logging
import os
import tempfile

import requests

import dir_exec
import hooks
import repo_config as rc
import workflow_step


def _load_plan(work_token, api_base_url, dir_path, workspace, plan_path):
    res = requests.get(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
                       params={'path': dir_path, 'workspace': workspace})

    if res.status_code != 200:
        raise Exception('Could not load plan')

    plan_raw_data = base64.b64decode(res.json()['data'])

    logging.debug('APPLY : LOAD_PLAN : dir_path=%s : workspace=%s : md5=%s',
                  dir_path,
                  workspace,
                  hashlib.md5(plan_raw_data).hexdigest())

    with open(plan_path, 'wb') as f:
        f.write(plan_raw_data)


def _store_results(work_token, api_base_url, results):
    res = requests.put(api_base_url + '/v1/work-manifests/' + work_token,
                       json=results)

    return res.status_code == 200


def _order_dirs_by_rank(dirs):
    ret = {}

    for d in dirs:
        ret.setdefault(d['rank'], []).append(d)

    return [d for d in sorted(ret.keys())]


def _f(state, results, d):
    with tempfile.TemporaryDirectory() as tmpdir:
        logging.debug('EXEC : DIR : %s', d['path'])

        # Need to reset output every iteration unfortunately because we do not
        # have immutable dicts
        state = state._replace(output={})

        path = d['path']
        workspace = d['workspace']
        workflow_idx = d.get('workflow')

        _load_plan(state.work_token,
                   state.api_base_url,
                   path,
                   workspace,
                   os.path.join(tmpdir, 'plan'))

        env = state.env.copy()
        env['TERRATEAM_PLAN_FILE'] = os.path.join(tmpdir, 'plan')
        env['TERRATEAM_DIR'] = path
        env['TERRATEAM_WORKSPACE'] = workspace
        state = state._replace(env=env)

        if workflow_idx is None:
            workflow = rc.get_default_workflow(state.repo_config)
        else:
            workflow = rc.get_workflow(state.repo_config, workflow_idx)

        state = workflow_step.run_steps(
            state._replace(working_dir=os.path.join(state.working_dir, path),
                           path=path,
                           workspace=workspace,
                           workflow=workflow),
            workflow['apply'])

        result = {
            'path': path,
            'workspace': workspace,
            'success': not state.failed,
            'output': state.output.copy()
        }

        return (state, result)


def run(state):
    apply_hooks = rc.get_apply_hooks(state.repo_config)

    logging.debug('EXEC : HOOKS : PRE_APPLY')
    state = hooks.run_pre_hooks(state, apply_hooks)

    if state.failed:
        raise Exception('Failed executing pre apply hooks')

    # We want to run all directories even if one failed, so we need to reset the
    # state failure at the beginning of each one but we want to fail the total
    # operation if any one of them fails.
    results = {
        'dirspaces': [],
        'overall': {
            'success': True
        },
    }

    original_state = state

    res = dir_exec.run(rc.get_parallelism(state.repo_config),
                       state.work_manifest['dirs'],
                       _f,
                       (original_state, results))

    for (s, r) in res:
        state = state._replace(failed=state.failed or s.failed)
        results['dirspaces'].append(r)

    results['overall']['success'] = not state.failed

    # Run post applies no matter what, some of they may run on failure
    logging.debug('EXEC : HOOKS : POST_APPLY')
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, 'results'), 'w') as f:
            f.write(json.dumps(results))

        env = state.env.copy()
        env['TERRATEAM_RESULTS_FILE'] = os.path.join(tmpdir, 'results')
        state = state._replace(env=env)
        state = hooks.run_post_hooks(state, apply_hooks)

    ret = _store_results(state.work_token, state.api_base_url, results)

    if not ret:
        raise Exception('Failed to send results')

    if not results['overall']['success']:
        raise Exception('Failed executing plan')

    return state
