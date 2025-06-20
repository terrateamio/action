import json
import logging
import os
import subprocess
import sys

import cmd
import repo_config as rc
import requests_retry

from . import core


class Runtime(object):
    def initialize(self, state):
        return state

    def set_secret(self, secret):
        pass

    def work_index(self, state):
        indexer_conf = rc.get_indexer(state.repo_config)
        build_tag = indexer_conf.get('build_tag', 'ghcr.io/terrateamio/terrat-code-indexer:latest')
        cmd.run(state, {'cmd': ['apt-get', 'update']})
        cmd.run(state, {'cmd': ['apt-get', 'install', '-y', 'docker.io', 'musl']})
        cmd.run(state, {'cmd': ['docker', 'pull', build_tag]})

        # Default output so we don't have to set it in every failure path
        stdout = {'paths': {}, 'version': 1, 'success': False}

        proc = cmd.run(
            state,
            {
                'cmd': [
                    'docker',
                    'create',
                    '--name',
                    'code-indexer',
                    build_tag
                ]
            })
        if proc.returncode == 0:
            proc = cmd.run(
                state,
                {
                    'cmd': [
                        'docker',
                        'cp',
                        'code-indexer:/usr/local/bin/terrat_code_indexer',
                        '/tmp'
                    ]
                })

            if proc.returncode == 0:
                cmd.run(
                    state,
                    {
                        'cmd': ['docker', 'rm', 'code-indexer',]
                    })

                (proc, stdout, stderr) = cmd.run_with_output(
                    state,
                    {
                        'cmd': ['/tmp/terrat_code_indexer', 'index'] + state.work_manifest['dirs']
                    })

                if proc.returncode == 0:
                    try:
                        stdout = json.loads(stdout)
                        stdout['success'] = True
                    except json.JSONDecodeError as exn:
                        logging.exception(exn)
                        stdout = {'paths': {}, 'version': 1, 'success': False}
                else:
                    logging.error('Failed to run indexer')
            else:
                logging.error('Failed to copy indexer')
        else:
            logging.error('Failed to create indexer image')

        requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                           json=stdout)


    def steps(self):
        return {}

    def group_output(self, title, output):
        sys.stdout.write(output)
        sys.stdout.flush()

    def update_workflow_steps(self, run_type, steps):
        return steps

    def is_command(self, str):
        return str.startswith('::add-mask::')

    def extract_secrets(self, str):
        secrets = []
        for s in str.splitlines():
            if s.startswith('::add-mask::'):
                secrets.append(s[len('::add-mask::'):])

        return secrets
