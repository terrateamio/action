import unittest
from types import SimpleNamespace
from unittest import mock

import workflow_step_plan


class PlanStepTest(unittest.TestCase):
    def test_store_plan_none_defaults_unsafe_apply_without_plan_false(self):
        state = SimpleNamespace()
        with mock.patch('workflow_step_plan._store_plan_data') as store_plan_data:
            store_plan_data.return_value = (True, '')

            result = workflow_step_plan._store_plan_none(
                state,
                {'method': 'none'},
                'dev',
                'default',
                True)

        self.assertEqual(result, (True, ''))
        store_plan_data.assert_called_once_with(
            state,
            {
                'method': 'none',
                'unsafe_apply_without_plan': False,
                'version': 1,
            },
            'dev',
            'default',
            True)

    def test_store_plan_none_preserves_unsafe_apply_without_plan(self):
        state = SimpleNamespace()
        with mock.patch('workflow_step_plan._store_plan_data') as store_plan_data:
            store_plan_data.return_value = (True, '')

            result = workflow_step_plan._store_plan_none(
                state,
                {
                    'method': 'none',
                    'unsafe_apply_without_plan': True,
                },
                'dev',
                'default',
                True)

        self.assertEqual(result, (True, ''))
        store_plan_data.assert_called_once_with(
            state,
            {
                'method': 'none',
                'unsafe_apply_without_plan': True,
                'version': 1,
            },
            'dev',
            'default',
            True)


if __name__ == '__main__':
    unittest.main()
