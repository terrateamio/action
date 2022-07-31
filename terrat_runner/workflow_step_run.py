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

        try:
            # Only capture output if we want to save it somewhere
            if output_key is not None:
                proc, stdout = cmd.run_with_output(state, config)
                state.output[output_key] = stdout
            else:
                proc = cmd.run(state, config)

            failed = not (proc.returncode == 0 or ignore_errors)
        except cmd.MissingEnvVar as exn:
            # On env error, add to 'error' key in output
            state.output.setdefault('errors', []).append(
                'Missing environment variable: {}'.format(exn.args[0])
            )
            failed = True

        return workflow.Result(failed=failed, state=state)
    else:
        return workflow.Result(failed=False, state=state)
