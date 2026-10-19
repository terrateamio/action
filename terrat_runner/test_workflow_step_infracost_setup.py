import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import workflow_step_infracost_setup


class DiffLogTest(unittest.TestCase):
    DIFF = {
        'currency': 'USD',
        'pastTotalMonthlyCost': '1',
        'totalMonthlyCost': '2',
        'diffTotalMonthlyCost': '1',
        'projects': [
            {
                'metadata': {'path': 'dev', 'terraformWorkspace': 'default'},
                'pastBreakdown': {'totalMonthlyCost': '1'},
                'breakdown': {
                    'totalMonthlyCost': '2',
                    'resources': [{'name': 'aws_instance.secret_name'}],
                },
                'diff': {'totalMonthlyCost': '1'},
            }
        ],
    }

    def _log(self, config):
        with tempfile.TemporaryDirectory() as tmpdir:
            infracost_dir = os.path.join(tmpdir, 'infracost')
            os.makedirs(infracost_dir)
            with open(os.path.join(infracost_dir, 'infracost-diff.json'), 'w') as f:
                json.dump(self.DIFF, f)
            config_yml = os.path.join(infracost_dir, 'config.yml')
            with open(config_yml, 'w') as f:
                f.write('')

            state = SimpleNamespace(
                env={},
                tmpdir=tmpdir,
                work_manifest={'dirspaces': []},
                working_dir='.')

            with mock.patch('workflow_step_infracost_setup._configure_infracost'), \
                 mock.patch('workflow_step_infracost_setup._create_base_infracost'), \
                 mock.patch('workflow_step_infracost_setup._resolve_config_file') as resolve, \
                 mock.patch('workflow_step_infracost_setup._run_retry') as run_retry, \
                 mock.patch('workflow_step_infracost_setup.workflow.make') as make, \
                 self.assertLogs(level='INFO') as logs:
                resolve.return_value = config_yml
                run_retry.return_value = ''
                workflow_step_infracost_setup.run(state, config)

        self.assertTrue(make.call_args[1]['success'])
        return '\n'.join(logs.output)

    def test_logs_the_full_diff_by_default(self):
        self.assertIn('aws_instance.secret_name', self._log({}))

    def test_log_output_false_logs_only_the_totals(self):
        log = self._log({'log_output': False})

        self.assertNotIn('aws_instance.secret_name', log)
        self.assertIn('INFRACOST : DIFF : projects=1', log)


if __name__ == '__main__':
    unittest.main()
