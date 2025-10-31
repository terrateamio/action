import os

import kv_store
import workflow


def _mk_key(state):
    def _f(_):
        return kv_store.mk_dirspace_key(state, 'init')

    return _f

def run(state, config):
    config = config.copy()
    config['tee'] = kv_store.gen_unique_key_path(state, _mk_key(state))
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
