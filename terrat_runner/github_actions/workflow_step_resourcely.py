import json
import os
import tempfile

import workflow_step_run
import workflow_step_terraform


def run(state, config):
    extra_args = config.get('extra_args', [])

    result = workflow_step_terraform.run(state,
                                         {
                                             'args': ['show', '-json', '$TERRATEAM_PLAN_FILE'],
                                             'output_key': 'plan_json'
                                         })

    if not result.success:
        return result

    plan_json = result.outputs['text']

    with tempfile.TemporaryDirectory() as tmpdir:
        json_file = os.path.join(tmpdir, 'json')
        with open(json_file, 'w') as f:
            f.write(plan_json)

        run_config = {
            'cmd': ['resourcely-cli',
                    '--no_color',
                    'evaluate',
                    '--error_on_violations',
                    '--format',
                    'json',
                    '--change_request_url',
                    'https://github.com/{}/pull/{}'.format(state.env['GITHUB_REPOSITORY'],
                                                           state.work_manifest['run_kind_data']['id']),
                    '--change_request_sha',
                    '${GITHUB_SHA}',
                    '--plan',
                    json_file] + extra_args,
            'capture_output': True
        }

        result = workflow_step_run.run(state, run_config)

    if not result.success:
        errors = []
        lines = result.payload['text'].splitlines()
        for line in lines:
            try:
                line = json.loads(line)
                if line['label'] == 'error':
                    errors.append(line['data'])
                data = json.loads(line['data'])
                break
            except json.JSONDecodeError:
                pass

        if errors:
            result.payload['text'] = '\n'.join(errors)
        else:
            result.payload['text'] = json.dumps(data, indent=2)

    return result
