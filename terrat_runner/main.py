import argparse
import json
import logging
import os
import subprocess

import repo_config
import run_state

import work_apply
import work_build_config
import work_build_tree
import work_exec
import work_manifest
import work_plan
import work_unsafe_apply

from runtime.github_actions import runtime as github_actions
from runtime.gitlab_ci import runtime as gitlab_ci

DEFAULT_API_BASE_URL = 'https://app.terrateam.io'


def set_env_context(env, context):
    try:
        vals = json.loads(context)

        if vals:
            for k, v in vals.items():
                env[k] = str(v)
    except json.decoder.JSONDecodeError as exn:
        logging.error('Failed to decode {}'.format(context))
        logging.exception(exn)


def install_ca_bundles():
    env = os.environ.copy()
    set_env_context(env, env.get('SECRETS_CONTEXT', '{}'))
    set_env_context(env, env.get('VARIABLES_CONTEXT', '{}'))
    set_env_context(env, env.get('ENVIRONMENT_CONTEXT', '{}'))

    bundles = []
    for k, v in env.items():
        if k.startswith('CUSTOM_CA_BUNDLE_'):
            logging.info('CUSTOM_CA_BUNDLES : %s : FOUND', k)
            if v.strip():
                bundles.append((k, v))
            else:
                logging.info('CUSTOM_CA_BUNDLES : %s : EMPTY', k)

    for k, v in bundles:
        path = os.path.join('/usr/local/share/ca-certificates', '{}.crt'.format(k))
        logging.info('CUSTOM_CA_BUNDLES : %s : CREATING : %s', k, path)

        with open(path, 'w') as f:
            f.write(v)

    if bundles:
        logging.info('CUSTOM_CA_BUNDLES : UPDATING')
        subprocess.check_call(['update-ca-certificates'])


def perform_merge(working_dir, base_ref):
    current_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                             cwd=working_dir).decode('utf-8').strip()
    logging.debug('current commit=%s : fetching base ref', current_commit)
    try:
        logging.info('%r',
                     ['git',
                      'fetch',
                      '--depth=1',
                      'origin',
                      base_ref + ':refs/remotes/origin/' + base_ref])
        print(subprocess.check_output(['git',
                                       'fetch',
                                       '--depth=1',
                                       'origin',
                                       base_ref + ':refs/remotes/origin/' + base_ref],
                                      stderr=subprocess.STDOUT))
    except subprocess.CalledProcessError as exn:
        logging.info('%s', exn.output.decode('utf-8'))
        # If it is because a merge happened between the time we started running
        # and we ran, just ignore it and use whatever we checked out as main
        if 'rejected' in exn.output.decode('utf-8') \
           and 'non-fast-forward' in exn.output.decode('utf-8'):
            return
        else:
            raise

    for i in range(100):
        try:
            logging.info('%r', ['git', 'merge', '--no-edit', 'origin/' + base_ref])
            print(subprocess.check_output(['git', 'merge', '--no-edit', 'origin/' + base_ref],
                                          stderr=subprocess.STDOUT))
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

def ensure_merged(state, f):
    perform_merge(state.working_dir, state.work_manifest['base_ref'])
    f(state)


WORK_MANIFEST_DISPATCH = {
    'plan': lambda state: tf_operation(state, work_plan.Exec()),
    'apply': lambda state: tf_operation(state, work_apply.Exec()),
    'unsafe-apply': lambda state: tf_operation(state, work_unsafe_apply.Exec()),
    'index': lambda state: state.runtime.work_index(state),
    'build-config': lambda state: ensure_merged(state, work_build_config.run),
    'build-tree': lambda state: ensure_merged(state, work_build_tree.run),
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
    parser.add_argument('--runtime',
                        default='github',
                        choices=['github', 'gitlab'],
                        help='Which runtime to use')

    return parser


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

    if args.runtime == 'github':
        logging.info('Starting GitHub runtime')
        runtime = github_actions.Runtime()
        runtime.group_output('Repository Configuration', json.dumps(rc, indent=2))
        runtime.set_secret(wm['token'])
    elif args.runtime == 'gitlab':
        logging.info('Starting GitLab runtime')
        runtime = gitlab_ci.Runtime()
        runtime.group_output('Repository Configuration', json.dumps(rc, indent=2))
        runtime.set_secret(wm['token'])
    else:
        raise Exception('Unknown runtime: {}'.format(args.runtime))

    result_version = wm.get('result_version', 1)

    state = run_state.create(
        api_base_url=args.api_base_url,
        api_token=wm['token'],
        repo_config=rc,
        runtime=runtime,
        sha=args.sha,
        work_manifest=wm,
        work_token=args.work_token,
        working_dir=args.workspace,
        result_version=result_version
    )

    state = runtime.initialize(state)

    state = run_state.set_secret(state, wm['token'])

    env = state.env.copy()
    # Setup Terraform environment variables for automation
    env['TF_IN_AUTOMATION'] = 'true'
    env['TF_INPUT'] = 'false'
    env['TERRAGRUNT_NON_INTERACTIVE'] = 'true'

    # Setup Terrateam environment variables
    env['TERRATEAM_ROOT'] = state.working_dir
    env['TERRATEAM_RUN_KIND'] = wm.get('run_kind', '')
    env['TERRATEAM_RUN_KIND_DATA'] = json.dumps(wm.get('run_kind_data', {}))

    # Set log level to error because when we run things in parallel,
    # sometimes the logging around the lockfile breaks parsing underlying
    # commands (for example terragrunt getting tofu version)
    env['TENV_LOG'] = 'error'

    if 'tenv' in wm.get('capabilities', []):
        # If the server supports tenv, then we can use it for various list and
        # remote operations.  This gets around the limitation in http request
        # rate limiting.
        logging.info('CONFIGURING FOR TENV SERVER SUPPORT')
        env['TOFUENV_LIST_MODE'] = 'direct'
        env['TG_LIST_MODE'] = 'direct'
        env['TOFUENV_LIST_URL'] = state.api_base_url + '/tenv/' + state.work_token + '/opentofu/opentofu/releases'
        env['TG_LIST_URL'] = state.api_base_url + '/tenv/' + state.work_token + '/gruntwork-io/terragrunt/releases'
        env['TOFUENV_REMOTE'] = state.api_base_url + '/tenv/' + state.work_token
        env['TG_REMOTE'] = state.api_base_url + '/tenv/' + state.work_token

    secret_env = {}
    set_env_context(secret_env, env.get('SECRETS_CONTEXT', '{}'))
    for k, v in secret_env.items():
        state = run_state.set_secret(state, v)
        env[k] = v

    set_env_context(env, env.get('VARIABLES_CONTEXT', '{}'))
    set_env_context(env, env.get('ENVIRONMENT_CONTEXT', '{}'))

    # Move this to run-time
    for k, v in env.items():
        if k.lower() == 'github_token':
            env['TENV_GITHUB_TOKEN'] = env[k]
            env['GITHUB_TOKEN'] = env[k]
            break

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

    logging.info('CUSTOM_CA_BUNDLES : INSTALLING')
    install_ca_bundles()

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
