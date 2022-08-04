import logging
import os
import subprocess

import infracost


INFRACOST_API_KEY = 'INFRACOST_API_KEY'
INFRACOST_CURRENCY = 'INFRACOST_CURRENCY'


def checkout_base(state):
    subprocess.check_call(['git', 'config', '--global', '--add', 'safe.directory', state.working_dir])
    subprocess.check_call(['git', 'config', '--global', 'advice.detachedHead', 'false'])
    subprocess.check_call(['git', 'branch'], cwd=state.working_dir)
    subprocess.check_call(['git', 'checkout', state.work_manifest['base_ref'], '--'],
                          cwd=state.working_dir)


def configure_infracost(state, config):
    env = state.env
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


def run(state, config):
    try:
        checkout_base(state)

        logging.info('INFRACOST : SETUP')
        configure_infracost(state, config)

        infracost_dir = os.path.join(state.tmpdir, 'infracost')
        os.makedirs(infracost_dir, exist_ok=True)

        prev_infracost = os.path.join(infracost_dir, 'infracost-prev.json')
        infracost_config_yml = os.path.join(infracost_dir, 'config.yml')

        infracost.create_infracost_yml(infracost_config_yml, state.work_manifest['base_dirspaces'])

        output = subprocess.check_output(['infracost',
                                          'breakdown',
                                          '--config-file={}'.format(infracost_config_yml),
                                          '--format=json',
                                          '--out-file={}'.format(prev_infracost)],
                                         cwd=state.working_dir,
                                         stderr=subprocess.STDOUT)

        output = output.decode('utf-8')

        for line in output.splitlines():
            logging.info('INFRACOST : SETUP : %s', line)

    except subprocess.CalledProcessError as exn:
        logging.error('%s', exn.stdout)
        raise exn

    return (False, state)
