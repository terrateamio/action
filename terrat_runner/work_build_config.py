import json
import os
import tempfile

import cmd
import repo_config as rc
import requests_retry


def run(state):
    config_builder = rc.get_config_builder(state.repo_config)

    if not config_builder['enabled']:
        raise Exception('Impossible')

    with tempfile.TemporaryDirectory() as tmpdir:
        script = config_builder['script']

        if not script.startswith('#!'):
            script = '#! /usr/bin/env bash\n\n' + script

        script_path = os.path.join(tmpdir, 'config-builder')

        with open(script_path, 'w') as f:
            f.write(script)

        os.chmod(script_path, 0o005)

        try:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': [script_path],
                    'input': json.dumps(state.repo_config),
                    'cwd': tmpdir
                })
            if proc.returncode == 0:
                try:
                    config = json.loads(stdout)
                    requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                                       json={'config': config})
                except json.JSONDecodeError as exn:
                    requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                                       json={'msg': exn.msg})
                except Exception as exn:
                    requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                                       json={'msg': str(exn)})
            else:
                requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                                   json={'msg': '\n'.join([stderr, stdout])})
        except Exception as exn:
            requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                               json={'msg': str(exn)})
