import base64
import hashlib
import json
import logging
import os
import string
import tempfile

import cmd
import repo_config as rc
import requests_retry
import work_exec
import workflow_step
import workflow_step_terrateam_ssh_key_setup


def _load_plan(state, work_token, api_base_url, dir_path, workspace, plan_path):
    res = requests_retry.get(api_base_url + '/v1/work-manifests/' + work_token + '/plans',
                             params={'path': dir_path, 'workspace': workspace})

    if res.status_code != 200:
        return (False, 'Could not load plan from backend')

    plan_data = base64.b64decode(res.json()['data'])

    try:
        plan_data = json.loads(plan_data)

        if plan_data['method'] == 'terrateam':
            plan_data_encoded = plan_data['data']
            plan_data_raw = base64.b64decode(plan_data_encoded)
            logging.debug('APPLY : LOAD_PLAN : dir_path=%s : workspace=%s : md5=%s',
                          dir_path,
                          workspace,
                          hashlib.md5(plan_data_raw).hexdigest())

            with open(plan_path, 'wb') as f:
                f.write(plan_data_raw)

            return (True, None)
        elif plan_data['method'] == 'cmd':
            tmpl_vars = {
                'plan_dst_path': plan_path
            }
            fetch_cmd = [string.Template(s).safe_substitute(tmpl_vars) for s in plan_data['fetch']]
            proc = cmd.run(state, {'cmd': fetch_cmd})
            if proc.returncode != 0:
                return (False, 'Failed to fetch plan, see action logs for more details')
            if plan_data.get('delete'):
                cmd.run(state, {'cmd': plan_data['delete']})
                return (True, None)
        else:
            raise Exception('Unknown method')
    except json.JSONDecodeError:
        plan_data_raw = plan_data
        logging.debug('APPLY : LOAD_PLAN : dir_path=%s : workspace=%s : md5=%s',
                      dir_path,
                      workspace,
                      hashlib.md5(plan_data_raw).hexdigest())

        with open(plan_path, 'wb') as f:
            f.write(plan_data_raw)

        return (True, None)


class Exec(work_exec.ExecInterface):
    def pre_hooks(self, state):
        pre_hooks = rc.get_all_hooks(state.repo_config)['pre']

        env = state.env
        if 'TF_API_TOKEN' in env:
            pre_hooks.append({'type': 'tf_cloud_setup'})
        if workflow_step_terrateam_ssh_key_setup.ssh_keys(env):
            pre_hooks.append({'type': 'terrateam_ssh_key_setup'})

        pre_hooks.extend(rc.get_apply_hooks(state.repo_config)['pre'])

        return pre_hooks

    def post_hooks(self, state):
        return (rc.get_all_hooks(state.repo_config)['post']
                + rc.get_apply_hooks(state.repo_config)['post'])

    def exec(self, state, d):
        with tempfile.TemporaryDirectory() as tmpdir:
            logging.debug('EXEC : DIR : %s', d['path'])

            # Need to reset output every iteration unfortunately because we do not
            # have immutable dicts
            state = state._replace(outputs=[])

            path = d['path']
            workspace = d['workspace']
            workflow_idx = d.get('workflow')

            (success, output) = _load_plan(state,
                                           state.work_token,
                                           state.api_base_url,
                                           path,
                                           workspace,
                                           os.path.join(tmpdir, 'plan'))

            if not success:
                outputs = [
                    {
                        'success': False,
                        'outputs': {'text': output},
                        'workflow_step': {
                            'type': 'init'
                        }
                    }
                ]
                state = state._replace(failed=True)
                result = {
                    'path': path,
                    'workspace': workspace,
                    'success': not state.failed,
                    'outputs': outputs,
                }
                return (state, result)
            else:
                env = state.env.copy()
                env['TERRATEAM_PLAN_FILE'] = os.path.join(tmpdir, 'plan')
                env['TERRATEAM_DIR'] = path
                env['TERRATEAM_WORKSPACE'] = workspace
                env['TERRATEAM_TMPDIR'] = tmpdir

                if workflow_idx is None:
                    workflow = rc.get_default_workflow(state.repo_config)
                else:
                    workflow = rc.get_workflow(state.repo_config, workflow_idx)

                create_and_select_workspace = rc.get_create_and_select_workspace(
                    state.repo_config,
                    path)

                logging.info('APPLY : CREATE_AND_SELECT_WORKSPACE : %s : %r',
                             path,
                             create_and_select_workspace)

                logging.info('APPLY : CDKTF : %s : %r',
                             path,
                             workflow['cdktf'])

                if not workflow['cdktf'] and create_and_select_workspace:
                    env['TF_WORKSPACE'] = workspace

                env['TERRATEAM_TERRAFORM_VERSION'] = work_exec.determine_tf_version(
                    state.working_dir,
                    os.path.join(state.working_dir, path),
                    workflow['terraform_version'])

                state = state._replace(env=env)

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
                    'outputs': state.outputs.copy(),
                }

                return (state, result)
