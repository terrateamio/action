import abc
import json
import logging
import os
import tempfile

import dir_exec
import hooks
import repo_config as rc
import requests_retry


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


def determine_tf_version(repo_root, working_dir, workflow_version):
    def _read(fname):
        with open(fname) as f:
            return f.read().strip()

    path = working_dir
    while path != repo_root:
        if os.path.exists(os.path.join(path, '.terraform-version')):
            return _read(os.path.join(path, '.terraform-version'))
        path = os.path.dirname(path)

    if os.path.exists(os.path.join(repo_root, '.terraform-version')):
        return _read(os.path.join(repo_root, '.terraform-version'))
    else:
        return workflow_version


def set_tf_version_env(env, repo_config, engine, repo_root, working_dir):
    TF_CMD_ENV_NAME = 'TERRATEAM_TF_CMD'
    TOFU_ENV_NAME = 'TOFUENV_TOFU_DEFAULT_VERSION'
    TERRAFORM_ENV_NAME = 'TERRATEAM_TERRAFORM_VERSION'

    if engine['name'] == 'tofu':
        env[TF_CMD_ENV_NAME] = 'tofu'
        version = engine.get('version')
        if version:
            env[TOFU_ENV_NAME] = version
    elif engine['name'] in ['cdktf', 'terragrunt']:
        # If cdktf or terragrunt, set the appropriate terraform/tofu version if
        # it exists.
        if engine['tf_cmd'] == 'tofu':
            env[TF_CMD_ENV_NAME] = 'tofu'
            version_env_name = TOFU_ENV_NAME
            version = engine.get('tf_version')
            if version:
                env[version_env_name] = version
        else:
            env[TF_CMD_ENV_NAME] = 'terraform'
            env[TERRAFORM_ENV_NAME] = engine.get('tf_version',
                                                 rc.get_default_tf_version(repo_config))
    else:
        env[TF_CMD_ENV_NAME] = 'terraform'
        version = engine.get('version')

        if version:
            env[TERRAFORM_ENV_NAME] = determine_tf_version(
                repo_root,
                working_dir,
                version)
        else:
            env[TERRAFORM_ENV_NAME] = determine_tf_version(
                repo_root,
                working_dir,
                rc.get_default_tf_version(repo_config))


def _store_results(work_token, api_base_url, results):
    res = requests_retry.put(api_base_url + '/v1/work-manifests/' + work_token,
                             json=results)

    return res.status_code == 200


def _run(state, exec_cb):
    # Setup the global terraform version, for use if terraform is called in any hooks.
    env = state.env.copy()
    # Using state.working_dir twice as a bit of a hack because
    # determine_tf_version expects the directory that we are running the command
    # in as an option as well, but at this point there is none.
    set_tf_version_env(
        env,
        state.repo_config,
        rc.get_engine(state.repo_config),
        state.working_dir,
        state.working_dir)

    env['TERRATEAM_TMPDIR'] = state.tmpdir
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
        raise Exception('Failed executing operation')

    return state


def run(state, exec_cb):
    with tempfile.TemporaryDirectory() as tmpdir:
        return _run(state._replace(tmpdir=tmpdir), exec_cb)
