import json
import logging
import os
import re

import cmd
import engine


def format_diff(text):
    """Reformat diff markers for GitHub syntax highlighting.

    Moves +/-/~ from after indentation to start of line so GitHub's
    ```diff code fence colors them. Replaces ~ with ! for changed lines.
    Same approach as engine_tf.py.
    """
    s = re.sub(r'^(\s+)([+\-~])', r'\2\1', text, flags=re.MULTILINE)
    s = re.sub(r'^~', r'!', s, flags=re.MULTILINE)
    return s


def init(state, config):
    logging.info(
        'INIT : %s : engine=%s',
        state.path,
        state.workflow['engine']['name'])

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['pulumi', 'login'] + config.get('extra_args', [])
        })

    if proc.returncode != 0:
        return (False, stdout, stderr)

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['pulumi', 'stack', 'select', state.workspace]
        })

    return (proc.returncode == 0, stdout, stderr)


def apply(state, config):
    logging.info(
        'APPLY : %s : engine=%s',
        state.path,
        state.workflow['engine']['name'])

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['pulumi', 'up', '--yes', '--diff']
        })

    return (proc.returncode == 0, format_diff(stdout), stderr)


def diff(state, config):
    """Read the preview --diff output saved by plan() and format for GitHub highlighting."""
    diff_file = state.env['TERRATEAM_PLAN_FILE'] + '.diff'
    if os.path.exists(diff_file):
        with open(diff_file, 'r') as f:
            stdout = f.read()
        return (True, format_diff(stdout), '')
    return None


def diff_json(state, config):
    """Run pulumi preview -j for structured JSON diff data."""
    logging.info(
        'DIFF_JSON : %s : engine=%s',
        state.path,
        state.workflow['engine']['name'])

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['pulumi', 'preview', '-j']
        })

    if proc.returncode == 0:
        try:
            return (True, json.loads(stdout))
        except json.JSONDecodeError as exn:
            return (False, stdout, str(exn))

    return (False, stdout, stderr)


def plan(state, config):
    logging.info(
        'PLAN : %s : engine=%s',
        state.path,
        state.workflow['engine']['name'])

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['pulumi', 'preview', '--diff'] + config.get('extra_args', [])
        })

    with open(state.env['TERRATEAM_PLAN_FILE'], 'w') as f:
        f.write('{}')

    # Save preview output for diff() to pick up
    with open(state.env['TERRATEAM_PLAN_FILE'] + '.diff', 'w') as f:
        f.write(stdout)

    success = proc.returncode == 0
    change_indicators = ['to create', 'to update', 'to delete', 'to replace']
    has_changes = success and any(ind in stdout for ind in change_indicators)
    return (success, has_changes, stdout, stderr)


def unsafe_apply(state, config):
    logging.info(
        'UNSAFE_APPLY : %s : engine=%s',
        state.path,
        state.workflow['engine']['name'])

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['pulumi', 'up', '--yes']
        })

    return (proc.returncode == 0, stdout, stderr)


def outputs(state, config):
    """Collect stack outputs via pulumi stack output --json."""
    logging.info(
        'OUTPUTS : %s : engine=%s',
        state.path,
        state.workflow['engine']['name'])

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['pulumi', 'stack', 'output', '--json']
        })

    return (proc.returncode == 0, stdout, stderr)


def make():
    return engine.Engine(
        name='pulumi',
        init=init,
        apply=apply,
        plan=plan,
        diff=diff,
        diff_json=diff_json,
        unsafe_apply=unsafe_apply,
        outputs=outputs)
