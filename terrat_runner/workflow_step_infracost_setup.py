import json
import logging
import os
import subprocess

import infracost
import retry
import workflow


INFRACOST_API_KEY = 'INFRACOST_API_KEY'
INFRACOST_CURRENCY = 'INFRACOST_CURRENCY'

TRIES = 3
INITIAL_SLEEP = 2
BACKOFF = 1.5


def _dedup_infracost_projects(breakdown_fname):
    """We need to remove any deuplicates from the projects section.  This is
    because Infracost recursively processes the directories, but we specify each
    specific directory we want to process.  The infracost CLI doesn't figure out
    that it is doing double work on its own.  The file produced in a breakdown
    cannot be used in a diff because the diff assumes that all projects are
    unique.

    What's unclear is if we also need to manipualte the summary section.  It
    looks like "no", but who knows.

    """
    with open(breakdown_fname) as f:
        breakdown = json.loads(f.read())

    projects = {
        (p['metadata']['path'], p['metadata']['terraformWorkspace']): p
        for p in breakdown['projects']
    }
    breakdown['projects'] = list(projects.values())

    with open(breakdown_fname, 'w') as f:
        f.write(json.dumps(breakdown))


def _run_retry(cmd, *args, **kwargs):
    ret = retry.run(
        lambda: subprocess.run(cmd, *args, **kwargs),
        retry.finite_tries(TRIES, lambda ret: ret.returncode == 0),
        retry.betwixt_sleep_with_backoff(INITIAL_SLEEP, BACKOFF))

    if ret.returncode != 0:
        raise subprocess.CalledProcessError(ret.returncode, cmd, ret.stdout, ret.stderr)

    return ret


def _checkout_base(state):
    base_branch = subprocess.check_output(['git', 'branch', '--show-current'],
                                          cwd=state.working_dir)
    subprocess.check_call(['git', 'branch'], cwd=state.working_dir)
    # If they made any changes to the repo, stash it for now
    subprocess.call(['git', 'stash', 'push'])
    subprocess.check_call(['git', 'checkout', state.work_manifest['base_ref'], '--'],
                          cwd=state.working_dir)
    return base_branch.strip()


def _configure_infracost(state, config):
    env = state.env
    if INFRACOST_API_KEY in env:
        logging.info('INFRACOST : SETUP : PUBLIC_ENDPOINT')
        _run_retry(['infracost',
                    'configure',
                    'set',
                    'api_key',
                    env[INFRACOST_API_KEY].strip()])
    else:
        logging.info('INFRACOST : SETUP : SELF_HOSTED_ENDPOINT')
        _run_retry(['infracost',
                    'configure',
                    'set',
                    'pricing_api_endpoint',
                    state.api_base_url + '/infracost'])
        _run_retry(['infracost',
                    'configure',
                    'set',
                    'api_key',
                    state.work_token])

    _run_retry(['infracost',
                'configure',
                'set',
                'currency',
                env.get(INFRACOST_CURRENCY, config['currency'])])


def _create_base_infracost(state, config, infracost_dir, infracost_json):
    base_branch = _checkout_base(state)
    try:
        infracost_config_yml = os.path.join(infracost_dir, 'config.yml')

        infracost.create_infracost_yml(infracost_config_yml, state.work_manifest['base_dirspaces'])

        ret = _run_retry(['infracost',
                          'breakdown',
                          '--config-file={}'.format(infracost_config_yml),
                          '--format=json',
                          '--out-file={}'.format(infracost_json)],
                         cwd=state.working_dir,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)

        output = ret.stdout.decode('utf-8')

        _dedup_infracost_projects(infracost_json)

        for line in output.splitlines():
            logging.info('INFRACOST : SETUP : %s', line)

    finally:
        subprocess.check_call(['git', 'checkout', base_branch, '--'], cwd=state.working_dir)
        subprocess.call(['git', 'stash', 'pop'])


def run(state, config):
    infracost_dir = os.path.join(state.tmpdir, 'infracost')
    os.makedirs(infracost_dir, exist_ok=True)

    prev_infracost = os.path.join(infracost_dir, 'infracost-prev.json')
    curr_infracost = os.path.join(infracost_dir, 'infracost.json')
    diff_infracost = os.path.join(infracost_dir, 'infracost-diff.json')
    infracost_config_yml = os.path.join(infracost_dir, 'config.yml')

    try:
        logging.info('INFRACOST : SETUP')
        _configure_infracost(state, config)

        _create_base_infracost(state, config, infracost_dir, prev_infracost)

        infracost.create_infracost_yml(infracost_config_yml, state.work_manifest['dirspaces'])

        ret = _run_retry(['infracost',
                          'breakdown',
                          '--config-file={}'.format(infracost_config_yml),
                          '--format=json',
                          '--out-file={}'.format(curr_infracost)],
                         cwd=state.working_dir,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)

        output = ret.stdout.decode('utf-8')

        for line in output.splitlines():
            logging.info('INFRACOST : SETUP : %s', line)

        _dedup_infracost_projects(curr_infracost)

        diff_ret = _run_retry(['infracost',
                               'diff',
                               '--format=json',
                               '--path={}'.format(curr_infracost),
                               '--compare-to={}'.format(prev_infracost),
                               '--out-file={}'.format(diff_infracost)],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)

        diff_output = diff_ret.stdout.decode('utf-8')

        for line in diff_output.splitlines():
            logging.info('INFRACOST : SETUP : %s', line)

        if 'level=error' not in output:
            with open(diff_infracost) as f:
                diff = json.load(f)

        changed_dirspaces = set([(ds['path'], ds['workspace'])
                                 for ds in state.work_manifest['changed_dirspaces']])

        dirspaces = [
            {
                'path': p['metadata']['path'],
                'workspace': p['metadata']['terraformWorkspace'],
                'prev_monthly_cost': infracost.convert_cost(p['pastBreakdown']['totalMonthlyCost']),
                'total_monthly_cost': infracost.convert_cost(p['breakdown']['totalMonthlyCost']),
                'diff_monthly_cost': infracost.convert_cost(p['diff']['totalMonthlyCost'])
            }
            for p in diff['projects']
            if (p['metadata']['path'], p['metadata']['terraformWorkspace']) in changed_dirspaces
        ]

        return workflow.Result(
            failed=False,
            state=state,
            workflow_step={'type': 'cost-estimation'},
            outputs={
                'cost_estimation': {
                    'prev_monthly_cost': infracost.convert_cost(diff['pastTotalMonthlyCost']),
                    'total_monthly_cost': infracost.convert_cost(diff['totalMonthlyCost']),
                    'diff_monthly_cost': infracost.convert_cost(diff['diffTotalMonthlyCost']),
                    'currency': diff['currency'],
                    'dirspaces': dirspaces
                },
            })
    except subprocess.CalledProcessError as exn:
        logging.exception('INFRACOST : ERROR')
        logging.error('%s', exn.stdout)

        if exn.stdout is None:
            text = 'See action output'
        else:
            text = exn.stdout.decode('utf-8')

        return workflow.Result(failed=False,
                               state=state,
                               workflow_step={'type': 'cost-estimation'},
                               outputs={'text': text})
