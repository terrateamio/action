# Hooks are a restricted set of workflow steps that are executed before or after
# all directories are executed
import workflow_step


ALLOWED_HOOK_STEPS = [
    'drift_create_issue',
    'env',
    'infracost_setup',
    'oidc',
    'run',
    'terrateam_ssh_key_setup',
    'tf_cloud_setup',
]


def run_hooks(state, steps):
    return workflow_step.run_steps(state, steps, restrict_types=ALLOWED_HOOK_STEPS)


def run_pre_hooks(state, hooks):
    return run_hooks(state, hooks)


def run_post_hooks(state, hooks):
    return run_hooks(state, hooks)
