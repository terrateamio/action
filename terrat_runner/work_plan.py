import logging
import os
import tempfile

import repo_config as rc
import work_exec
import workflow_step
import workflow_step_terrateam_ssh_key_setup


def _merge_integrations(state, steps, integrations):
    if state.work_manifest.get('run_kind') == 'pr' and integrations['resourcely']['enabled']:
        steps = steps + [{
            'type': 'resourcely',
            'extra_args': integrations['resourcely'].get('extra_args', [])
        }]

    return steps


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
                        'currency': cost_estimation_config['currency'],
                        'ignore_errors': True
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

            plan_file = os.path.join(tmpdir, 'plan')

            env = state.env.copy()
            env['TERRATEAM_PLAN_FILE'] = plan_file
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

            logging.info('PLAN : CREATE_AND_SELECT_WORKSPACE : %s : %r',
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

            plan_steps = _merge_integrations(state, workflow['plan'], workflow['integrations'])

            state = workflow_step.run_steps(
                state._replace(working_dir=os.path.join(state.working_dir, path),
                               path=path,
                               workspace=workspace,
                               workflow=workflow),
                {'type': 'dirspace', 'dir': path, 'workspace': workspace},
                state.runtime.update_workflow_steps('plan', plan_steps))

            result = {
                'path': path,
                'workspace': workspace,
                'success': state.success,
                'outputs': state.outputs.copy(),
            }

            return (state, result)
