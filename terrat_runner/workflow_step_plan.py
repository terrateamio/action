import json
import logging
import os
import subprocess
import tempfile

import infracost
import repo_config as rc
import workflow_step_terraform


def _exec_infracost(state):
    with tempfile.TemporaryDirectory() as tmpdir:
        show_plan_path = os.path.join(tmpdir, 'plan.json')
        (failed, state) = workflow_step_terraform.run(
            state,
            {
                'args': ['show', '-json', '$TERRATEAM_PLAN_FILE'],
                'output_key': 'plan_json'
            })

        if not failed:
            plan_json = state.output.pop('plan_json')

            with open(show_plan_path, 'w') as f:
                f.write(plan_json)

            breakdown_path = os.path.join(tmpdir, 'infracost-breakdown.json')

            try:
                output = subprocess.check_output(['infracost',
                                                  'breakdown',
                                                  '--path={}'.format(show_plan_path),
                                                  '--format=json',
                                                  '--out-file={}'.format(breakdown_path)],
                                                 stderr=subprocess.STDOUT)

                output = output.decode('utf-8')

                if 'level=error' in output:
                    state.output.setdefault('errors', []).append(output)
                    failed = True
                else:
                    with open(breakdown_path) as f:
                        breakdown = json.load(f)

                    state.output['cost_estimation'] = {
                        'prev_monthly_cost': infracost.convert_cost(breakdown['pastTotalMonthlyCost']),
                        'total_monthly_cost': infracost.convert_cost(breakdown['totalMonthlyCost']),
                        'diff_monthly_cost': infracost.convert_cost(breakdown['diffTotalMonthlyCost']),
                        'currency': breakdown['currency']
                    }
            except subprocess.CalledProcessError as exn:
                logging.exception(exn)
                state.output.setdefault('errors', []).append(exn.output.decode('utf-8'))
                failed = True
            except Exception as exn:
                logging.exception(exn)
                state.output.setdefault('errors', []).append(str(exn))
                failed = True

        return (failed, state)


def _exec_cost_estimation(state, cost_estimation):
    if cost_estimation['provider'] == 'infracost':
        return _exec_infracost(state)
    else:
        raise Exception('Unknown cost estimation provider')


def run(state, config):
    config = config.copy()
    config['args'] = ['plan', '-out', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'plan'
    (failed, state) = workflow_step_terraform.run(state, config)

    if failed:
        return (failed, state)

    # Grab just the plan output.  If running the plan succeded, we want to just
    # show the plan text.  If it failed above, we want to be able to show the
    # user the entire terminal output.
    config['args'] = ['show', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'plan_text'

    (failed, state) = workflow_step_terraform.run(state, config)

    if failed:
        return (failed, state)

    cost_estimation = rc.get_cost_estimation(state.repo_config)
    if cost_estimation['enabled']:
        (failed, state) = _exec_cost_estimation(state, cost_estimation)

    return (failed, state)
