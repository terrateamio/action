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

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
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
            step='tf/checkov',
            success=False)

    plan_show = os.path.join(state.tmpdir, 'checkov.plan.json')
    with open(plan_show, 'w') as f:
        f.write(stdout)

    extra_args = config.get('extra_args')
    if extra_args:
        return workflow_step_run.run(
            state,
            {
                'cmd': ['checkov'] + extra_args + ['-f', plan_show],
            })._replace(step='tf/checkov')
    else:
        return workflow_step_run.run(
            state,
            {
                'cmd': ['checkov', '--quiet', '--compact', '-f', plan_show],
            })._replace(step='tf/checkov')
