import workflow_step_run


def run(state, config):
    # Construct a new config, pulling through the pieces of the existing config
    # that are needed for the [run] step.  This is a big fragile if [run] step
    # acquires new configuration, we have to remember to thread them through.
    run_config = {
        'cmd': config['cmd'],
        'capture_output': True
    }

    if 'ignore_errors' in config:
        run_config['ignore_errors'] = config['ignore_errors']
    if 'run_on' in config:
        run_config['run_on'] = config['run_on']

    result = workflow_step_run.run(state, run_config)

    if not result.failed:
        cmd_output = result.outputs['text']

        if config.get('trim_trailing_newlines', True):
            cmd_output = cmd_output.rstrip('\n')

        env = state.env.copy()
        env[config['name']] = cmd_output
        state = state._replace(env=env)
        result = result._replace(state=state, outputs=None)

    return result._replace(
        workflow_step={
            'type': 'env',
            'name': config['name'],
            'cmd': config['cmd']
        })
