import os
import yaml


def load(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return yaml.safe_load(f.read())
    else:
        return {}


def default_plan_workflow():
    return [
        {'type': 'init'},
        {'type': 'plan'}
    ]


def default_apply_workflow():
    return [
        {'type': 'init'},
        {'type': 'apply'}
    ]


def get_plan_hooks(repo_config):
    hooks = repo_config.get('hooks', {})
    return hooks.get('plan', {'pre': [], 'post': []})


def get_apply_hooks(repo_config):
    hooks = repo_config.get('hooks', {})
    return hooks.get('apply', {'pre': [], 'post': []})


def get_plan_workflow(repo_config, idx):
    return repo_config['workflows'][idx].get('plan', default_plan_workflow())


def get_apply_workflow(repo_config, idx):
    return repo_config['workflows'][idx].get('apply', default_apply_workflow())


def get_workflow(repo_config, idx):
    workflow = repo_config['workflows'][idx]
    return {
        'terragrunt': workflow.get('terragrunt', False),
        'terraform_version': workflow.get('terraform_version', get_default_tf_version(repo_config)),
        'plan': workflow.get('plan', default_plan_workflow()),
        'apply': workflow.get('apply', default_apply_workflow)
    }


def get_default_workflow(repo_config):
    return {
        'terragrunt': False,
        'terraform_version': get_default_tf_version(repo_config),
        'plan': default_plan_workflow(),
        'apply': default_apply_workflow()
    }


def get_checkout_strategy(repo_config):
    return repo_config.get('checkout_strategy', 'merge')


def get_default_tf_version(repo_config):
    return repo_config.get('default_tf_version', 'latest')


def get_parallelism(repo_config):
    return repo_config.get('parallel_runs', 3)


def get_create_and_select_workspace(repo_config, path):
    dirs = repo_config.get('dirs')
    if dirs is None:
        dirs = {}
    return dirs.get(path, {}).get('create_and_select_workspace', True)
