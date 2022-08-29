import io
import logging
import subprocess

import repo_config
import workflow


def _accum_output(output_buffer, cmd, *args, **kwargs):
    output = subprocess.check_output(cmd, *args, **kwargs)
    output = output.decode('utf-8')
    output_buffer.write(output)


def _setup_repo(output_buffer, git_workspace):
    _accum_output(output_buffer,
                  ['git', 'config', '--global', '--add', 'safe.directory', git_workspace],
                  stderr=subprocess.STDOUT)
    _accum_output(output_buffer,
                  ['git', 'config', '--global', 'user.email', 'hello@terrateam.com'],
                  stderr=subprocess.STDOUT)
    _accum_output(output_buffer,
                  ['git', 'config', '--global', 'user.name', 'Terrateam Action'],
                  stderr=subprocess.STDOUT)
    _accum_output(output_buffer,
                  ['git', 'config', '--global', 'advice.detachedHead', 'false'],
                  stderr=subprocess.STDOUT)


def _perform_merge(output_buffer, git_workspace, base_ref, head_ref):
    _accum_output(output_buffer,
                  ['git', 'branch'],
                  stderr=subprocess.STDOUT,
                  cwd=git_workspace)
    _accum_output(output_buffer,
                  ['git', 'checkout', base_ref, '--'],
                  stderr=subprocess.STDOUT,
                  cwd=git_workspace)
    _accum_output(output_buffer,
                  ['git', 'checkout', '-b', 'terrateam/main', base_ref],
                  stderr=subprocess.STDOUT,
                  cwd=git_workspace)
    _accum_output(output_buffer,
                  ['git', 'merge', '--no-commit', head_ref],
                  stderr=subprocess.STDOUT,
                  cwd=git_workspace)


def run(state, config):
    failed = False
    output = io.StringIO()

    _setup_repo(output, state.working_dir)

    checkout_strategy = repo_config.get_checkout_strategy(state.repo_config)
    logging.debug('CHECKOUT_STRATEGY : %s', checkout_strategy)
    if checkout_strategy == 'merge':
        try:
            _perform_merge(output, state.working_dir, state.work_manifest['base_ref'], state.sha)
        except subprocess.CalledProcessError as exn:
            failed = True
            output.write(exn.stdout.decode('utf-8'))
            output.write(exn.stderr.decode('utf-8'))

    return workflow.Result(failed=failed,
                           state=state,
                           workflow_step={'type': 'checkout'},
                           outputs={'text': output.getvalue()})
