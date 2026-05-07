import logging
import os

import cmd
import engine


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
                '--workspace', state.workspace]
    plan_cmd += config.get('extra_args', [])
    (success, stdout, stderr) = _run(state, plan_cmd)
    has_changes = success and 'No changes detected.' not in stdout
    return (success, has_changes, stdout, stderr)


def diff(state, config):
    return None


def diff_json(state, config):
    return None


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
