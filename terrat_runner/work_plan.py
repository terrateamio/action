import base64
import hashlib
import logging
import os
import tempfile

import repo_config as rc
import requests_retry
import work_exec
import workflow_step
import workflow_step_terrateam_ssh_key_setup


TRIES = 3
INITIAL_SLEEP = 1
BACKOFF = 1.5


def _store_plan(work_token, api_base_url, dir_path, workspace, plan_path):
    try:
        with open(plan_path, 'rb') as f:
            plan_raw_data = f.read()
            plan_data = base64.b64encode(plan_raw_data).decode('utf-8')

        logging.debug('PLAN : STORE_PLAN : dir_path=%s : workspace=%s : md5=%s',
                      dir_path,
                      workspace,
                      hashlib.md5(plan_raw_data).hexdigest())

        res = requests_retry.post(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
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
    def pre_hooks(self, state):
        pre_hooks = rc.get_all_hooks(state.repo_config)['pre']
        env = state.env
        if 'TF_API_TOKEN' in env:
            pre_hooks.append({'type': 'tf_cloud_setup'})
        if workflow_step_terrateam_ssh_key_setup.ssh_keys(env):
            pre_hooks.append({'type': 'terrateam_ssh_key_setup'})
        pre_hooks.extend(rc.get_plan_hooks(state.repo_config)['pre'])
        cost_estimation_config = rc.get_cost_estimation(state.repo_config)
        if cost_estimation_config['enabled']:
            if cost_estimation_config['provider'] == 'infracost':
                pre_hooks.append(
                    {
                        'type': 'infracost_setup',
                        'currency': cost_estimation_config['currency']
                    }
                )
        return pre_hooks

    def post_hooks(self, state):
        return (rc.get_all_hooks(state.repo_config)['post']
                + rc.get_plan_hooks(state.repo_config)['post'])

    def exec(self, state, d):
        with tempfile.TemporaryDirectory() as tmpdir:
            logging.debug('EXEC : DIR : %s', d['path'])

            # Need to reset output every iteration unfortunately because we do not
            # have immutable dicts
            state = state._replace(outputs=[])

            path = d['path']
            workspace = d['workspace']
            workflow_idx = d.get('workflow')

            env = state.env.copy()
            env['TERRATEAM_PLAN_FILE'] = os.path.join(tmpdir, 'plan')
            env['TERRATEAM_DIR'] = path
            env['TERRATEAM_WORKSPACE'] = workspace
            env['TERRATEAM_TMPDIR'] = tmpdir

            create_and_select_workspace = rc.get_create_and_select_workspace(
                state.repo_config,
                path)

            logging.info('PLAN : CREATE_AND_SELECT_WORKSPACE : %s : %r',
                         path,
                         create_and_select_workspace)

            if create_and_select_workspace:
                env['TF_WORKSPACE'] = workspace

            if workflow_idx is None:
                workflow = rc.get_default_workflow(state.repo_config)
            else:
                workflow = rc.get_workflow(state.repo_config, workflow_idx)

            env['TERRATEAM_TERRAFORM_VERSION'] = workflow['terraform_version']
            state = state._replace(env=env)

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
                'outputs': state.outputs.copy(),
            }

            return (state, result)
