import os
import subprocess
import sys

from . import core

from . import workflow_step_drift_create_issue


class Runtime(object):
    def initialize(self, state):
        return state

    def set_secret(self, secret):
        pass

    def steps(self):
        return {
            'drift_create_issue': workflow_step_drift_create_issue.run,
        }

    def group_output(self, title, output):
        sys.stdout.write(output)
        sys.stdout.flush()

    def update_workflow_steps(self, run_type, steps):
        return steps

    def update_pre_hook_steps(self, run_type, steps):
        return steps

    def is_command(self, str):
        return str.startswith('::add-mask::')

    def extract_secrets(self, str):
        secrets = []
        for s in str.splitlines():
            if s.startswith('::add-mask::'):
                secrets.append(s[len('::add-mask::'):])

        return secrets

    def add_reviewers(self, env, reviewers):
        pass

