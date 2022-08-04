import json
import logging
import os

import infracost
import repo_config as rc
import workflow_step_terraform


def _exec_infracost(state):
    infracost_dir = os.path.join(state.tmpdir, 'infracost')
    diff_infracost = os.path.join(infracost_dir, 'infracost-diff.json')

    if os.path.exists(diff_infracost):
        with open(diff_infracost) as f:
            diff = json.load(f)

        p = [p for p in diff['projects']
             if (p['metadata']['path'] == state.path and
                 p['metadata']['terraformWorkspace'] == state.workspace)]

        if p:
            p = p[0]
            state.output['cost_estimation'] = {
                'prev_monthly_cost': infracost.convert_cost(p['pastBreakdown']['totalMonthlyCost']),
                'total_monthly_cost': infracost.convert_cost(p['breakdown']['totalMonthlyCost']),
                'diff_monthly_cost': infracost.convert_cost(p['diff']['totalMonthlyCost']),
                'currency': diff['currency']
            }
        else:
            logging.warn('INFRACOST : %s : %s : ERROR_MISSING_DIRSPACE_IN_YAML',
                         state.path,
                         state.workspace)
    else:
        logging.warn('INFRACOST : %s : %s : ERROR_MISSING_DIFF_FILE', state.path, state.workspace)


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
        _exec_cost_estimation(state, cost_estimation)

    return (failed, state)
