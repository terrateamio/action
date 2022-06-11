import workflow_step_run


def run(state, config):
    # We're going to reuse how the workflow_step_run works but we don't want to
    # much up anything in the [output] section, so we save it, replace, and then
    # we'll restore it once done
    output = state.output

    # Construct a new config, pulling through the pieces of the existing config
    # that are needed for the [run] step.  This is a big fragile if [run] step
    # acquires new configuration, we have to remember to thread them through.
    run_config = {
        'cmd': config['cmd'],
        'output_key': 'output'
    }

    if 'ignore_errors' in config:
        run_config['ignore_errors'] = config['ignore_errors']
    if 'run_on' in config:
        run_config['run_on'] = config['run_on']

    (failed, state) = workflow_step_run.run(state._replace(output={}), run_config)

    cmd_output = state.output['output']

    if config.get('trim_trailing_newlines', True):
        cmd_output = cmd_output.rstrip(b'\n')

    state = state._replace(output=output)

    if not failed:
        env = state.env.copy()
        env[config['name']] = cmd_output
        state = state._replace(env=env)

    return (failed, state)
