# A workflow step is an individual operation.  It can have a number of types
# which each take their own configuration parameters.
import logging
import sys

import workflow

import workflow_step_apply
import workflow_step_checkov
import workflow_step_conftest
import workflow_step_env
import workflow_step_infracost_setup
import workflow_step_init
import workflow_step_oidc
import workflow_step_plan
import workflow_step_run
import workflow_step_terrateam_ssh_key_setup
import workflow_step_tf_cloud_setup
import workflow_step_unsafe_apply


RUN_ON_SUCCESS = 'success'
RUN_ON_FAILURE = 'failure'
RUN_ON_ALWAYS = 'always'


STEPS = {
    'apply': workflow_step_apply.run,
    'checkov': workflow_step_checkov.run,
    'conftest': workflow_step_conftest.run,
    'env': workflow_step_env.run,
    'infracost_setup': workflow_step_infracost_setup.run,
    'init': workflow_step_init.run,
    'oidc': workflow_step_oidc.run,
    'plan': workflow_step_plan.run,
    'run': workflow_step_run.run,
    'terrateam_ssh_key_setup': workflow_step_terrateam_ssh_key_setup.run,
    'tf_cloud_setup': workflow_step_tf_cloud_setup.run,
    'unsafe_apply': workflow_step_unsafe_apply.run,
}


def execute_on_error(state, on_error, gates):
    for e in on_error:
        if 'type' not in e:
            raise Exception('Missing "type"')
        elif e['type'] == 'gate':
            if 'token' not in e:
                raise Exception('Missing token in gate')
            else:
                gates.append({
                    'all_of': e.get('all_of', []),
                    'any_of': e.get('any_of', []),
                    'any_of_count': e.get('any_of_count', 0),
                    'token': e['token'],
                    'dir': state.env.get('TERRATEAM_DIR'),
                    'workspace': state.env.get('TERRATEAM_WORKSPACE')
                })
        else:
            raise Exception('Unknown type: {}'.format(type))


def run_steps(state, scope, steps):
    valid_steps = STEPS.copy()
    valid_steps.update(state.runtime.steps())

    results = []

    for step in steps:
        # Flush all outputs between steps
        sys.stdout.flush()
        sys.stderr.flush()
        run_on = step.get('run_on', RUN_ON_SUCCESS)

        if run_on == RUN_ON_ALWAYS \
           or (not state.success and run_on == RUN_ON_FAILURE) \
           or (state.success and run_on == RUN_ON_SUCCESS):

            if 'type' not in step:
                raise Exception('Step must contain a type')
            elif step['type'] not in valid_steps:
                raise Exception('Step type {} is unknown'.format(step['type']))
            else:
                try:
                    logging.info('STEP : RUN : %s : %r', state.working_dir, step)
                    result = valid_steps[step['type']](state, step)
                    state = result.state
                except Exception as exn:
                    logging.exception(exn)
                    logging.error('STEP : FAIL : %s : %r', state.working_dir, step)
                    # TODO: Fixme, this is not a valid result
                    result = workflow.make(payload={},
                                           state=state,
                                           step=step['type'],
                                           success=False)

                ignore_errors = step.get('ignore_errors', False)
                gates = []
                payload = result.payload
                if not result.success and 'on_error' in step:
                    try:
                        execute_on_error(state, step['on_error'], gates)
                    except Exception as exn:
                        payload = {
                            'text': 'Failed to process on_error: {}'.format(exn)
                        }
                        ignore_errors = False

                results.append({
                    'ignore_errors': ignore_errors,
                    'payload': payload,
                    'scope': scope,
                    'step': result.step,
                    'success': result.success,
                    'gates': gates
                })

                if not result.success and not ignore_errors:
                    logging.error('STEP : FAIL : %s : %r', state.working_dir, step)
                    state = state._replace(success=False)

    return state._replace(outputs=results)
