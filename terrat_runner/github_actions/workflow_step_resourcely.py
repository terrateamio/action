import os
import tempfile

import workflow_step_run
import workflow_step_terraform


def run(state, config):
    result = workflow_step_terraform.run(state,
                                         {
                                             'args': ['show', '-json', '$TERRATEAM_PLAN_FILE'],
                                             'output_key': 'plan_json'
                                         })

    if result.failed:
        return result._replace(workflow_step={'type': 'resourcely'})

    plan_json = result.outputs['text']

    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = os.path.join(tmpdir, 'json')
        with open(json_file, 'w') as f:
            f.write(plan_json)

        run_config = {
            'cmd': ['resourcely-cli',
                    '--no_color',
                    'evaluate',
                    '--change_request_url',
                    'https://github.com/{}/pull/{}'.format(state.env['GITHUB_REPOSITORY'],
                                                           state.work_manifest['run_kind_data']['id']),
                    '--change_request_sha',
                    '${GITHUB_SHA}',
                    '--plan',
                    json_file],
            'capture_output': True
        }

        result = workflow_step_run.run(state, run_config)

    return result
