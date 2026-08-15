import unittest
from unittest import mock

import workflow_step_plan


class PlanStepTest(unittest.TestCase):
    def test_store_plan_none_defaults_unsafe_apply_without_plan_false(self):
        with mock.patch('workflow_step_plan._store_plan_data') as store_plan_data:
            store_plan_data.return_value = (True, '')

            result = workflow_step_plan._store_plan_none(
                {'method': 'none'},
                'token',
                'https://api.example.com',
                'dev',
                'default',
                True)

        self.assertEqual(result, (True, ''))
        store_plan_data.assert_called_once_with(
            {
                'method': 'none',
                'unsafe_apply_without_plan': False,
                'version': 1,
            },
            'token',
            'https://api.example.com',
            'dev',
            'default',
            True)

    def test_store_plan_none_preserves_unsafe_apply_without_plan(self):
        with mock.patch('workflow_step_plan._store_plan_data') as store_plan_data:
            store_plan_data.return_value = (True, '')

            result = workflow_step_plan._store_plan_none(
                {
                    'method': 'none',
                    'unsafe_apply_without_plan': True,
                },
                'token',
                'https://api.example.com',
                'dev',
                'default',
                True)

        self.assertEqual(result, (True, ''))
        store_plan_data.assert_called_once_with(
            {
                'method': 'none',
                'unsafe_apply_without_plan': True,
                'version': 1,
            },
            'token',
            'https://api.example.com',
            'dev',
            'default',
            True)


if __name__ == '__main__':
    unittest.main()
