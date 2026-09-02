import workflow


def run(state, config):
    visible_on = config.get('visible_on', 'failure')

    (success, stdout, stderr) = state.engine.init(state, config)

    if success:
        text = stdout
    else:
        text = '\n'.join([stderr, stdout])

    return workflow.Result2(
        payload={
            'text': text,
            'visible_on': visible_on
        },
        state=state,
        step=state.engine.name + '/init',
        success=success)
