import json
import logging
import os
import tempfile

import workflow
import workflow_step_run


def run(state, config):
    extra_args = config.get('extra_args', [])

    res = state.engine.show(state, config)

    if res is None:
        return workflow.Result2(
            payload={
                'text': 'Unsable to show plan'
            },
            state=state,
            step='run',
            success=False)

    (success, stdout, stderr) = res

    if not success:
        return workflow.Result2(
            payload={
                'text': '\n'.join([stderr, stdout])
            },
            state=state,
            step='run',
            success=False)

    plan_json = stdout

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
            except json.JSONDecodeError as exn:
                logging.exception(exn)
                pass

        if errors:
            result.payload['text'] = '\n'.join(errors)
        else:
            result.payload['text'] = result.payload['text']

    return result
