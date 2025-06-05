import logging

import cmd


class Engine:
    def __init__(self,
                 name,
                 init_args,
                 apply_args,
                 diff_args,
                 plan_args,
                 unsafe_apply_args,
                 outputs_args):
        self.name = name
        self.init_args = init_args
        self.apply_args = apply_args
        self.diff_args = diff_args
        self.plan_args = plan_args
        self.unsafe_apply_args = unsafe_apply_args
        self.outputs_args = outputs_args

    def init(self, state, config):
        logging.info(
            'INIT : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        if self.init_args:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.init_args + config.get('extra_args', [])
                })

            return (proc.returncode == 0, stdout.strip(), stderr.strip())
        else:
            return (True, '', '')

    def apply(self, state, config):
        logging.info(
            'APPLY : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        if self.apply_args:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.apply_args + config.get('extra_args', [])
                })

            return (proc.returncode == 0, stdout.strip(), stderr.strip())
        else:
            return (True, '', '')

    def diff(self, state, config):
        if self.diff_args:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.diff_args
                })

            return (proc.returncode == 0, stdout.strip(), stderr.strip())
        else:
            return None

    def plan(self, state, config):
        logging.info(
            'PLAN : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        if self.plan_args:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.plan_args + config.get('extra_args', [])
                })

            return (proc.returncode in [0, 2], proc.returncode == 0, stdout.strip(), stderr.strip())
        else:
            return (True, False, '', '')

    def unsafe_apply(self, state, config):
        logging.info(
            'UNSAFE_APPLY : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        if self.unsafe_apply_args:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.unsafe_apply_args + config.get('extra_args', [])
                })

            return (proc.returncode == 0, stdout.strip(), stderr.strip())
        else:
            return (True, '', '')

    def outputs(self, state, config):
        logging.info(
            'UNSAFE_APPLY : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        if self.outputs_args:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.outputs_args
                })

            return (proc.returncode == 0, stdout.strip(), stderr.strip())
        else:
            return None


def make(**kwargs):
    return Engine(name='custom', **kwargs)
