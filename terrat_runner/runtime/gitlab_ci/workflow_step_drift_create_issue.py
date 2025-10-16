import hashlib
import json
import logging
import os

import requests_retry
import workflow


TITLE = 'Terrateam: Drift Detected'

ISSUE_HEADER = '''
## Terrateam Drift Detection Report
**Terrateam detected drift against live infrastructure.**

Create a new pull request to reconcile differences or enable automatic reconciliation using the Terrateam configuration file. See [Drift Detection](https://terrateam.io/docs/features/drift-detection) documentation for details.

## Terrateam Plan Output
'''

SUCCESS_OUTPUT = '''
<details>
<summary>Directory: {dir} | Workspace: {workspace}</summary>

```
{plan}
```

</details>
'''

FAILURE_OUTPUT = '''
<details>
<summary>Directory: {dir} | Workspace: {workspace}</summary>

Running the plan failed, please see the action output for details

</details>
'''


def format_dirspace_output(directory, workspace, plan, success):
    if success:
        msg = SUCCESS_OUTPUT
    else:
        msg = FAILURE_OUTPUT

    return msg.format(dir=directory, workspace=workspace, plan=plan)


def extract_dirspace_plans(fname):
    with open(fname) as f:
        data = json.load(f)

    ret = []

    for step in data['steps']:
        if step['step'] == 'tf/plan' and step['payload'].get('has_changes'):
            payload = step['payload']
            ret.append({
                'dir': step['scope']['dir'],
                'workspace': step['scope']['workspace'],
                'plan': payload.get('plan', ''),
                'has_changes': payload['has_changes'],
                'success': step['success']
            })

    return ret


def format_dirspaces(dirspace_plans):
    return '\n'.join([format_dirspace_output(v['dir'], v['workspace'], v['plan'], v['success'])
                      for v in dirspace_plans])


def format_issue_body(all_dirspace_plan_output, report_id):
    return ('''
{header}
{output}
---
Report ID: {report_id}
'''.format(header=ISSUE_HEADER, output=all_dirspace_plan_output, report_id=report_id))


def drift_output_too_long(env, report_id):
    return ('''
{header}
Drift output too large to display.
---
Report ID: {report_id}
''').format(header=ISSUE_HEADER,
            repo=env['GITHUB_REPOSITORY'],
            run_id=env['GITHUB_RUN_ID'],
            report_id=report_id)


def find_matching_issue(env, report_id):
    # We'll set labels for an issues to make it easier to track and the
    # description will have the report id
    url = '{server_url}/api/v4/projects/{project_id}/issues?labels=terrateam,drift&state=opened&search={report_id}'.format(
        server_url=env['CI_SERVER_URL'],
        project_id=env['CI_PROJECT_ID'],
        report_id=report_id)
    headers = {
        'User-Agent': 'Terrateam Action',
        'Authorization': 'bearer ' + env['TERRATEAM_DRIFT_ACCESS_TOKEN']
    }
    ret = requests_retry.get(url, headers=headers)

    issues = ret.json()
    if issues:
        return issues[0]
    else:
        return None


def compact_issue_body(issue_body):
    return '\n'.join([
        line
        for line in issue_body.splitlines()
        if ' Refreshing state...' not in line and '= (known after apply)' not in line
    ])


def body_is_too_long(body):
    errors = body.get('errors', [])
    for err in errors:
        if 'message' in err and err['message'].startswith('body is too long'):
            return True

    return False


def create_issue(state, report_id, issue_body, compact_view=False):
    if compact_view:
        issue_body = compact_issue_body(issue_body)

    url = '{server_url}/api/v4/projects/{project_id}/issues'.format(
        server_url=state.env['CI_SERVER_URL'],
        project_id=state.env['CI_PROJECT_ID'])
    headers = {
        'User-Agent': 'Terrateam Action',
        'Authorization': 'bearer ' + state.env['TERRATEAM_DRIFT_ACCESS_TOKEN']
    }
    issue = {
        'title': TITLE,
        'description': issue_body,
        'labels': 'terrateam,drift'
    }
    ret = requests_retry.post(url, headers=headers, json=issue)
    if ret.status_code == 201:
        logging.info('DRIFT_CREATE_ISSUE : SUCCESS')
    elif ret.status_code == 422 and body_is_too_long(ret.json()) and not compact_view:
        return create_issue(state, report_id, issue_body, compact_view=True)
    elif ret.status_code == 422 and body_is_too_long(ret.json()):
        return create_issue(state, report_id, drift_output_too_long(state.env, report_id))
    else:
        logging.error('Failed to make issue: %s', ret.text)
        raise Exception('Failed to make issue')


def maybe_create_issue(state):
    run_kind = state.env['TERRATEAM_RUN_KIND']
    results_file = state.env['TERRATEAM_RESULTS_FILE']
    all_dirspace_plan_output = ''
    if run_kind == 'drift' and os.path.isfile(results_file):
        dirspaces_with_changes = extract_dirspace_plans(state.env['TERRATEAM_RESULTS_FILE'])
        if dirspaces_with_changes:
            all_dirspace_plan_output = format_dirspaces(dirspaces_with_changes)
            report_id = hashlib.md5(all_dirspace_plan_output.encode('utf-8')).hexdigest()

            existing_issue = find_matching_issue(state.env, report_id)
            if existing_issue:
                logging.info('DRIFT_CREATE_ISSUE : ISSUE_EXISTS : %s', existing_issue['id'])
            else:
                issue_body = format_issue_body(all_dirspace_plan_output, report_id)
                create_issue(state, report_id, issue_body)


def run(state, config):
    maybe_create_issue(state)
    return workflow.make(success=True,
                         state=state,
                         step='tf/drift-create-issue',
                         payload={})
