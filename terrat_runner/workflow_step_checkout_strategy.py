import logging
import subprocess

import repo_config


def perform_merge(git_workspace, base_ref, head_ref):
    subprocess.check_call(['git', 'config', '--global', '--add', 'safe.directory', git_workspace])
    subprocess.check_call(['git', 'config', '--global', 'user.email', 'hello@terrateam.com'])
    subprocess.check_call(['git', 'config', '--global', 'user.name', 'Terrateam Action'])
    subprocess.check_call(['git', 'config', '--global', 'advice.detachedHead', 'false'])
    subprocess.check_call(['git', 'branch'], cwd=git_workspace)
    subprocess.check_call(['git', 'checkout', base_ref], cwd=git_workspace)
    subprocess.check_call(['git', 'merge', '--no-commit', head_ref], cwd=git_workspace)


def run(state, config):
    checkout_strategy = repo_config.get_checkout_strategy(state.repo_config)
    logging.debug('CHECKOUT_STRATEGY : %s', checkout_strategy)
    if checkout_strategy == 'merge':
        try:
            perform_merge(state.working_dir, state.work_manifest['base_ref'], state.sha)
        except subprocess.CalledProcessError:
            # TODO Handle
            raise
    else:
        subprocess.check_call(['git', 'checkout', state.sha], cwd=state.working_dir)

    return (False, state)
