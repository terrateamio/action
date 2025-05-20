import json
import logging
import os
import tempfile

import cmd
import repo_config as rc
import requests_retry


def _cleanup_path(terrateam_root, path):
    if path.startswith(terrateam_root):
        return path[len(terrateam_root):]
    elif path.startswith('./'):
        return path[len('./'):]
    elif path.startswith('/'):
        return path[1:]
    else:
        return path


def _remove_none(d):
    keys = list(d.keys())
    for k in keys:
        if d[k] is None:
            d.pop(k)

    return d


# Clean up some common ways building a tree might be done wrong.  In particular:
#
# 1. Trees should not start with any absolute path, such as $TERRATEAM_ROOT
#
# 2. Trees should not start with any relative paths, like ./
def _cleanup(terrateam_root, files):
    return [
        # Remove any None's because, depending on how old the server is, it may
        # reject trees with the "id" key.  Older versions of the server are not
        # as accepting of extra keys.
        _remove_none(
            {
                'path': _cleanup_path(terrateam_root, v['path']),
                'changed': v.get('changed'),
                'id': v.get('id')
            })
            for v in files]


def run(state):
    tree_builder = rc.get_tree_builder(state.repo_config)

    if not tree_builder['enabled']:
        raise Exception('Impossible')

    with tempfile.TemporaryDirectory() as tmpdir:
        script = tree_builder['script']

        if not script.startswith('#!'):
            script = '#! /usr/bin/env bash\n\n' + script

        script_path = os.path.join(tmpdir, 'tree-builder')

        with open(script_path, 'w') as f:
            f.write(script)

        os.chmod(script_path, 0o005)

        try:
            env = {'TERRATEAM_BASE_REF': state.work_manifest['base_ref']}
            env.update(state.env)
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': [script_path],
                    'cwd': tmpdir,
                    'env': env,
                })
            if proc.returncode == 0:
                try:
                    tree = _cleanup(state.env['TERRATEAM_ROOT'], json.loads(stdout))
                    requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                                       json={'files': tree})
                except json.JSONDecodeError as exn:
                    logging.exception('Failed to decode JSON')
                    requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                                       json={'msg': exn.msg})
                except Exception as exn:
                    logging.exception('Unknown failure')
                    requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                                       json={'msg': str(exn)})
            else:
                requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                                   json={'msg': '\n'.join([stderr, stdout])})
        except Exception as exn:
            logging.exception('Unknown failure')
            requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                               json={'msg': str(exn)})
