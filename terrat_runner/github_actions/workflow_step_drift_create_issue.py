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

    for ds in data['dirspaces']:
        for output in ds['outputs']:
            if output['workflow_step']['type'] == 'plan' and output['outputs']:
                ret.append({
                    'dir': ds['path'],
                    'workspace': ds['workspace'],
                    'plan': output['outputs'].get('plan_text', output['outputs'].get('plan')),
                    'has_changes': output['outputs'].get('has_changes'),
                    'success': ds['success']
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


def find_matching_issue(env, report_id):
    report_id_line = 'Report ID: ' + report_id
    url = 'https://api.github.com/repos/{repo}/issues'.format(
        repo=env['GITHUB_REPOSITORY'])
    headers = {
        'User-Agent': 'Terrateam Action',
        'X-GitHub-Api-Version': '2022-11-28',
        'Authorization': 'token ' + env['TERRATEAM_GITHUB_TOKEN']
    }
    ret = requests_retry.get(url, headers=headers)
    for issue in ret.json():
        if issue['title'] == 'Terrateam: Drift Detected':
            if report_id_line in issue['body']:
                return issue


def maybe_create_issue(state):
    run_kind = state.env['TERRATEAM_RUN_KIND']
    results_file = state.env['TERRATEAM_RESULTS_FILE']
    all_dirspace_plan_output = ''
    if run_kind == 'drift' and os.path.isfile(results_file):
        dirspace_plans = extract_dirspace_plans(state.env['TERRATEAM_RESULTS_FILE'])
        dirspaces_with_changes = [d for d in dirspace_plans if d['has_changes']]
        if dirspaces_with_changes:
            all_dirspace_plan_output = format_dirspaces(dirspaces_with_changes)
            report_id = hashlib.md5(all_dirspace_plan_output.encode('utf-8')).hexdigest()

            state = state.run_time.update_authentication(state)

            existing_issue = find_matching_issue(state.env, report_id)
            if existing_issue:
                logging.info('DRIFT_CREATE_ISSUE : ISSUE_EXISTS : %s', existing_issue['id'])
            else:
                issue_body = format_issue_body(all_dirspace_plan_output, report_id)
                url = 'https://api.github.com/repos/{repo}/issues'.format(repo=state.env['GITHUB_REPOSITORY'])
                headers = {
                    'User-Agent': 'Terrateam Action',
                    'Authorization': 'token ' + state.env['TERRATEAM_GITHUB_TOKEN']}
                issue = {
                    'title': TITLE,
                    'body': issue_body
                }
                ret = requests_retry.post(url, headers=headers, json=issue)
                if ret.status_code != 201:
                    logging.error('Failed to make issue: %s', ret.text)
                    raise Exception('Failed to make issue')


def run(state, config):
    maybe_create_issue(state)
    return workflow.Result(failed=False,
                           state=state,
                           workflow_step={'type': 'drift-create-issue'},
                           outputs=None)
