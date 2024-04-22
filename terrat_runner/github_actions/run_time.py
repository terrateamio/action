import json
import logging
import os
import subprocess

import cmd
import repo_config as rc
import requests_retry

from . import core

from . import workflow_step_drift_create_issue


class Run_time(object):
    def initialize(self, state):
        subprocess.check_call(['git',
                               'config',
                               '--global',
                               'credential.https://github.com.username',
                               'x-access-token'])
        subprocess.check_call(['git',
                               'config',
                               '--global',
                               'url.https://github.com/.insteadOf',
                               'git@github.com:'])

        env = state.env.copy()
        askpass = '/tmp/askpass'
        with open(askpass, 'w') as f:
            f.write('#! /usr/bin/env bash\n')
            f.write('set -e\n')
            f.write('set -u\n')
            f.write('echo $TERRATEAM_GITHUB_TOKEN\n')
        os.chmod(askpass, 0o555)
        env['GIT_ASKPASS'] = askpass
        state = state._replace(env=env)
        return state

    def set_secret(self, secret):
        return core.set_secret(secret)

    def update_authentication(self, state):
        url = state.api_base_url + '/v1/work-manifests/' + state.work_token + '/access-token'
        res = requests_retry.post(url, headers={'authorization': 'bearer ' + state.api_token})

        if res.status_code == 200:
            access_token = res.json()['access_token']
            self.set_secret(access_token)
            env = state.env.copy()
            env['TERRATEAM_GITHUB_TOKEN'] = access_token
            return state._replace(env=env)
        else:
            raise Exception('Unable to obtain access token')

    def work_index(self, state):
        indexer_conf = rc.get_indexer(state.repo_config)
        build_tag = indexer_conf.get('build_tag', 'ghcr.io/terrateamio/terrat-code-indexer:latest')
        cmd.run(state, {'cmd': ['apt-get', 'update']})
        cmd.run(state, {'cmd': ['apt-get', 'install', '-y', 'docker.io']})
        cmd.run(state, {'cmd': ['docker', 'pull', build_tag]})
        repo_name = state.env['GITHUB_REPOSITORY'].split('/')[1]
        (proc, output) = cmd.run_with_output(
            state,
            {
                'cmd': [
                    'docker',
                    'run',
                    '-v',
                    '/home/runner/work/{repo_name}/{repo_name}/:/mnt/'.format(repo_name=repo_name),
                    build_tag,
                    'index'] + state.work_manifest['dirs']
            })

        if proc.returncode == 0:
            try:
                output = json.loads(output)
                output['success'] = True
            except json.JSONDecodeError as exn:
                logging.exception(exn)
                output = {'paths': {}, 'version': 1, 'success': False}
        else:
            output = {'paths': {}, 'version': 1, 'success': False}

        requests_retry.put(state.api_base_url + '/v1/work-manifests/' + state.work_token,
                           json=output)

    def steps(self):
        return {
            'drift_create_issue': workflow_step_drift_create_issue.run,
        }
