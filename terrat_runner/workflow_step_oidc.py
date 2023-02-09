import json
import logging
import os
import subprocess

import requests_retry
import retry
import workflow


TRIES = 3
INITIAL_SLEEP = 2
BACKOFF = 1.5

DEFAULT_AWS_AUDIENCE = 'sts.amazonaws.com'
DEFAULT_DURATION = 3600
DEFAULT_REGION = 'us-east-1'
DEFAULT_SESSION_NAME = 'terrateam'

REQUEST_URL_VAR = 'ACTIONS_ID_TOKEN_REQUEST_URL'
REQUEST_TOKEN_VAR = 'ACTIONS_ID_TOKEN_REQUEST_TOKEN'


def assume_role(state, config, web_identity_token):
    role_arn = config['role_arn']
    assume_role_arn = config.get('assume_role_arn', role_arn)
    duration = config.get('duration', DEFAULT_DURATION)
    session_name = config.get('session_name', DEFAULT_SESSION_NAME)

    proc = retry.run(
        lambda: subprocess.run(
            [
                'aws',
                'sts',
                'assume-role-with-web-identity',
                '--role-arn', assume_role_arn,
                '--role-session-name', session_name,
                '--web-identity-token', web_identity_token,
                '--duration-seconds', str(duration),
                '--output', 'json'
            ],
            cwd=state.working_dir,
            env=state.env,
            capture_output=True
        ),
        retry.finite_tries(TRIES, lambda ret: ret.returncode == 0),
        retry.betwixt_sleep_with_backoff(INITIAL_SLEEP, BACKOFF))

    if proc.returncode == 0:
        output = json.loads(proc.stdout.decode('utf-8'))
        env = state.env.copy()
        env['AWS_ACCESS_KEY_ID'] = output['Credentials']['AccessKeyId']
        env['AWS_SECRET_ACCESS_KEY'] = output['Credentials']['SecretAccessKey']
        env['AWS_SESSION_TOKEN'] = output['Credentials']['SessionToken']
        state = state._replace(env=env)

        return workflow.Result(failed=False,
                               state=state,
                               workflow_step={'type': 'oidc'},
                               outputs=None)
    else:
        logging.error('OIDC : %s : ERROR : %s', role_arn, output)
        return workflow.Result(failed=True,
                               state=state,
                               workflow_step={'type': 'oidc'},
                               outputs={
                                   'text': proc.stderr.decode('utf-8')
                               })


def run_aws(state, config):
    role_arn = config['role_arn']
    audience = config.get('audience', DEFAULT_AWS_AUDIENCE)

    request_url = state.env[REQUEST_URL_VAR]
    request_token = state.env[REQUEST_TOKEN_VAR]

    res = requests_retry.get(request_url,
                             headers={
                                 'authorization': 'bearer {}'.format(request_token)
                             },
                             params={
                                 'audience': audience
                             })

    if res.status_code == 200:
        logging.info('OIDC : %s : SUCCESS', role_arn)
        web_identity_token = res.json()['value']
        web_identity_token_file = os.path.join(state.tmpdir, 'oidc_token_file')
        with open(web_identity_token_file, 'w') as f:
            f.write(web_identity_token)

        region = config.get('region', DEFAULT_REGION)

        env = state.env
        env['AWS_ROLE_ARN'] = role_arn
        env['AWS_REGION'] = region
        env['AWS_WEB_IDENTITY_TOKEN_FILE'] = web_identity_token_file
        state = state._replace(env=env)
        if config.get('assume_role_enabled', True):
            logging.info('OIDC : %s : ASSUMING_ROLE', role_arn)
            return assume_role(state, config, web_identity_token)
        else:
            return workflow.Result(failed=False,
                                   state=state,
                                   workflow_step={'type': 'oidc'},
                                   outputs=None)

    else:
        logging.error('OIDC : %s : ERROR : %s',
                      role_arn,
                      res.content.decode('utf-8'))
        return workflow.Result(failed=True,
                               state=state,
                               workflow_step={'type': 'oidc'},
                               outputs={
                                   'text': res.content.decode('utf-8')
                               })


def run(state, config):
    if config.get('provider', 'aws') == 'aws':
        return run_aws(state, config)
    else:
        return workflow.Result(failed=True,
                               state=state,
                               workflow_step={'type': 'oidc'},
                               outputs={
                                   'text': 'Unknown provider: {}'.config.get('provider')
                               })
