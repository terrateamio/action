import abc
import json
import logging
import os
import tempfile

import requests

import dir_exec
import hooks
import repo_config as rc


class ExecInterface(abc.ABC):
    @abc.abstractmethod
    def pre_hooks(self, state):
        pass

    @abc.abstractmethod
    def post_hooks(self, state):
        pass

    @abc.abstractmethod
    def exec(self, state, d):
        pass


def _store_results(work_token, api_base_url, results):
    res = requests.put(api_base_url + '/v1/work-manifests/' + work_token,
                       json=results)

    return res.status_code == 200


def _run(state, exec_cb):

    env = state.env.copy()
    env['TERRATEAM_TERRAFORM_VERSION'] = rc.get_default_tf_version(state.repo_config)
    state = state._replace(env=env)

    pre_hooks = exec_cb.pre_hooks(state)

    logging.debug('EXEC : HOOKS : PRE')
    state = hooks.run_pre_hooks(state, pre_hooks)

    # Bail out if we failed in prehooks
    if state.failed:
        results = {
            'dirspaces': [
                {
                    'path': ds['path'],
                    'workspace': ds['workspace'],
                    'success': False,
                    'outputs': [],
                }
                for ds in state.work_manifest['changed_dirspaces']
            ],
            'overall': {
                'success': False,
                'outputs': {
                    'pre': state.outputs,
                    'post': []
                }
            },
        }
        ret = _store_results(state.work_token, state.api_base_url, results)

        if not ret:
            raise Exception('Failed to send results')
        else:
            raise Exception('Failed executing pre hooks')

    pre_hook_outputs = state.outputs

    state = state._replace(outputs=[])

    res = dir_exec.run(rc.get_parallelism(state.repo_config),
                       state.work_manifest['changed_dirspaces'],
                       exec_cb.exec,
                       (state,))

    dirspaces = []
    for (s, r) in res:
        state = state._replace(failed=state.failed or s.failed)
        dirspaces.append(r)

    logging.debug('EXEC : HOOKS : POST')

    results_json = os.path.join(state.tmpdir, 'results.json')

    results = {
        'dirspaces': dirspaces,
        'overall': {
            'success': not state.failed,
        }
    }

    with open(results_json, 'w') as f:
        f.write(json.dumps(results))

    env = state.env.copy()
    env['TERRATEAM_RESULTS_FILE'] = results_json
    state = state._replace(env=env)

    post_hooks = exec_cb.post_hooks(state)
    state = hooks.run_post_hooks(state._replace(outputs=[]), post_hooks)

    results['overall']['success'] = not state.failed
    results['overall']['outputs'] = {
        'pre': pre_hook_outputs,
        'post': state.outputs
    }

    ret = _store_results(state.work_token, state.api_base_url, results)

    if not ret:
        raise Exception('Failed to send results')

    if not results['overall']['success']:
        raise Exception('Failed executing plan')

    return state


def run(state, exec_cb):
    with tempfile.TemporaryDirectory() as tmpdir:
        return _run(state._replace(tmpdir=tmpdir), exec_cb)
