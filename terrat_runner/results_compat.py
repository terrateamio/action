import math

# Implements compatibilty between result formats
RESULTS_VERSION = 2


def tuple_of_scope(scope):
    if scope['type'] == 'run':
        return ('flow:{}'.format(scope['flow']),
                'subflow:{}'.format(scope['subflow']))
    elif scope['type'] == 'dirspace':
        return ('dir:{}'.format(scope['dir']),
                'workspace:{}'.format(scope['workspace']))
    else:
        raise Exception('Unknown scope type: {}'.format(scope['type']))


def success(result):
    return result['success'] or result['ignore_errors']


def output_text_transform_to_1(result):
    step = result['step']
    if step == 'tf/apply':
        return {
            'output_key': 'apply',
            'text': result['payload'].get('text')
        }
    elif step == 'tf/init':
        return {
            'output_key': 'init',
            'text': result['payload'].get('text')
        }
    else:
        return {
            'text': result['payload'].get('text', '')
        }


def output_plan_transform_to_1(result):
    return {
        'has_changes': result['payload'].get('has_changes', True),
        'plan_text': result['payload']['plan'],
        'plan': result['payload']['text']
    }


def output_cost_estimation_transform_to_1(result):
    payload = result['payload']
    return {
        'cost_estimation': {
            'currency': payload['currency'],
            'diff_monthly_cost': payload['summary']['diff_monthly_cost'],
            'prev_monthly_cost': payload['summary']['prev_monthly_cost'],
            'total_monthly_cost': payload['summary']['total_monthly_cost'],
            'dirspaces': [
                {
                    'path': ds['dir'],
                    'workspace': ds['workspace'],
                    'diff_monthly_cost': ds['diff_monthly_cost'],
                    'prev_monthly_cost': ds['prev_monthly_cost'],
                    'total_monthly_cost': ds['total_monthly_cost']
                }
                for ds in payload['dirspaces']
                if not math.isclose(ds['diff_monthly_cost'], 0.0)
            ]
        }
    }


def workflow_step_transform_to_1(result):
    step = result['step']

    if step == 'run':
        return {
            'success': success(result),
            'workflow_step': {
                'cmd': result['payload']['cmd'],
                'exit_code': result['payload'].get('exit_code'),
                'type': 'run'
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'env':
        return {
            'success': success(result),
            'workflow_step': {
                'cmd': result['payload']['cmd'],
                'method': result['payload'].get('method'),
                'name': result['payload'].get('name'),
                'type': 'env'
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'checkout':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'checkout'
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'tf/cost-estimation':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'cost-estimation'
            },
            'outputs': (output_cost_estimation_transform_to_1(result)
                        if result['success']
                        else output_text_transform_to_1(result))
        }
    elif step == 'auth/oidc':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'oidc'
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'tf/apply':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'apply'
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'tf/init':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'run',
                'cmd': result['payload']['cmd'],
                'exit_code': result['payload'].get('exit_code')
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'tf/plan':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'plan'
            },
            'outputs': (output_plan_transform_to_1(result)
                        if result['success']
                        else output_text_transform_to_1(result))
        }
    elif step == 'tf/terrateam_ssh_key_setup':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'run',
                'cmd': ['terrateam_ssh_key_setup']
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'tf/tf_cloud_setup':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'run',
                'cmd': ['tf_cloud_setup']
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'tf/terraform':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'run',
                'cmd': result['payload']['cmd'],
                'exit_code': result['payload'].get('exit_code')
            },
            'outputs': output_text_transform_to_1(result)
        }
    elif step == 'tf/drift-create-issue':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'drift-create-issue',
            }
        }
    elif step == 'auth/update-terrateam-github-token':
        return {
            'success': success(result),
            'workflow_step': {
                'type': 'run',
                'cmd': ['update-terrateam-github-token']
            },
            'outputs': output_text_transform_to_1(result)
        }
    else:
        raise Exception('Unknown output step: {}'.format(step))


def dirspace_transform_to_1(scope, steps):
    return {
        'path': scope['dir'],
        'workspace': scope['workspace'],
        'success': all(success(o) for o in steps),
        'outputs': [workflow_step_transform_to_1(o) for o in steps]
    }


def transform_to_1(state, results):
    dirspaces = {}
    for o in results['steps']:
        if o['scope']['type'] == 'dirspace':
            dirspaces.setdefault(tuple_of_scope(o['scope']), []).append(o)

    return {
        'overall': {
            'success': all(success(o) for o in results['steps']),
            'outputs': {
                'pre': [workflow_step_transform_to_1(o) for o in results['steps']
                        if o['scope'] == {'type': 'run', 'flow': 'hooks', 'subflow': 'pre'}],
                'post': [workflow_step_transform_to_1(o) for o in results['steps']
                         if o['scope'] == {'type': 'run', 'flow': 'hooks', 'subflow': 'post'}]
                },
        },
        'dirspaces': [dirspace_transform_to_1(steps[0]['scope'], steps)
                      for steps in dirspaces.values()]
    }


def transform_to(state, current_results_version, desired_results_version, results):
    if current_results_version == desired_results_version:
        return results
    elif current_results_version == 2:
        return transform_to(state, 1, desired_results_version, transform_to_1(state, results))
    else:
        raise Exception('Unknown results version {} -> {}'.format(current_results_version,
                                                                  desired_results_version))


def transform(state, results):
    return transform_to(state, RESULTS_VERSION, state.result_version, results)
