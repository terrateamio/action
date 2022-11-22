import argparse
import json
import logging
import os

import repo_config
import run_state
import work_apply
import work_exec
import work_manifest
import work_plan
import work_unsafe_apply


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
def set_secrets_context(state):
    secrets_context = state.env.get('SECRETS_CONTEXT')

    if secrets_context is not None:
        env = state.env.copy()
        try:
            secrets = json.loads(secrets_context)

            for k, v in secrets.items():
                env[k] = str(v)

            return state._replace(env=env)
        except json.decoder.JSONDecodeError as exn:
            logging.error('Failed to decode SECRETS_CONTEXT')
            logging.exception(exn)

    return state


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

    logging.debug('LOADING: REPO_CONFIG')
    rc = repo_config.load([os.path.join(args.workspace, path) for path in REPO_CONFIG_PATHS])
    state = run_state.create(args.work_token, rc, args.workspace, args.api_base_url, wm, args.sha)

    env = state.env.copy()
    env['TERRATEAM_ROOT'] = state.working_dir
    env['INFRACOST_PARALLELISM'] = '1'
    state = state._replace(env=env)

    state = set_secrets_context(state)

    logging.debug('EXEC : %s', wm['type'])
    work_exec.run(state, WORK_MANIFEST_DISPATCH[wm['type']]())


if __name__ == '__main__':
    main()
