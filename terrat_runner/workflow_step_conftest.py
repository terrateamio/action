import os

import cmd
import workflow

import workflow_step_run


def run(state, config):
    # Not the best, but we modify the config so workflow_step will automatically
    # handle our gate
    if 'gate' in config:
        gate = config['gate']
        gate['type'] = 'gate'
        config.setdefault('on_error', []).append(gate)
        config['ignore_errors'] = True

    if state.env.get('TERRATEAM_ENGINE_NAME') == 'cdktf':
        working_dir = os.path.join(state.working_dir, 'cdktf.out', 'stacks', state.workspace)
    else:
        working_dir = state.working_dir

    (proc, stdout, stderr) = cmd.run_with_output(
        state._replace(working_dir=working_dir),
        {
            'cmd': ['${TERRATEAM_TF_CMD}', 'show', '-json', '${TERRATEAM_PLAN_FILE}'],
            'log_output': False,
        })

    if proc.returncode != 0:
        return workflow.make(
            payload={
                'text': '\n'.join([stderr, stdout]),
                'visible_on': 'error',
            },
            state=state,
            step='tf/conftest',
            success=False)

    plan_show = os.path.join(state.tmpdir, 'conftest.plan.json')
    with open(plan_show, 'w') as f:
        f.write(stdout)

    extra_args = config.get('extra_args', [])
    return workflow_step_run.run(
        state._replace(working_dir=working_dir),
        {
            'cmd': ['conftest', 'test', '--ignore', '.git'] + extra_args + [plan_show],
        })._replace(step='tf/conftest')
