import json
import logging

import cmd


class Engine:
    def __init__(self,
                 name,
                 init_args,
                 apply_args,
                 diff_args,
                 diff_json_args,
                 resource_summary_args,
                 plan_args,
                 unsafe_apply_args,
                 outputs_args):
        self.name = name
        self.init_args = init_args
        self.apply_args = apply_args
        self.diff_args = diff_args
        self.diff_json_args = diff_json_args
        self.resource_summary_args = resource_summary_args
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
        logging.info(
            'DIFF : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        if self.diff_args:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.diff_args
                })

            return (proc.returncode == 0, stdout.strip(), stderr.strip())
        else:
            return None

    def diff_json(self, state, config):
        logging.info(
            'DIFF_JSON : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        if self.diff_json_args:
            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {
                    'cmd': self.diff_json_args
                })

            if proc.returncode == 0:
                try:
                    return (True, json.loads(stdout))
                except json.JSONDecodeError as exn:
                    return (False, stdout, str(exn))
            else:
                return (False, stdout.strip(), stderr.strip())
        else:
            return None

    def resource_summary(self, state, config):
        # Run the custom summary program.  The program prints JSON with the
        # same shape as the tf resource_summary result: one object with the
        # keys 'created', 'updated', 'deleted', and 'replaced', each an
        # integer count.  If the program is not set, or it fails, or its
        # output is not a JSON object, return None so the plan step drops the
        # summary.
        if not self.resource_summary_args:
            return None

        logging.info(
            'RESOURCE_SUMMARY : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': self.resource_summary_args
            })

        if proc.returncode != 0:
            return None

        try:
            summary = json.loads(stdout)
        except json.JSONDecodeError as exn:
            logging.warning(
                'RESOURCE_SUMMARY : %s : engine=%s : bad JSON output: %s',
                state.path,
                state.workflow['engine']['name'],
                str(exn))
            return None

        if not isinstance(summary, dict):
            logging.warning(
                'RESOURCE_SUMMARY : %s : engine=%s : output is not a JSON object',
                state.path,
                state.workflow['engine']['name'])
            return None

        return summary

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
