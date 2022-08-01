import json
import logging
import os
import subprocess

import infracost


INFRACOST_API_KEY = 'INFRACOST_API_KEY'
INFRACOST_CURRENCY = 'INFRACOST_CURRENCY'


def run(state, config):
    failed = False
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

    infracost_dir = os.path.join(state.tmpdir, 'infracost')
    os.makedirs(infracost_dir, exist_ok=True)

    total_monthly_cost = 0.0

    for dirspace in state.work_manifest['dirspaces']:
        path = dirspace['path']
        workspace = dirspace['workspace']

        logging.info('INFRACOST : SETUP : %s', path)

        outname = os.path.join(state.tmpdir, infracost.json_filename_of_dirspace(dirspace))

        output = subprocess.check_output(['infracost',
                                          'breakdown',
                                          '--path={}'.format(os.path.join(state.working_dir, path)),
                                          '--terraform-workspace={}'.format(workspace),
                                          '--format=json',
                                          '--out-file={}'.format(outname)],
                                         stderr=subprocess.STDOUT)

        output = output.decode('utf-8')

        for line in output.splitlines():
            logging.info('INFRACOST : SETUP : %s : %s', path, line)

        if 'level=error' in output:
            state.output.setdefault('errors', []).append(output)
            failed = True
            break
        else:
            with open(outname) as f:
                breakdown = json.load(f)

            total_monthly_cost += infracost.convert_cost(breakdown['totalMonthlyCost'])

    state.output['cost_estimation'] = {
        'total_monthly_cost': total_monthly_cost,
        'currency': config['currency']
    }

    return (failed, state)
