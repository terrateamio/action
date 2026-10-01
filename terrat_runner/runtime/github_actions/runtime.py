import json
import os
import subprocess
import sys

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

    def set_secret(self, secret):
        return core.set_secret(secret)

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

    def update_pre_hook_steps(self, run_type, steps):
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
