import logging
import subprocess


INFRACOST_API_KEY = 'INFRACOST_API_KEY'
INFRACOST_CURRENCY = 'INFRACOST_CURRENCY'


def run(state, config):
    env = state.env

    logging.info('INFRACOST : SETUP')
    if INFRACOST_API_KEY in env:
        logging.info('INFRACOST : SETUP : PUBLIC_ENDPOINT')
        subprocess.check_call(['infracost',
                               'configure',
                               'set',
                               'api_key',
                               env[INFRACOST_API_KEY].strip()])
    else:
        logging.info('INFRACOST : SETUP : SELF_HOSTED_ENDPOINT')
        subprocess.check_call(['infracost',
                               'configure',
                               'set',
                               'pricing_api_endpoint',
                               state.api_base_url + '/infracost'])
        subprocess.check_call(['infracost',
                               'configure',
                               'set',
                               'api_key',
                               state.work_token])

    subprocess.check_call(['infracost',
                           'configure',
                           'set',
                           'currency',
                           env.get(INFRACOST_CURRENCY, config['currency'])])

    return (False, state)
