import logging

import cmd
import workflow


RUN_ON_SUCCESS = 'success'
RUN_ON_FAILURE = 'failure'
RUN_ON_ALWAYS = 'always'


def run(state, config):
    ignore_errors = config.get('ignore_errors', False)
    run_on = config.get('run_on', RUN_ON_SUCCESS)

    if ignore_errors not in [True, False]:
        raise Exception('Invalid hook ignore_errors configuration: {}'.format(config))

    if run_on not in [RUN_ON_SUCCESS, RUN_ON_FAILURE, RUN_ON_ALWAYS]:
        raise Exception('Invalid hook run_on configuration: {}'.format(config))

    if run_on == RUN_ON_ALWAYS \
       or (state.failed and run_on == RUN_ON_FAILURE) \
       or (not state.failed and run_on == RUN_ON_SUCCESS):

        output_key = config.get('output_key')
        capture_output = config.get('capture_output', False)

        outputs = None

        try:
            # Only capture output if we want to save it somewhere or we have
            # explicitly enabled it.
            if output_key is not None or capture_output:
                proc, stdout = cmd.run_with_output(state, config)
                if output_key:
                    outputs = {'output_key': output_key, 'text': stdout}
                else:
                    outputs = {'text': stdout}
            else:
                proc = cmd.run(state, config)

            failed = not (proc.returncode == 0 or ignore_errors)
            return workflow.Result(failed=failed,
                                   state=state,
                                   workflow_step={
                                       'type': 'run',
                                       'cmd': config['cmd'],
                                       'exit_code': proc.returncode
                                   },
                                   outputs=outputs)
        except cmd.MissingEnvVar as exn:
            failed = True
            logging.error('Missing environment variable: %s', exn.args[0])
            outputs = {
                'text': 'ERROR: Missing environment variable: {}'.format(exn.args[0])
            }
            if output_key:
                outputs['output_key'] = output_key

            return workflow.Result(failed=failed,
                                   state=state,
                                   workflow_step={
                                       'type': 'run',
                                       'cmd': config['cmd'],
                                   },
                                   outputs=outputs)
        except FileNotFoundError:
            failed = True
            logging.exception('Could not find program to run %r', config['cmd'])
            outputs = {
                'text': 'ERROR: Could not find program to run: {}'.format(config['cmd'])
            }
            if output_key:
                outputs['output_key'] = output_key

            return workflow.Result(failed=True,
                                   state=state,
                                   workflow_step={
                                       'type': 'run',
                                       'cmd': config['cmd'],
                                   },
                                   outputs=outputs)

    else:
        return workflow.Result(failed=True,
                               state=state,
                               workflow_step={'type': 'run', 'cmd': config['cmd']},
                               outputs=None)
