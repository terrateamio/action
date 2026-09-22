import json
import logging

import api
import cmd


def run(state):
    # Default output so we don't have to set it in every failure path
    output = {'paths': {}, 'version': 1, 'success': False}

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['stategraph', 'osc', 'indexer'] + state.work_manifest['dirs']
        })

    if proc.returncode == 0:
        try:
            output = json.loads(stdout)
            output['success'] = True
        except json.JSONDecodeError as exn:
            logging.exception(exn)
    else:
        logging.error('Failed to run indexer')

    api.work_manifest_put(state, json=output)
