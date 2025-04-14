import os
import yaml


def _get(d, k, default):
    """Return [default] if it is not set or set to None."""
    v = d.get(k, default)
    if v is None:
        return default
    else:
        return v


def load(paths):
    for path in paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
                if content.strip():
                    return yaml.safe_load(content)
                else:
                    return {}

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


def _get_integrations(repo_config, workflow_integrations):
    global_integrations = _get(repo_config, 'integrations', {})
    resourcely = _get(workflow_integrations,
                      'resourcely',
                      _get(global_integrations, 'resourcely', {}))
    return {
        'resourcely': {
            'enabled': _get(resourcely, 'enabled', False),
            'extra_args': _get(resourcely, 'extra_args', [])
        }
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


def get_engine(repo_config):
    # Get the engine config.  If one is already there, we will take it verbatim,
    # however if we need to construct a default one, we specify terraform and we
    # also want to use the [default_tf_version] if present.  This is to maintain
    # compatibility with existing configurations.
    if 'engine' in repo_config:
        engine = repo_config['engine'].copy()
        if engine['name'] in ['cdktf', 'terragrunt'] and 'tf_cmd' not in engine:
            engine['tf_cmd'] = 'terraform'

        return engine
    else:
        return {
            'name': 'terraform',
            'version': repo_config.get('default_tf_version')
        }


def get_workflow(repo_config, idx):
    workflow = repo_config['workflows'][idx]
    cfg = {
        'apply': workflow.get('apply', _default_apply_workflow()),
        'plan': workflow.get('plan', _default_plan_workflow()),
        'integrations': _get_integrations(repo_config, _get(workflow, 'integrations', {}))
    }

    default_engine = get_engine(repo_config)
    engine = _get(workflow, 'engine', {}).copy()

    # In order to maintain backwards compatibility, we need to do some work to
    # transform an existing workflow configuration to one with an engine.
    # Additionally, we want to make future lookups easy so we fill in the
    # configurations that would be inferred.
    if 'engine' not in workflow:
        # If no engine is specified, convert any legacy configuration to the
        # engine config.  Fill in the minimal configuration and the rest will be
        # done next.
        if workflow.get('terragrunt'):
            engine = {
                'name': 'terragrunt',
            }
        elif workflow.get('cdktf'):
            engine = {
                'name': 'cdktf',
            }
        elif workflow.get('terraform_version'):
            engine = {
                'name': 'terraform',
                'version': workflow['terraform_version']
            }
        else:
            engine = default_engine.copy()

    if default_engine['name'] == 'tofu':
        default_tf_cmd = 'tofu'
        default_tf_version = default_engine.get('version')
    else:
        default_tf_cmd = 'terraform'
        default_tf_version = None

    if engine['name'] in ['terragrunt', 'cdktf']:
        engine['tf_cmd'] = _get(engine, 'tf_cmd',  default_tf_cmd)
        if engine['tf_cmd'] == 'terraform':
            engine['tf_version'] = _get(engine, 'tf_version', get_default_tf_version(repo_config))
        else:
            engine['tf_version'] = _get(engine, 'tf_version', default_tf_version)
    elif engine['name'] == 'terraform':
        engine['version'] = _get(engine, 'version', get_default_tf_version(repo_config))
    elif engine['name'] == 'tofu':
        engine['version'] = _get(engine, 'version', default_tf_version)
    elif engine['name'] in ['pulumi', 'custom', 'fly']:
        pass
    else:
        raise Exception('Unknown engine')

    cfg['engine'] = engine
    return cfg


def get_default_workflow(repo_config):
    return {
        'apply': _default_apply_workflow(),
        'plan': _default_plan_workflow(),
        'engine': get_engine(repo_config),
        'integrations': _get_integrations(repo_config, {})
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


def get_indexer(config):
    return _get(config, 'indexer', {'enabled': False})


def get_config_builder(config):
    return _get(config, 'config_builder', {'enabled': False})


def get_tree_builder(config):
    return _get(config, 'tree_builder', {'enabled': False})
