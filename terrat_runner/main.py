import argparse
import json
import logging
import os
import subprocess

import repo_config
import run_state

import work_apply
import work_build_config
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


def maybe_setup_cdktf(rc, work_manifest, env):
    # Determine if any engine uses cdktf and only install it if it is required.
    cdktf_used = False
    for d in work_manifest['changed_dirspaces']:
        if 'workflow' in d:
            workflow = repo_config.get_workflow(rc, d['workflow'])
            cdktf_used = cdktf_used or workflow['engine']['name'] == 'cdktf'

    if cdktf_used:
        subprocess.check_call(['/cdktf-setup.sh'])
        env['PATH'] = env['PATH'] + ':' + os.path.join(env['TERRATEAM_ROOT'], 'node_modules', '.bin')


def tf_operation(state, op):
    perform_merge(state.working_dir, state.work_manifest['base_ref'])
    maybe_setup_cdktf(state.repo_config, state.work_manifest, state.env)
    work_exec.run(state, op)


WORK_MANIFEST_DISPATCH = {
    'plan': lambda state: tf_operation(state, work_plan.Exec()),
    'apply': lambda state: tf_operation(state, work_apply.Exec()),
    'unsafe-apply': lambda state: tf_operation(state, work_unsafe_apply.Exec()),
    'index': lambda state: state.run_time.work_index(state),
    'build-config': lambda state: work_build_config.run(state)
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

ERROR_BANNER = r"""
 _____ ____  ____   ___  ____
| ____|  _ \|  _ \ / _ \|  _ \
|  _| | |_) | |_) | | | | |_) |
| |___|  _ <|  _ <| |_| |  _ <
|_____|_| \_\_| \_\\___/|_| \_\
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


def set_env_context(env, context):
    try:
        vals = json.loads(context)

        if vals:
            for k, v in vals.items():
                env[k] = str(v)
    except json.decoder.JSONDecodeError as exn:
        logging.error('Failed to decode {}'.format(context))
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


def run(args):
    logging.debug('LOADING : WORK_MANIFEST')

    try:
        wm = work_manifest.get(args.api_base_url, args.work_token, args.run_id, args.sha)
    except work_manifest.NoWorkManifestError:
        print(ERROR_BANNER)
        print('*** The work manifest was not found ***')
        print('***')
        print('*** The most likely cause of this is the GitHub Action Workflow ***')
        print('*** is being run manually ***')
        print('***')
        print('*** This is not supported by Terrateam.  All runs must be initiated ***')
        print('*** by an operation in a pull request ***')
        print('***')
        print('*** If this error persists, reach out to us in our Slack: https://slack.terrateam.io/ ***')
        print('*** or email us directly at support@terrateam.io ***')
        raise

    # If it's a "done" work manifest, then bail
    if wm['type'] == 'done':
        logging.info('Work manifest is completed, exiting.')
        return True

    logging.debug('LOADING: REPO_CONFIG')
    rc = wm['config']

    run_time = github_actions.run_time.Run_time()

    run_time.group_output('Repository Configuration', json.dumps(rc, indent=2))

    run_time.set_secret(wm['token'])

    result_version = wm.get('result_version', 1)

    state = run_state.create(
        api_base_url=args.api_base_url,
        api_token=wm['token'],
        repo_config=rc,
        run_time=run_time,
        sha=args.sha,
        work_manifest=wm,
        work_token=args.work_token,
        working_dir=args.workspace,
        result_version=result_version
    )

    state = run_time.initialize(state)

    state = run_state.set_secret(state, wm['token'])

    env = state.env.copy()
    # Setup Terraform environment variables for automation
    env['TF_IN_AUTOMATION'] = 'true'
    env['TF_INPUT'] = 'false'

    # Setup Terrateam environment variables
    env['TERRATEAM_ROOT'] = state.working_dir
    env['TERRATEAM_RUN_KIND'] = wm.get('run_kind', '')

    secret_env = {}
    set_env_context(secret_env, env.get('SECRETS_CONTEXT', '{}'))
    for k, v in secret_env.items():
        state = run_state.set_secret(state, v)
        env[k] = v

    set_env_context(env, env.get('VARIABLES_CONTEXT', '{}'))
    set_env_context(env, env.get('ENVIRONMENT_CONTEXT', '{}'))
    transform_tf_vars(env)
    state = state._replace(env=env)

    logging.debug('RESULT_VERSION : %r', result_version)
    logging.debug('EXEC : %s', wm['type'])
    WORK_MANIFEST_DISPATCH[wm['type']](state)

    return False


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

    # We only support a merge-based evaluation.  We must perform the merge first
    # because we load the repo config next and we want it to be the merged
    # version.
    subprocess.check_call(['git', 'config', '--global', '--add', 'safe.directory', args.workspace])
    subprocess.check_call(['git', 'config', '--global', 'user.email', 'hello@terrateam.com'])
    subprocess.check_call(['git', 'config', '--global', 'user.name', 'Terrateam Action'])
    subprocess.check_call(['git', 'config', '--global', 'advice.detachedHead', 'false'])

    done = False
    run_count = 0

    while not done:
        done = run(args)
        run_count += 1
        if run_count > 10:
            print('*** Performed too many work manifests, exiting to prevent unexpected loop')
            break

    # This means we only did one run, which is that we got the "done" work
    # manifest.
    if run_count == 1:
        print('*** It looks like the work manifest was completed before this started ***')
        print('*** Manual re-runs are not supported ***')
        print('*** Please create a run through the Terrateam interface ***')


if __name__ == '__main__':
    main()
