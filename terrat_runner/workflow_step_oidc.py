import logging
import os

import requests_retry
import workflow


DEFAULT_AWS_AUDIENCE = 'sts.amazonaws.com'

REQUEST_URL_VAR = 'ACTIONS_ID_TOKEN_REQUEST_URL'
REQUEST_TOKEN_VAR = 'ACTIONS_ID_TOKEN_REQUEST_TOKEN'


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
        env = state.env.copy()
        env['AWS_ROLE_ARN'] = role_arn
        env['AWS_WEB_IDENTITY_TOKEN_FILE'] = os.path.join(state.tmpdir, 'oidc_token_file')
        state = state._replace(env=env)
        with open(env['AWS_WEB_IDENTITY_TOKEN_FILE'], 'w') as f:
            f.write(res.json()['value'])

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
