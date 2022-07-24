import base64
import hashlib
import logging
import os
import tempfile

import requests

import repo_config as rc
import work_exec
import workflow_step


def _load_plan(work_token, api_base_url, dir_path, workspace, plan_path):
    res = requests.get(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
                       params={'path': dir_path, 'workspace': workspace})

    if res.status_code != 200:
        raise Exception('Could not load plan')

    plan_raw_data = base64.b64decode(res.json()['data'])

    logging.debug('APPLY : LOAD_PLAN : dir_path=%s : workspace=%s : md5=%s',
                  dir_path,
                  workspace,
                  hashlib.md5(plan_raw_data).hexdigest())

    with open(plan_path, 'wb') as f:
        f.write(plan_raw_data)


class Exec(work_exec.ExecInterface):
    def pre_hooks(self, state):
        return [{'type': 'checkout'}] + rc.get_apply_hooks(state.repo_config)['pre']

    def post_hooks(self, state):
        return rc.get_apply_hooks(state.repo_config)['post']

    def exec(self, state, d):
        with tempfile.TemporaryDirectory() as tmpdir:
            logging.debug('EXEC : DIR : %s', d['path'])

            # Need to reset output every iteration unfortunately because we do not
            # have immutable dicts
            state = state._replace(output={})

            path = d['path']
            workspace = d['workspace']
            workflow_idx = d.get('workflow')

            _load_plan(state.work_token,
                       state.api_base_url,
                       path,
                       workspace,
                       os.path.join(tmpdir, 'plan'))

            env = state.env.copy()
            env['TERRATEAM_PLAN_FILE'] = os.path.join(tmpdir, 'plan')
            env['TERRATEAM_DIR'] = path
            env['TERRATEAM_WORKSPACE'] = workspace
            env['TERRATEAM_TMPDIR'] = tmpdir

            create_and_select_workspace = rc.get_create_and_select_workspace(
                state.repo_config,
                path)

            logging.info('APPLY : CREATE_AND_SELECT_WORKSPACE : %s : %r',
                         path,
                         create_and_select_workspace)

            if create_and_select_workspace:
                env['TF_WORKSPACE'] = workspace

            state = state._replace(env=env)

            if workflow_idx is None:
                workflow = rc.get_default_workflow(state.repo_config)
            else:
                workflow = rc.get_workflow(state.repo_config, workflow_idx)

            state = workflow_step.run_steps(
                state._replace(working_dir=os.path.join(state.working_dir, path),
                               path=path,
                               workspace=workspace,
                               workflow=workflow),
                workflow['apply'])

            result = {
                'path': path,
                'workspace': workspace,
                'success': not state.failed,
                'output': state.output.copy()
            }

            return (state, result)
