# A workflow step is an individual operation.  It can have a number of types
# which each take their own configuration parameters.
import logging

import workflow_step_apply
import workflow_step_checkout_strategy
import workflow_step_env
import workflow_step_infracost_setup
import workflow_step_init
import workflow_step_plan
import workflow_step_run


STEPS = {
    'apply': workflow_step_apply.run,
    'checkout': workflow_step_checkout_strategy.run,
    'env': workflow_step_env.run,
    'infracost_setup': workflow_step_infracost_setup.run,
    'init': workflow_step_init.run,
    'plan': workflow_step_plan.run,
    'run': workflow_step_run.run,
}


def run_steps(state, steps, restrict_types=None):
    for step in steps:
        if 'type' not in step:
            raise Exception('Step must contain a type')
        elif step['type'] not in STEPS:
            raise Exception('Step type {} is unknown'.format(step['type']))
        elif restrict_types and step['type'] not in restrict_types:
            raise Exception('Step type {} not allowed in this mode'.format(step['type']))
        else:
            try:
                (failed, state) = STEPS[step['type']](state, step)
            except Exception as exn:
                logging.exception(exn)
                logging.error('STEP : FAIL : %r', step)
                failed = True

            if failed:
                logging.error('STEP : FAIL : %r', step)
                state = state._replace(failed=True)

    return state
