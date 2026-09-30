import json
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
    # Cost and security analysis are opt-in: a step config that sets
    # extra_args replaces this default.
    plan_cmd += config.get('extra_args', ['--skip-costs', '--skip-security'])
    (proc, stdout, stderr) = cmd.run_with_output(state, {'cmd': plan_cmd})
    # --detailed-exitcode: 0 = no changes, 2 = changes, anything else = error.
    success = proc.returncode in [0, 2]
    has_changes = proc.returncode == 2
    return (success, has_changes, stdout, stderr)


def diff(state, config):
    logging.info('DIFF : %s : engine=stategraph', state.path)
    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['stategraph', 'tf', 'show', '${TERRATEAM_PLAN_FILE}']
        })

    # Stategraph renders the plan in the same format as `terraform show`, so
    # it is formatted the same way.
    if proc.returncode == 0:
        stdout = engine_tf.format_diff(stdout)

    return (proc.returncode == 0, stdout, stderr)


def diff_json(state, config):
    logging.info('DIFF_JSON : %s : engine=stategraph', state.path)
    # The JSON plan does not redact sensitive values, so keep it out of the
    # log.  Stategraph emits the same plan JSON representation as
    # `terraform show -json`.
    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['stategraph', 'tf', 'show', '--json', '${TERRATEAM_PLAN_FILE}'],
            'log_output': False
        })

    if proc.returncode == 0:
        try:
            return (True, json.loads(stdout))
        except json.JSONDecodeError as exn:
            return (False, stdout, str(exn))

    return (False, stdout, stderr)


def resource_summary(state, config):
    logging.info('RESOURCE_SUMMARY : %s : engine=stategraph', state.path)
    res = diff_json(state, config)
    # diff_json returns (True, plan_json) on success and a 3-tuple
    # (False, stdout, stderr) on failure.
    if len(res) != 2:
        return None

    (_success, plan_json) = res
    return engine_tf._resource_summary_from_plan_json(plan_json)


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
        resource_summary=resource_summary,
        unsafe_apply=unsafe_apply,
        outputs=outputs)
