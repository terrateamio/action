import json
import logging
import os
import subprocess

import cmd
import infracost
import retry
import workflow


INFRACOST_API_KEY = 'INFRACOST_API_KEY'
INFRACOST_CURRENCY = 'INFRACOST_CURRENCY'

TRIES = 3
INITIAL_SLEEP = 2
BACKOFF = 1.5


def _retry_test(c, ret):
    proc, output = ret
    logging.debug('INFRACOST : RETRY_TEST : %r', c)
    return (proc.returncode == 0 and 'level=error' not in output)


def _run_retry(state, c):
    proc, output = retry.run(
        lambda: cmd.run_with_output(state, {'cmd': c}),
        retry.finite_tries(TRIES, lambda ret: _retry_test(c, ret)),
        retry.betwixt_sleep_with_backoff(INITIAL_SLEEP, BACKOFF))

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(returncode=proc.returncode, cmd=c, output=output)

    return output


def _checkout_base(state):
    current_branch = subprocess.check_output(['git', 'branch', '--show-current'],
                                             cwd=state.working_dir)
    subprocess.check_call(['git', 'branch'], cwd=state.working_dir)
    # If they made any changes to the repo, stash it for now
    subprocess.call(['git', 'stash', 'push'])
    subprocess.check_call(['git', 'checkout', state.work_manifest['base_ref'], '--'],
                          cwd=state.working_dir)
    return current_branch.strip()


def _configure_infracost(state, config):
    env = state.env
    if INFRACOST_API_KEY in env:
        logging.info('INFRACOST : SETUP : PUBLIC_ENDPOINT')
        _run_retry(state,
                   ['infracost',
                    'configure',
                    'set',
                    'api_key',
                    env[INFRACOST_API_KEY].strip()])
    else:
        logging.info('INFRACOST : SETUP : SELF_HOSTED_ENDPOINT')
        _run_retry(state,
                   ['infracost',
                    'configure',
                    'set',
                    'pricing_api_endpoint',
                    state.api_base_url + '/infracost'])
        _run_retry(state,
                   ['infracost',
                    'configure',
                    'set',
                    'api_key',
                    state.work_token])

    _run_retry(state,
               ['infracost',
                'configure',
                'set',
                'currency',
                env.get(INFRACOST_CURRENCY, config['currency'])])


def _create_base_infracost(state, config, infracost_dir, infracost_json):
    current_branch = _checkout_base(state)
    try:
        infracost_config_yml = os.path.join(infracost_dir, 'config.yml')

        infracost.create_infracost_yml(infracost_config_yml, state.work_manifest['base_dirspaces'])

        _run_retry(state,
                   ['infracost',
                    'breakdown',
                    '--config-file={}'.format(infracost_config_yml),
                    '--format=json',
                    '--out-file={}'.format(infracost_json)])

    finally:
        subprocess.check_call(['git', 'checkout', current_branch, '--'], cwd=state.working_dir)
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

        output = _run_retry(state,
                            ['infracost',
                             'breakdown',
                             '--config-file={}'.format(infracost_config_yml),
                             '--format=json',
                             '--out-file={}'.format(curr_infracost)])

        _run_retry(state,
                   ['infracost',
                    'diff',
                    '--format=json',
                    '--path={}'.format(curr_infracost),
                    '--compare-to={}'.format(prev_infracost),
                    '--out-file={}'.format(diff_infracost)])

        if 'level=error' not in output:
            with open(diff_infracost) as f:
                diff = json.load(f)

            changed_dirspaces = set([(ds['path'], ds['workspace'])
                                     for ds in state.work_manifest['changed_dirspaces']])

            try:
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
            except Exception as exn:
                return workflow.Result(
                    failed=False,
                    state=state,
                    workflow_step={'type': 'cost-estimation'},
                    outputs={'text': str(exn)})
        else:
            return workflow.Result(failed=False,
                                   state=state,
                                   workflow_step={'type': 'cost-estimation'},
                                   outputs={'text': output})

    except subprocess.CalledProcessError as exn:
        logging.exception('INFRACOST : ERROR')
        logging.error('%s', exn.stdout)

        if exn.stdout is None:
            text = 'See action output'
        else:
            text = exn.stdout

        return workflow.Result(failed=False,
                               state=state,
                               workflow_step={'type': 'cost-estimation'},
                               outputs={'text': text})
