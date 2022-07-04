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
    results = {
        'dirspaces': [],
        'overall': {
            'success': True
        },
    }

    pre_hooks = exec_cb.pre_hooks(state)

    logging.debug('EXEC : HOOKS : PRE')
    state = hooks.run_pre_hooks(state, pre_hooks)

    if state.failed:
        raise Exception('Failed executing pre hooks')

    res = dir_exec.run(rc.get_parallelism(state.repo_config),
                       state.work_manifest['dirs'],
                       exec_cb.exec,
                       (state,))

    for (s, r) in res:
        state = state._replace(failed=state.failed or s.failed)
        results['dirspaces'].append(r)

    results['overall']['success'] = not state.failed

    logging.debug('EXEC : HOOKS : POST')

    results_json = os.path.join(state.tmpdir, 'results.json')

    with open(results_json, 'w') as f:
        f.write(json.dumps(results))

    env = state.env.copy()
    env['TERRATEAM_RESULTS_FILE'] = results_json
    state = state._replace(env=env)
    post_hooks = exec_cb.post_hooks(state)
    state = hooks.run_post_hooks(state, post_hooks)

    ret = _store_results(state.work_token, state.api_base_url, results)

    if not ret:
        raise Exception('Failed to send results')

    if not results['overall']['success']:
        raise Exception('Failed executing plan')

    return state


def run(state, exec_cb):
    with tempfile.TemporaryDirectory() as tmpdir:
        return _run(state._replace(tmpdir=tmpdir), exec_cb)
