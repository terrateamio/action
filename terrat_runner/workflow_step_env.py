import logging
import tempfile

import cmd
import run_state
import workflow_step_run


def source_cmd(fname):
    return [
        'set -e',
        'set -u',
        'source "$@" > {} 2>&1'.format(fname),
        'env -0'
    ]


def run_exec(state, config):
    run_config = {
        'cmd': config['cmd'],
        'capture_output': True,
        'log_output': not config.get('sensitive', False),
        'log_cmd_pre_replace': True,
    }

    result = workflow_step_run.run(state, run_config)

    if result.success:
        cmd_output = result.payload['text']

        if config.get('trim_trailing_newlines', True):
            cmd_output = cmd_output.rstrip('\n')

        if config.get('sensitive', False):
            state = run_state.set_secret(state, cmd_output)

        env = state.env.copy()
        env[config['name']] = cmd_output
        state = state._replace(env=env)
        result = result._replace(state=state)

    payload = {
        'cmd': result.payload.get('cmd', config['cmd']),
        'method': 'exec',
        'text': result.payload['text']
    }

    return result._replace(payload=payload,
                           step='env')


def run_source(state, config):
    with tempfile.NamedTemporaryFile() as tmp:
        run_config = {
            # The second 'bash' string here is because "bash -c" uses the first
            # parameter after the "-c" as the name of the shell.
            'cmd': (['bash', '-c', '\n'.join(source_cmd(tmp.name)), 'bash']
                    + [cmd.replace_vars(c, state.env) for c in config['cmd']]),
            'capture_output': True,
            'log_output': not config.get('sensitive', False),
            'log_cmd_pre_replace': True,
            'replace_vars': False,
        }
        result = workflow_step_run.run(state, run_config)

        with open(tmp.name, 'r') as f:
            lines = f.read()

        for line in lines.splitlines():
            logging.info('cwd=%s : %s', state.working_dir, line)

    if result.success:
        state = result.state
        cmd_output = result.payload['text']

        env = dict([line.split('=', 1) for line in cmd_output.split('\0') if line])

        if config.get('sensitive', False):
            for k, v in env.items():
                if k not in state.env or state.env[k] != v:
                    state = run_state.set_secret(state, v)

        state = state._replace(env=env)
        result = result._replace(state=state)

    payload = {
        'cmd': result.payload.get('cmd', config['cmd']),
        'method': 'source',
        'text': lines
    }

    return result._replace(payload=payload,
                           step='env')


METHOD_DISPATCH = {
    'exec': run_exec,
    'source': run_source,
}


def run(state, config):
    return METHOD_DISPATCH[config.get('method', 'exec')](state, config)
