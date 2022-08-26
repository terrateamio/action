import repo_config as rc
import retry
import workflow
import workflow_step_terraform


def _test_success_update_config(config):
    def _f(ret):
        if ret.failed:
            config['args'] = ['apply', '-auto-approve']
        return not ret.failed

    return _f


def run(state, config):
    config = config.copy()
    config['args'] = ['apply', '$TERRATEAM_PLAN_FILE']
    config['output_key'] = 'apply'

    retry_config = rc.get_retry(config)
    tries = retry_config['enabled'] and retry_config['tries'] or 1
    result = retry.run(
        lambda: workflow_step_terraform.run(state, config),
        retry.finite_tries(tries, _test_success_update_config(config)),
        retry.betwixt_sleep_with_backoff(retry_config['initial_sleep'],
                                         retry_config['backoff']))

    return workflow.Result(failed=result.failed,
                           state=result.state,
                           workflow_step={'type': 'apply'},
                           outputs=result.outputs)
