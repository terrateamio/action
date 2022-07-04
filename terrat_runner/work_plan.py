import base64
import hashlib
import logging
import os
import tempfile

import requests

import repo_config as rc
import work_exec
import workflow_step


def _store_plan(work_token, api_base_url, dir_path, workspace, plan_path):
    try:
        with open(plan_path, 'rb') as f:
            plan_raw_data = f.read()
            plan_data = base64.b64encode(plan_raw_data).decode('utf-8')

        logging.debug('PLAN : STORE_PLAN : dir_path=%s : workspace=%s : md5=%s',
                      dir_path,
                      workspace,
                      hashlib.md5(plan_raw_data).hexdigest())

        res = requests.post(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
                            json={
                                'path': dir_path,
                                'workspace': workspace,
                                'plan_data': plan_data
                            })

        return res.status_code == 200
    except Exception as exn:
        print('Failed: {}'.format(exn))
        return False


class Exec(work_exec.ExecInterface):
    def hooks(self, state):
        return rc.get_plan_hooks(state.repo_config)

    def exec(self, state, d):
        with tempfile.TemporaryDirectory() as tmpdir:
            logging.debug('EXEC : DIR : %s', d['path'])

            # Need to reset output every iteration unfortunately because we do not
            # have immutable dicts
            state = state._replace(output={})

            path = d['path']
            workspace = d['workspace']
            workflow_idx = d.get('workflow')

            env = state.env.copy()
            env['TERRATEAM_PLAN_FILE'] = os.path.join(tmpdir, 'plan')
            env['TERRATEAM_DIR'] = path
            env['TERRATEAM_WORKSPACE'] = workspace
            env['TERRATEAM_TMPDIR'] = tmpdir
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
                workflow['plan'])

            if not state.failed:
                success = _store_plan(state.work_token,
                                      state.api_base_url,
                                      path,
                                      workspace,
                                      os.path.join(tmpdir, 'plan'))
                state = state._replace(failed=not success)

            result = {
                'path': path,
                'workspace': workspace,
                'success': not state.failed,
                'output': state.output.copy()
            }

            return (state, result)
