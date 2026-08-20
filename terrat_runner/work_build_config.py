import json
import os
import tempfile

import api
import cmd
import repo_config as rc


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
                    api.work_manifest_put(state, json={'config': config})
                except json.JSONDecodeError as exn:
                    api.work_manifest_put(state, json={'msg': exn.msg})
                except Exception as exn:
                    api.work_manifest_put(state, json={'msg': str(exn)})
            else:
                api.work_manifest_put(state, json={'msg': '\n'.join([stderr, stdout])})
        except Exception as exn:
            api.work_manifest_put(state, json={'msg': str(exn)})
