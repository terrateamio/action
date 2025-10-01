import os

import kv_store
import workflow


def run(state, config):
    config = config.copy()
    init_key = kv_store.mk_dirspace_key(state, 'init')
    config['tee'] = os.path.join(state.outputs_dir, init_key)
    (success, stdout_key, stderr_key) = state.engine.init(state, config)

    return workflow.Result2(
        payload={
            '@text': os.path.basename(stdout_key),
            '@stderr': os.path.basename(stderr_key),
            'visible_on': 'error'
        },
        state=state,
        step=state.engine.name + '/init',
        success=success)
