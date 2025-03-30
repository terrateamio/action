import logging

import cmd
import workflow


def run(state, config):
    capture_output = config.get('capture_output', True)
    visible_on = config.get('visible_on', 'error')

    try:
        # Only capture output if we want to save it somewhere or we have
        # explicitly enabled it.
        if capture_output:
            proc, stdout, stderr = cmd.run_with_output(state, config)
            if proc.returncode == 0:
                payload = {
                    'text': stdout,
                    'stderr': stderr
                }
            else:
                # Not a great solution but the best for shor term.  If the
                # command failed, just combine stdout and stderr.  Otherwise
                # we'll keep them separate on success because probably you don't
                # need to look at stderr on success and stdout might need to be
                # something like JSON that needs to be parsed.
                payload = {'text': '\n'.join([stderr, stdout])}
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
