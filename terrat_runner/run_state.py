import collections
import os


State = collections.namedtuple('State', ['work_token',
                                         'api_token',
                                         'repo_config',
                                         'working_dir',
                                         'work_manifest',
                                         'api_base_url',
                                         'workspace',
                                         'workflow',
                                         'path',
                                         'env',
                                         'outputs',
                                         'failed',
                                         'sha',
                                         'tmpdir',
                                         'run_time',
                                         'secrets'])


def create(work_token,
           api_token,
           repo_config,
           working_dir,
           api_base_url,
           work_manifest,
           sha,
           run_time):
    return State(work_token=work_token,
                 api_token=api_token,
                 repo_config=repo_config,
                 working_dir=working_dir,
                 work_manifest=work_manifest,
                 api_base_url=api_base_url,
                 path=None,
                 workspace=None,
                 workflow=None,
                 env=os.environ.copy(),
                 outputs=[],
                 failed=False,
                 sha=sha,
                 tmpdir=None,
                 run_time=run_time,
                 secrets=set())


def set_secret(state, secret):
    state.run_time.set_secret(secret)
    return state._replace(secrets=state.secrets | set([secret]))
