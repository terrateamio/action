import argparse
import json
import logging
import os
import subprocess

import repo_config
import run_state
import work_apply
import work_exec
import work_manifest
import work_plan
import work_unsafe_apply
import github_actions.run_time


DEFAULT_API_BASE_URL = 'https://app.terrateam.io'

REPO_CONFIG_PATHS = [
    os.path.join('.terrateam', 'config.yml'),
    os.path.join('.terrateam', 'config.yaml')
]


WORK_MANIFEST_DISPATCH = {
    'plan': work_plan.Exec,
    'apply': work_apply.Exec,
    'unsafe-apply': work_unsafe_apply.Exec,
}


BANNER = r"""
 ____  _____    _    ____
|  _ \| ____|  / \  |  _ \
| |_) |  _|   / _ \ | | | |
|  _ <| |___ / ___ \| |_| |
|_| \_\_____/_/   \_\____/

 __  __ _____
|  \/  | ____|
| |\/| |  _|
| |  | | |___
|_|  |_|_____|
"""


def make_parser():
    parser = argparse.ArgumentParser(description='Terrateam Runner')
    parser.add_argument('--work-token',
                        required=True,
                        help='Work token')
    parser.add_argument('--workspace',
                        required=True,
                        help='Path to workspace')
    parser.add_argument('--api-base-url',
                        default=DEFAULT_API_BASE_URL,
                        help='Base URL for API')
    parser.add_argument('--run-id',
                        required=True,
                        help='Github Action run id')
    parser.add_argument('--sha',
                        required=True,
                        help='SHA of the checkout being run on')

    return parser


# If an environment variable SECRETS_CONTEXT is specified, then expand this out
# into the actual environment.  This value is assumed to be JSON encoding
# key-value pairs of secrets.  If it does not successfully decode from JSON, the
# value is ignored.
def set_secrets_context(env):
    secrets_context = env.get('SECRETS_CONTEXT')

    if secrets_context is not None:
        try:
            secrets = json.loads(secrets_context)

            for k, v in secrets.items():
                env[k] = str(v)
        except json.decoder.JSONDecodeError as exn:
            logging.error('Failed to decode SECRETS_CONTEXT')
            logging.exception(exn)


# Iterate the environment and convert any environment variables starting with
# TF_VAR_ to TF_VAR_<lower case>.  If the lower-case name already exists in env,
# do nothing.
def transform_tf_vars(env):
    new_keys = {}
    for k, v in env.items():
        if k.startswith('TF_VAR_') and k != 'TF_VAR_':
            # Get the name
            name = k.split('_', 2)[2]
            # Create a new env variable with the lower version name
            new_name = 'TF_VAR_{}'.format(name.lower())
            if new_name not in env:
                new_keys[new_name] = v

    env.update(new_keys)


def maybe_setup_cdktf(rc, work_manifest, env):
    # Determine if any workflows use cdktf and only install it if it is
    # required.
    cdktf_used = False
    for d in work_manifest['changed_dirspaces']:
        if 'workflow' in d:
            workflow = repo_config.get_workflow(rc, d['workflow'])
            cdktf_used = cdktf_used or workflow['cdktf']

    if cdktf_used:
        subprocess.check_call(['/cdktf-setup.sh'])
        env['PATH'] = env['PATH'] + ':' + os.path.join(env['TERRATEAM_ROOT'], 'node_modules', '.bin')


def perform_merge(working_dir, base_ref):
    current_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                             cwd=working_dir).decode('utf-8').strip()
    subprocess.check_call(['git', 'fetch', '--depth=1', 'origin', base_ref])
    for i in range(100):
        try:
            subprocess.check_output(['git', 'merge', '--no-edit', 'origin/' + base_ref],
                                    stderr=subprocess.STDOUT)
            return
        except subprocess.CalledProcessError as exn:
            logging.info('%s', exn.output.decode('utf-8'))
            if 'not something we can merge' in exn.output.decode('utf-8') \
               or 'refusing to merge unrelated histories' in exn.output.decode('utf-8'):
                logging.debug('MERGE : DEEPENING')
                subprocess.check_call(['git', 'fetch', '--deepen=100', 'origin', '+' + current_commit])
            else:
                raise

    raise Exception('Could not merge destination branch')


def main():
    logging.basicConfig(level=logging.DEBUG)

    print(BANNER)
    print('*** These are not the logs you are looking for ***')
    print('***')
    print('*** The output of the action is not meant for debugging purposes ***')
    print('*** If you are reading this to debug an issue please: ***')
    print('- Join our Slack community https://slack.terrateam.io/ (Fastest)')
    print('- Email us directly at support@terrateam.io')
    print('***')
    print('***')

    parser = make_parser()
    args = parser.parse_args()

    if not args.api_base_url:
        args.api_base_url = DEFAULT_API_BASE_URL

    if args.api_base_url[-1] == '/':
        # Remove trailing '/'
        args.api_base_url = args.api_base_url[:-1]

    logging.debug('LOADING : WORK_MANIFEST')
    wm = work_manifest.get(args.api_base_url, args.work_token, args.run_id, args.sha)

    # We only support a merge-based evaluation.  We must perform the merge first
    # because we load the repo config next and we want it to be the merged
    # version.
    subprocess.check_call(['git', 'config', '--global', '--add', 'safe.directory', args.workspace])
    subprocess.check_call(['git', 'config', '--global', 'user.email', 'hello@terrateam.com'])
    subprocess.check_call(['git', 'config', '--global', 'user.name', 'Terrateam Action'])
    subprocess.check_call(['git', 'config', '--global', 'advice.detachedHead', 'false'])
    perform_merge(args.workspace, wm['base_ref'])

    logging.debug('LOADING: REPO_CONFIG')
    rc = repo_config.load([os.path.join(args.workspace, path) for path in REPO_CONFIG_PATHS])

    run_time = github_actions.run_time.Run_time()

    run_time.set_secret(wm['token'])

    state = run_state.create(
        args.work_token,
        wm['token'],
        rc,
        args.workspace,
        args.api_base_url,
        wm,
        args.sha,
        run_time)

    state = run_time.initialize(state)

    env = state.env.copy()
    # Setup Terraform environment variables for automation
    env['TF_IN_AUTOMATION'] = 'true'
    env['TF_INPUT'] = 'false'

    # Setup Terrateam environment variables
    env['TERRATEAM_ROOT'] = state.working_dir
    env['TERRATEAM_RUN_KIND'] = wm.get('run_kind', '')

    maybe_setup_cdktf(rc, wm, env)
    set_secrets_context(env)
    transform_tf_vars(env)
    state = state._replace(env=env)

    logging.debug('EXEC : %s', wm['type'])
    work_exec.run(state, WORK_MANIFEST_DISPATCH[wm['type']]())


if __name__ == '__main__':
    main()
