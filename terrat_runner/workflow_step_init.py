import workflow


def run(state, config):
    (success, stdout, stderr) = state.engine.init(state, config)

    if success:
        text = stdout
    else:
        text = '\n'.join([stderr, stdout])

    return workflow.Result2(
        payload={
            'text': text,
            'visible_on': 'error'
        },
        state=state,
        step=state.engine.name + '/init',
        success=success)
