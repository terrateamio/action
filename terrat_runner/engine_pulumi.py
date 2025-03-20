import logging

import cmd
import engine


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
            'cmd': ['pulumi', 'up', '--yes']
        })

    return (proc.returncode == 0, stdout, stderr)


def diff(state, config):
    return None


def plan(state, config):
    logging.info(
        'PLAN : %s : engine=%s',
        state.path,
        state.workflow['engine']['name'])

    (proc, stdout, stderr) = cmd.run_with_output(
        state,
        {
            'cmd': ['pulumi', 'preview'] + config.get('extra_args', [])
        })

    with open(state.env['TERRATEAM_PLAN_FILE'], 'w') as f:
        f.write('{}')

    return (proc.returncode == 0, stdout, stderr)


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
    logging.info(
        'OUTPUTS : %s : engine=%s',
        state.path,
        state.workflow['engine']['name'])

    return None


def make():
    return engine.Engine(
        name='pulumi',
        init=init,
        apply=apply,
        plan=plan,
        diff=diff,
        unsafe_apply=unsafe_apply)
