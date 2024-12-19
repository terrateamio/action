import abc
import json
import logging
import os
import tempfile

import dir_exec
import hooks
import repo_config as rc
import requests_retry
import results_compat


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
    ENGINE_NAME = 'TERRATEAM_ENGINE_NAME'
    TF_CMD_ENV_NAME = 'TERRATEAM_TF_CMD'
    TOFU_ENV_NAME = 'TOFUENV_TOFU_DEFAULT_VERSION'
    TERRAFORM_ENV_NAME = 'TFENV_TERRAFORM_DEFAULT_VERSION'
    TERRAGRUNT_ENV_NAME = 'TG_DEFAULT_VERSION'
    TERRAGRUNT_TF_PATH_ENV_NAME = 'TERRAGRUNT_TFPATH'

    env[ENGINE_NAME] = engine['name']

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

        # If it is terragrunt specific environment
        if engine['name'] == 'terragrunt' and 'version' in engine:
            env[TERRAGRUNT_ENV_NAME] = engine['version']
            env[TERRAGRUNT_TF_PATH_ENV_NAME] = env[TF_CMD_ENV_NAME]

    else:
        env[TF_CMD_ENV_NAME] = 'terraform'
        version = engine.get('version')

        if not version:
            version = '1.5.7'

        env[TERRAFORM_ENV_NAME] = determine_tf_version(
            repo_root,
            working_dir,
            version)


def _mask_output(secrets, unmasked, output):
    # If the output exactly matches anything in unmasked then return output
    # unchanged.
    if output in unmasked:
        return output
    else:
        for secret in secrets:
            if secret in output:
                output = output.replace(secret, '***')
        return output


# Mask all secrets in value, unless masking it would alter an value in
# "unmasked"
def _mask_secrets(secrets, unmasked, value):
    if isinstance(value, str):
        return _mask_output(secrets, unmasked, value)
    elif isinstance(value, dict):
        ret = {}
        for k, v in value.items():
            ret[k] = _mask_secrets(secrets, unmasked, v)
        return ret
    elif isinstance(value, list):
        ret = []
        for v in value:
            ret.append(_mask_secrets(secrets, unmasked, v))
        return ret
    else:
        return value


def _store_results(state, work_token, api_base_url, results):
    unmasked = set([ds['path'] for ds in state.work_manifest['changed_dirspaces']]
                   + [ds['workspace'] for ds in state.work_manifest['changed_dirspaces']]
                   + [step['step'] for step in results['steps']])

    results = _mask_secrets(state.secrets, unmasked, results)
    results = results_compat.transform(state, results)

    res = requests_retry.put(api_base_url + '/v1/work-manifests/' + work_token,
                             json=results)

    return res


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

    steps = state.outputs

    # Bail out if we failed in prehooks
    if not state.success:
        results = {
            'steps': steps
        }
        ret = _store_results(state, state.work_token, state.api_base_url, results)

        if not ret:
            raise Exception('Failed to send results')
        else:
            return state

    state = state._replace(outputs=[])

    res = dir_exec.run(rc.get_parallelism(state.repo_config),
                       state.work_manifest['changed_dirspaces'],
                       exec_cb.exec,
                       (state,))

    for (s, r) in res:
        state = state._replace(success=state.success and s.success)
        steps.extend(r['outputs'])

    logging.debug('EXEC : HOOKS : POST')

    results_json = os.path.join(state.tmpdir, 'results.json')

    results = {
        'steps': steps,
        'success': state.success
    }

    with open(results_json, 'w') as f:
        f.write(json.dumps(results))

    env = state.env.copy()
    env['TERRATEAM_RESULTS_FILE'] = results_json
    state = state._replace(env=env)

    post_hooks = exec_cb.post_hooks(state)
    state = hooks.run_post_hooks(state._replace(outputs=[]), post_hooks)

    steps.extend(state.outputs)

    results = {
        'steps': steps
    }

    ret = _store_results(state, state.work_token, state.api_base_url, results)

    if ret.status_code != 200:
        logging.info('RESPONSE : STATUS_CODE : %d', ret.status_code)
        logging.info('RESPONSE : HEADERS : %r', ret.headers)
        logging.info('RESPONSE : CONTENT : %r', ret.content)
        raise Exception('Failed to send results')

    return state


def run(state, exec_cb):
    with tempfile.TemporaryDirectory() as tmpdir:
        return _run(state._replace(tmpdir=tmpdir), exec_cb)
