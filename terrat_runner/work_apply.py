import logging
import os
import tempfile

import repo_config as rc
import work_exec
import workflow_step
import workflow_step_terrateam_ssh_key_setup


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

            work_exec.set_engine_env(
                env,
                state.repo_config,
                workflow['engine'],
                state.working_dir,
                os.path.join(state.working_dir, path))

            state = state._replace(env=env,
                                   engine=work_exec.convert_engine(workflow['engine']))

            state = workflow_step.run_steps(
                state._replace(working_dir=os.path.join(state.working_dir, path),
                               path=path,
                               workspace=workspace,
                               workflow=workflow),
                {'type': 'dirspace', 'dir': path, 'workspace': workspace},
                state.runtime.update_workflow_steps('apply', workflow['apply']))

            result = {
                'path': path,
                'workspace': workspace,
                'success': state.success,
                'outputs': state.outputs.copy(),
            }

            return (state, result)
