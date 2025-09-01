import json
import logging
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
            step='tf/opa',
            success=False)

    plan_show = os.path.join(state.tmpdir, 'opa.plan.json')
    with open(plan_show, 'w') as f:
        f.write(stdout)

    extra_args = config.get('extra_args', [])

    fail_on = config.get('fail_on', 'undefined')
    if fail_on == 'undefined':
        fail_on_opt = '--fail'
    elif fail_on == 'defined':
        fail_on_opt = '--fail-defined'

    res = workflow_step_run.run(
        state._replace(working_dir=working_dir),
        {
            'cmd': ['opa', 'eval', fail_on_opt, '--format', 'json', '--ignore', '.git', '-i', plan_show] + extra_args,
        })._replace(step='tf/opa')

    try:
        data = json.loads(res.payload['text'])
        res.payload['data'] = data
    except json.JSONDecodeError as exn:
        logging.exception(exn)

    return res
