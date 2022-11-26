import retry
import workflow_step_terraform

TRIES = 3
INITIAL_SLEEP = 1
BACKOFF = 1.5


def run(state, config):
    original_config = config
    config = original_config.copy()
    config['args'] = ['init']
    config['output_key'] = 'init'

    result = retry.run(
        lambda: workflow_step_terraform.run(state, config),
        retry.finite_tries(TRIES, lambda result: not result.failed),
        retry.betwixt_sleep_with_backoff(INITIAL_SLEEP, BACKOFF))

    return result._replace(workflow_step={'type': 'init'})
