import json
import logging
import os

import cmd
import workflow


def run(state, config):
    # Errors will always be ignored for gates.
    config['ignore_errors'] = True

    if state.env.get('TERRATEAM_ENGINE_NAME') == 'cdktf':
        working_dir = os.path.join(state.working_dir, 'cdktf.out', 'stacks', state.workspace)
    else:
        working_dir = state.working_dir

    (proc, stdout, stderr) = cmd.run_with_output(
        state._replace(working_dir=working_dir),
        {
            'cmd': config['cmd'],
        })

    if proc.returncode == 0:
        try:
            data = json.loads(stdout)
            on_error = config.setdefault('on_error', [])
            add_reviewers = set()
            for g in data['gates']:
                on_error.append({
                    'all_of': g.get('all_of', []),
                    'any_of': g.get('any_of', []),
                    'any_of_count': g.get('any_of_count', 0),
                    'token': g.get('token'),
                    'name': g.get('name'),
                    'type': 'gate',
                })

                if g.get('add_reviewers', True):
                    for r in g.get('all_of', []) + g.get('any_of', []):
                        add_reviewers.add(r)

            state.runtime.add_reviewers(state.env, add_reviewers)

            # Setting gates requires that the workflow step has failed.
            return workflow.make(
                payload={
                    'visible_on': 'error'
                },
                state=state,
                step='gates',
                success=False)

        except json.JSONDecodeError as exn:
            return workflow.make(
                payload={
                    'text': '\n'.join([stderr, stdout]),
                    'visible_on': 'error'
                },
                state=state,
                step='gates',
                success=False)
    else:
        return workflow.make(
            payload={
                'text': '\n'.join([stderr, stdout]),
                'visible_on': 'error'
                },
            state=state,
            step='gates',
            success=False)
