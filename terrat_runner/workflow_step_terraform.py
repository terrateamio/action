import os
import subprocess

import repo_config
import workflow_step_run


def run(state, config):
    args = config['args']

    terraform_version = config.get('terraform_version',
                                   repo_config.get_default_tf_version(state.repo_config))

    terraform_bin_path = os.path.join('/usr', 'local', 'tf', 'versions', terraform_version, 'terraform')

    subprocess.check_call(['/install-terraform-version', terraform_version])

    env = config.get('env', {})

    if config.get('terragrunt', False):
        cmd = ['terragrunt']
        env = env.copy()
        env['TERRAGRUNT_TFPATH'] = terraform_bin_path
    else:
        cmd = [terraform_bin_path]

    extra_args = config.get('extra_args', [])
    config = {
        'cmd': cmd + args + extra_args,
        'output_key': config.get('output_key'),
        'env': env
    }
    return workflow_step_run.run(state, config)
