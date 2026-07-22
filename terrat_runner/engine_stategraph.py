import logging
import os

import cmd
import engine
import engine_tf


def _run(state, cmd_list):
    (proc, stdout, stderr) = cmd.run_with_output(state, {'cmd': cmd_list})
    return (proc.returncode == 0, stdout, stderr)


def init(state, config):
    """Preflight: verify env vars and stategraph.json + connectivity."""
    logging.info('INIT : %s : engine=stategraph', state.path)
    for required in ('STATEGRAPH_API_BASE', 'STATEGRAPH_API_KEY', 'STATEGRAPH_TENANT_ID'):
        if not state.env.get(required):
            return (False, '',
                    'Required env var %s is not set. Set this in your runner secrets.' % required)
    if not os.path.exists(os.path.join(state.working_dir, 'stategraph.json')):
        return (False, '',
                'No stategraph.json found in %s. Run `stategraph states create` or '
                '`stategraph import tf` and commit the result before opening a PR.'
                % state.working_dir)
    return _run(state, ['stategraph', 'info'])


def plan(state, config):
    logging.info('PLAN : %s : engine=stategraph', state.path)
    plan_cmd = ['stategraph', 'tf', 'plan',
                '--out', '${TERRATEAM_PLAN_FILE}',
                '--detailed-exitcode',
                '--workspace', state.workspace]
    plan_cmd += config.get('extra_args', [])
    (proc, stdout, stderr) = cmd.run_with_output(state, {'cmd': plan_cmd})
    # --detailed-exitcode: 0 = no changes, 2 = changes, anything else = error.
    success = proc.returncode in [0, 2]
    has_changes = proc.returncode == 2
    return (success, has_changes, stdout, stderr)


def diff(state, config):
    return None


def diff_json(state, config):
    # `stategraph tf show --json PLAN` emits the plan as a standard
    # `terraform show -json` document (resource_changes), so the server can
    # compute exact change counts.  The API base and credentials come from the
    # STATEGRAPH_* environment.
    logging.info('DIFF_JSON : %s : engine=stategraph', state.path)
    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['stategraph', 'tf', 'show', '--json', '${TERRATEAM_PLAN_FILE}']
        })

    if proc.returncode == 0:
        doc = engine_tf.parse_show_json(stdout)
        if doc is not None:
            return (True, doc)
        return (False, stdout, 'could not parse stategraph tf show --json output')

    return (False, stdout, stderr)


def apply(state, config):
    logging.info('APPLY : %s : engine=stategraph', state.path)
    return _run(state,
                ['stategraph', 'tf', 'apply', '${TERRATEAM_PLAN_FILE}']
                + config.get('extra_args', []))


def unsafe_apply(state, config):
    logging.info('UNSAFE_APPLY : %s : engine=stategraph', state.path)
    return apply(state, config)


def outputs(state, config):
    return None


def make(**engine_config):
    return engine.Engine(
        name='stategraph',
        init=init,
        apply=apply,
        plan=plan,
        diff=diff,
        diff_json=diff_json,
        unsafe_apply=unsafe_apply,
        outputs=outputs)
