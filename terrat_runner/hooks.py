# Hooks are a restricted set of workflow steps that are executed before or after
# all directories are executed
import workflow_step


def run_hooks(state, scope, steps):
    return workflow_step.run_steps(state,
                                   {
                                       'type': 'run',
                                       'flow': 'hooks',
                                       'subflow': scope
                                   },
                                   steps)


def run_pre_hooks(state, hooks):
    return run_hooks(state, 'pre', hooks)


def run_post_hooks(state, hooks):
    return run_hooks(state, 'post', hooks)
