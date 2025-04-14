import json
import os

import cmd
import engine_tf


def get_cdktf_working_dir(state):
    with open(os.path.join(state.working_dir, 'cdktf.out', 'manifest.json')) as f:
        manifest = json.loads(f.read())

    if state.workspace not in manifest['stacks']:
        return None

    stack_dir = manifest['stacks'][state.workspace]['workingDirectory']
    working_dir = os.path.join(state.working_dir, 'cdktf.out', stack_dir)
    return working_dir


def _run(state, config, f):
    working_dir = get_cdktf_working_dir(state)
    if working_dir is None:
        return (False, '', 'Stack {} not found'.format(state.workspace))

    state = state._replace(working_dir=working_dir)
    return f(state, config)


class Engine:
    def __init__(self):
        self.name = 'tf'
        self.engine_tf = engine_tf.make()

    def init(self, state, config):
        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': ['cdktf', 'get']
            })

        if proc.returncode != 0:
            return (False, stdout, stderr)

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': ['cdktf', 'synth']
            })

        if proc.returncode != 0:
            return (False, stdout, stderr)

        return _run(state,
                    config,
                    lambda state, config: self.engine_tf.init(state,
                                                              config,
                                                              create_and_select_workspace=False))

    def apply(self, state, config):
        return _run(state, config, self.engine_tf.apply)

    def diff(self, state, config):
        return _run(state, config, self.engine_tf.diff)

    def plan(self, state, config):
        return _run(state, config, self.engine_tf.plan)

    def unsafe_apply(self, state, config):
        return _run(state, config, self.engine_tf.unsafe_apply)

    def outputs(self, state, config):
        return _run(state, config, self.engine_tf.outputs)


def make():
    return Engine()
