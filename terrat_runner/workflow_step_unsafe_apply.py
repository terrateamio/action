import repo_config as rc
import retry
import workflow_step_terraform


def run(state, config):
    config = config.copy()
    config['args'] = ['apply', '-auto-approve']
    config['output_key'] = 'apply'

    retry_config = rc.get_retry(config)
    tries = retry_config['enabled'] and retry_config['tries'] or 1
    result = retry.run(
        lambda: workflow_step_terraform.run(state, config),
        retry.finite_tries(tries, lambda ret: ret.success),
        retry.betwixt_sleep_with_backoff(retry_config['initial_sleep'],
                                         retry_config['backoff']))

    return result._replace(step='tf/apply')
