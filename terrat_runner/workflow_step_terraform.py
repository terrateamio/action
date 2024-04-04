import os
import json

import cmd
import workflow_step_run
import workflow


TERRAFORM_BIN = 'terraform'
TOFU_BIN = 'tofu'


class SynthError(Exception):
    def __init__(self, msg):
        self.msg = msg
        super().__init__(msg)


def synth_cdktf(state, config):
    # (proc, get_output) = cmd.run_with_output(state, {'cmd': ['cdktf', 'get']})
    # if proc.returncode != 0:
    #     raise SynthError(get_output)

    (proc, synth_output) = cmd.run_with_output(state, {'cmd': ['cdktf', 'synth']})
    if proc.returncode != 0:
        raise SynthError(get_output + '\n' + synth_output)

    return get_output + '\n' + synth_output


def get_cdktf_working_dir(state):
    with open(os.path.join(state.working_dir, 'cdktf.out', 'manifest.json')) as f:
        manifest = json.loads(f.read())

    if state.workspace not in manifest['stacks']:
        raise SynthError('Stack {} not found'.format(state.workspace))

    stack_dir = manifest['stacks'][state.workspace]['workingDirectory']
    working_dir = os.path.join(state.working_dir, 'cdktf.out', stack_dir)
    return working_dir


def run_terraform(state, config):
    args = config['args']

    env = config.get('env', {})

    if state.workflow['engine']['name'] == 'terragrunt':
        cmd = ['terragrunt']
        env = env.copy()
        env['TERRAGRUNT_TFPATH'] = state.env['TERRATEAM_TF_CMD']
    else:
        cmd = ['${TERRATEAM_TF_CMD}']

    extra_args = config.get('extra_args', [])
    config = {
        'cmd': cmd + args + extra_args,
        'output_key': config.get('output_key'),
        'env': env,
    }
    return workflow_step_run.run(state, config)


def update_result_working_dir(result, working_dir):
    return result._replace(state=result.state._replace(working_dir=working_dir))


def run(state, config):
    working_dir = state.working_dir
    args = config['args']

    # If CDKTF is enabled, we need to synthesize the Terraform code and then
    # we'll run terraform in the output directory.  We'll then run the specified
    # stack.  If it does not exist, throw an error.  We look up the stack
    # directory and run Terraform and then switch back the directory to the
    # directory with the code, so the experience is seamless to the user.
    try:
        if state.workflow['engine']['name'] == 'cdktf' and args[0] == 'init':
            synth_cdktf(state, config)
            cdktf_working_dir = get_cdktf_working_dir(state)
            state = state._replace(working_dir=cdktf_working_dir)
            return update_result_working_dir(run_terraform(state, config), working_dir)
        elif state.workflow['engine']['name'] == 'cdktf':
            cdktf_working_dir = get_cdktf_working_dir(state)
            state = state._replace(working_dir=cdktf_working_dir)
            return update_result_working_dir(run_terraform(state, config), working_dir)
        else:
            return run_terraform(state, config)
    except SynthError as exn:
        return workflow.Result(failed=True,
                               state=state,
                               workflow_step={'type': 'run'},
                               outputs={'text': exn.msg})
