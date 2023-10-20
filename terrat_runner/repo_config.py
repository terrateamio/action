import os
import yaml


def _get(d, k, default):
    v = d.get(k, default)
    if v is None:
        return default
    else:
        return v


def load(paths):
    for path in paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                return yaml.safe_load(f.read())

    return {}


def _default_plan_workflow():
    return [
        {'type': 'init'},
        {'type': 'plan'}
    ]


def _default_apply_workflow():
    return [
        {'type': 'init'},
        {'type': 'apply'}
    ]


def _get_hooks(hooks):
    if not hooks:
        return {'pre': [], 'post': []}
    else:
        return {
            'pre': _get(hooks, 'pre', []),
            'post': _get(hooks, 'post', [])
        }


def get_all_hooks(repo_config):
    return _get_hooks(_get(_get(repo_config, 'hooks', {}), 'all', {}))


def get_plan_hooks(repo_config):
    return _get_hooks(_get(_get(repo_config, 'hooks', {}), 'plan', {}))


def get_apply_hooks(repo_config):
    return _get_hooks(_get(_get(repo_config, 'hooks', {}), 'apply', {}))


def get_plan_workflow(repo_config, idx):
    return repo_config['workflows'][idx].get('plan', _default_plan_workflow())


def get_apply_workflow(repo_config, idx):
    return repo_config['workflows'][idx].get('apply', _default_apply_workflow())


def get_workflow(repo_config, idx):
    workflow = repo_config['workflows'][idx]
    return {
        'apply': workflow.get('apply', _default_apply_workflow()),
        'cdktf': workflow.get('cdktf', False),
        'plan': workflow.get('plan', _default_plan_workflow()),
        'terraform_version': workflow.get('terraform_version', get_default_tf_version(repo_config)),
        'terragrunt': workflow.get('terragrunt', False),
    }


def get_default_workflow(repo_config):
    return {
        'apply': _default_apply_workflow(),
        'cdktf': False,
        'plan': _default_plan_workflow(),
        'terraform_version': get_default_tf_version(repo_config),
        'terragrunt': False,
    }


def get_default_tf_version(repo_config):
    return repo_config.get('default_tf_version', 'latest')


def get_parallelism(repo_config):
    return repo_config.get('parallel_runs', 3)


def get_create_and_select_workspace(repo_config, path):
    dirs = repo_config.get('dirs')
    if dirs is None:
        dirs = {}
    return dirs.get(path, {}).get('create_and_select_workspace',
                                  repo_config.get('create_and_select_workspace', True))


def get_cost_estimation(repo_config):
    cost_estimation = _get(repo_config, 'cost_estimation', {})
    return {
        'enabled': cost_estimation.get('enabled', True),
        'provider': cost_estimation.get('provider', 'infracost'),
        'currency': cost_estimation.get('currency', 'USD')
    }


def get_retry(config):
    retry = _get(config, 'retry', {})
    return {
        'enabled': _get(retry, 'enabled', False),
        'tries': _get(retry, 'tries', 3),
        'backoff': _get(retry, 'backoff', 3.0),
        'initial_sleep': _get(retry, 'initial_sleep', 5)
    }


def get_plan_storage(config):
    storage = _get(config, 'storage', {})
    return _get(storage, 'plans', {'method': 'terrateam'})
