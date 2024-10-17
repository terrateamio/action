import logging
import tempfile

import run_state
import workflow_step_run


def source_cmd(fname):
    return [
        'set -e',
        'set -u',
        # Escape the variable here because we will apply templating in the
        # workflow_step_run call and $@ conflicts with how the templating works.
        'source "$$@" > {} 2>&1'.format(fname),
        'env -0'
    ]


def run_exec(state, config):
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

        if config.get('sensitive', False):
            state = run_state.set_secret(state, cmd_output)

        env = state.env.copy()
        env[config['name']] = cmd_output
        state = state._replace(env=env)
        result = result._replace(state=state, outputs=None)

    return result._replace(
        workflow_step={
            'type': 'env',
            'name': config['name'],
            'method': 'exec',
            'cmd': config['cmd']
        })


def run_source(state, config):
    with tempfile.NamedTemporaryFile() as tmp:
        # Construct a new config, pulling through the pieces of the existing config
        # that are needed for the [run] step.  This is a big fragile if [run] step
        # acquires new configuration, we have to remember to thread them through.
        run_config = {
            # The second 'bash' string here is because "bash -c" uses the first
            # parameter after the "-c" as the name of the shell.
            'cmd': ['bash', '-c', '\n'.join(source_cmd(tmp.name)), 'bash'] + config['cmd'],
            'capture_output': True,
            'log_output': False
        }

        if 'ignore_errors' in config:
            run_config['ignore_errors'] = config['ignore_errors']
        if 'run_on' in config:
            run_config['run_on'] = config['run_on']

        result = workflow_step_run.run(state, run_config)

        with open(tmp.name, 'r') as f:
            lines = f.read().splitlines()

        for line in lines:
            logging.info('cwd=%s : %s', state.working_dir, line)

    if not result.failed:
        state = result.state
        cmd_output = result.outputs['text']

        env = dict([line.split('=', 1) for line in cmd_output.split('\0') if line])

        if config.get('sensitive', False):
            for k, v in env.items():
                if k not in state.env or state.env[k] != v:
                    state = run_state.set_secret(state, v)

        state = state._replace(env=env)
        result = result._replace(state=state, outputs=None)

    return result._replace(
        workflow_step={
            'type': 'env',
            'method': 'source',
            'cmd': config['cmd']
        })


METHOD_DISPATCH = {
    'exec': run_exec,
    'source': run_source,
}


def run(state, config):
    return METHOD_DISPATCH[config.get('method', 'exec')](state, config)
