import json
import logging
import os
import subprocess
import sys

import cmd
import repo_config as rc
import requests_retry

from . import core

from . import workflow_step_drift_create_issue
from . import workflow_step_resourcely
from . import workflow_step_update_terrateam_github_token


class Runtime(object):
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

    def name(self):
        return 'github'

    def set_secret(self, secret):
        return core.set_secret(secret)

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
        return {
            'drift_create_issue': workflow_step_drift_create_issue.run,
            'resourcely': workflow_step_resourcely.run,
            'update_terrateam_github_token': workflow_step_update_terrateam_github_token.run,
        }

    def group_output(self, title, output):
        sys.stdout.write('::group::{}\n'.format(title))
        sys.stdout.write(output)
        sys.stdout.write('\n')
        sys.stdout.write('::endgroup::\n')
        sys.stdout.flush()

    def update_workflow_steps(self, run_type, steps):
        return [{'type': 'update_terrateam_github_token'}] + steps

    def is_command(self, str):
        return str.startswith('::add-mask::')

    def extract_secrets(self, str):
        secrets = []
        for s in str.splitlines():
            if s.startswith('::add-mask::'):
                secrets.append(s[len('::add-mask::'):])

        return secrets


    def add_reviewers(self, env, reviewers):
        if env['TERRATEAM_RUN_KIND'] == 'pr' and reviewers:
            data = json.loads(env['TERRATEAM_RUN_KIND_DATA'])
            pr_number = data['id']

            url = '{}/repos/{}/pulls/{}/requested_reviewers'.format(
                env['GITHUB_API_URL'],
                env['GITHUB_REPOSITORY'],
                pr_number
            )

            user_reviewers = [r.split('user:')[1] for r in reviewers if r.startswith('user:')]
            team_reviewers = [r.split('team:')[1] for r in reviewers if r.startswith('team:')]

            data = {
                'reviewers': user_reviewers,
                'team_reviewers': team_reviewers
            }

            headers = {
                'content-type': 'application/json',
                'authorization': 'bearer {}'.format(env['TERRATEAM_GITHUB_TOKEN'])
            }

            res = requests_retry.post(url, headers=headers, json=data)

            if res.status_code != 201:
                raise Exception('Could not add reviewers')
