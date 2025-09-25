import logging
import os

import cmd
import kv_store
import workflow


def _mk_key(state):
    def _f(unique):
        if 'TERRATEAM_DIR' in state.env and 'TERRATEAM_WORKSPACE' in state.env:
            return kv_store.mk_dirspace_key(state, 'run.' + unique)
        else:
            return kv_store.mk_hooks_key(state, 'run', unique)

    return _f


def run(state, config):
    capture_output = config.get('capture_output', True)
    visible_on = config.get('visible_on', 'error')

    # Set ignore errors to true by default if any gates are set and the user
    # hasn't explicitly set a config.
    config['ignore_errors'] = config.get(
        'ignore_errors',
        any(c.get('type') == 'gate' for c in config.get('on_error', [])))

    try:
        # Only capture output if we want to save it somewhere or we have
        # explicitly enabled it.
        if capture_output:
            config = config.copy()
            config['tee'] = kv_store.gen_unique_key_path(state, _mk_key(state))
            proc, stdout_key, stderr_key = cmd.run_with_output(state, config)
            payload = {
                '@text': os.path.basename(stdout_key),
                '@stderr': os.path.basename(stderr_key),
            }
        else:
            proc = cmd.run(state, config)
            payload = {}

        payload['cmd'] = proc.args
        payload['exit_code'] = proc.returncode
        payload['visible_on'] = visible_on

        success = (proc.returncode == 0)

        return workflow.make(payload=payload,
                             state=state,
                             step='run',
                             success=success)
    except cmd.MissingEnvVar as exn:
        logging.error('Missing environment variable: %s', exn.args[0])
        payload = {
            'cmd': config['cmd'],
            'text': 'ERROR: Missing environment variable: {}'.format(exn.args[0]),
            'visible_on': visible_on
        }
        return workflow.make(payload=payload,
                             state=state,
                             step='run',
                             success=False)
    except FileNotFoundError:
        logging.exception('Could not find program to run %r', config['cmd'])
        payload = {
            'cmd': config['cmd'],
            'text': 'ERROR: Could not find program to run: {}'.format(config['cmd']),
            'visible_on': visible_on
        }

        return workflow.make(payload=payload,
                             state=state,
                             step='run',
                             success=False)
