import collections
import os


State = collections.namedtuple('State', [
    'api_base_url',
    'api_token',
    'env',
    'outputs',
    'path',
    'repo_config',
    'result_version',
    'run_time',
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
           run_time,
           sha,
           work_manifest,
           work_token,
           working_dir):
    return State(
        api_base_url=api_base_url,
        api_token=api_token,
        env=os.environ.copy(),
        outputs=[],
        path=None,
        repo_config=repo_config,
        result_version=result_version,
        run_time=run_time,
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
    state.run_time.set_secret(secret)
    return state._replace(secrets=state.secrets | set([secret]))
