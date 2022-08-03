import json
import logging
import os
import subprocess

import infracost


def run(state, config):
    infracost_dir = os.path.join(state.tmpdir, 'infracost')
    os.makedirs(infracost_dir, exist_ok=True)

    prev_infracost = os.path.join(infracost_dir, 'infracost-prev.json')
    curr_infracost = os.path.join(infracost_dir, 'infracost.json')
    diff_infracost = os.path.join(infracost_dir, 'infracost-diff.json')
    infracost_config_yml = os.path.join(infracost_dir, 'config.yml')

    infracost.create_infracost_yml(infracost_config_yml, state.work_manifest['dirspaces'])

    try:
        output = subprocess.check_output(['infracost',
                                          'breakdown',
                                          '--config-file={}'.format(infracost_config_yml),
                                          '--format=json',
                                          '--out-file={}'.format(curr_infracost)],
                                         cwd=state.working_dir,
                                         stderr=subprocess.STDOUT)
        output = output.decode('utf-8')

        for line in output.splitlines():
            logging.info('INFRACOST : SETUP : %s', line)

        diff_output = subprocess.check_output(['infracost',
                                               'diff',
                                               '--format=json',
                                               '--path={}'.format(curr_infracost),
                                               '--compare-to={}'.format(prev_infracost),
                                               '--out-file={}'.format(diff_infracost)],
                                              stderr=subprocess.STDOUT)

        diff_output = diff_output.decode('utf-8')

        for line in diff_output.splitlines():
            logging.info('INFRACOST : SETUP : %s', line)

        if 'level=error' not in output:
            with open(diff_infracost) as f:
                diff = json.load(f)

            state.output['cost_estimation'] = {
                'prev_monthly_cost': infracost.convert_cost(diff['pastTotalMonthlyCost']),
                'total_monthly_cost': infracost.convert_cost(diff['totalMonthlyCost']),
                'diff_monthly_cost': infracost.convert_cost(diff['diffTotalMonthlyCost']),
                'currency': diff['currency'],
            }

    except subprocess.CalledProcessError as exn:
        logging.exception('INFRACOST : ERROR')
        logging.error('%s', exn.stdout)

    return (False, state)
