import json

import workflow


def run(state, config):
    (success, stdout, stderr) = state.engine.unsafe_apply(state, config)

    if not success:
        return workflow.Result2(
            payload={
                'text': '\n'.join([stderr, stdout]),
                'visible_on': 'always',
            },
            state=state,
            step=state.engine.name + '/apply',
            success=False)

    res = state.engine.outputs(state, config)

    if res:
        (success, outputs_stdout, outputs_stderr) = res
    else:
        success = True
        outputs_stdout = '{}'
        outputs_stderr = ''

    try:
        outputs = json.loads(outputs_stdout)
        if outputs:
            return workflow.Result2(
                payload={
                    'text': stdout,
                    'outputs': outputs,
                    'visible_on': 'always',
                },
                state=state,
                step=state.engine.name + '/apply',
                success=True)
    except json.JSONDecodeError as exn:
        return workflow.Result2(
            payload={
                'text': '\n'.join([outputs_stderr, outputs_stdout]),
                'error': str(exn),
                'visible_on': 'always'
            },
            state=state,
            step=state.engine.name + '/apply',
            sucecss=False)
