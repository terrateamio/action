import collections
import os


State = collections.namedtuple('State', [
    'api_base_url',
    'api_token',
    'engine',
    'env',
    'outputs',
    'path',
    'repo_config',
    'result_version',
    'runtime',
    'secrets',
    'sha',
    'success',
    'tmpdir',
    'work_manifest',
    'work_token',
    'workflow',
    'working_dir',
    'workspace',
])


def create(api_base_url,
           api_token,
           repo_config,
           result_version,
           runtime,
           sha,
           work_manifest,
           work_token,
           working_dir):
    return State(
        api_base_url=api_base_url,
        api_token=api_token,
        engine=None,
        env=os.environ.copy(),
        outputs=[],
        path=None,
        repo_config=repo_config,
        result_version=result_version,
        runtime=runtime,
        secrets=set(),
        sha=sha,
        success=True,
        tmpdir=None,
        work_manifest=work_manifest,
        work_token=work_token,
        workflow=None,
        working_dir=working_dir,
        workspace=None,
    )


def set_secret(state, secret):
    if secret:
        state.runtime.set_secret(secret)
        return state._replace(secrets=state.secrets | set([secret]))
    else:
        return state


def combine_secrets(state, s):
    return state._replace(secrets=state.secrets | s.secrets)
