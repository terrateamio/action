import os
import subprocess

import requests_retry

from . import core


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
