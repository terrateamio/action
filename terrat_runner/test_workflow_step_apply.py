import base64
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import workflow_step_apply


class ApplyStepTest(unittest.TestCase):
    def _plan_response(self, plan_data):
        encoded = base64.b64encode(json.dumps(plan_data).encode('utf-8')).decode('utf-8')
        res = mock.Mock()
        res.status_code = 200
        res.json.return_value = {'data': encoded}
        return res

    def test_load_plan_rejects_none_without_unsafe_apply_opt_in(self):
        with mock.patch('workflow_step_apply.api.work_manifest_get') as get:
            get.return_value = self._plan_response({'method': 'none', 'version': 1})

            result = workflow_step_apply._load_plan(
                SimpleNamespace(),
                'dev',
                'default',
                '/tmp/plan')

        self.assertEqual(result[0], False)
        self.assertIn('unsafe_apply_without_plan', result[1])
        self.assertEqual(result[2], False)

    def test_load_plan_allows_none_with_unsafe_apply_opt_in(self):
        with mock.patch('workflow_step_apply.api.work_manifest_get') as get:
            get.return_value = self._plan_response({
                'method': 'none',
                'unsafe_apply_without_plan': True,
                'version': 1,
            })

            result = workflow_step_apply._load_plan(
                SimpleNamespace(),
                'dev',
                'default',
                '/tmp/plan')

        self.assertEqual(result, (True, None, False))

    def test_run_uses_apply_without_plan_when_no_plan_file_was_loaded(self):
        calls = []

        def apply(_state, _config):
            calls.append('apply')
            return (True, 'apply', '')

        def apply_without_plan(_state, _config):
            calls.append('apply_without_plan')
            return (True, 'apply without plan', '')

        engine = SimpleNamespace(
            apply=apply,
            apply_without_plan=apply_without_plan,
            name='tf',
            outputs=lambda _state, _config: None,
        )
        state = SimpleNamespace(
            api_base_url='https://api.example.com',
            engine=engine,
            env={'TERRATEAM_PLAN_FILE': '/tmp/plan'},
            path='.',
            work_token='token',
            workspace='default',
        )

        with mock.patch('workflow_step_apply._load_plan') as load_plan:
            load_plan.return_value = (True, None, False)

            result = workflow_step_apply.run(state, {})

        self.assertEqual(calls, ['apply_without_plan'])
        self.assertTrue(result.success)
        self.assertEqual(result.payload['text'], 'apply without plan')

    def _visible_on_of_run(self, config):
        engine = SimpleNamespace(
            apply=lambda _state, _config: (True, 'applied', ''),
            name='tf',
            outputs=lambda _state, _config: None,
        )
        state = SimpleNamespace(
            api_base_url='https://api.example.com',
            engine=engine,
            env={'TERRATEAM_PLAN_FILE': '/tmp/plan'},
            path='.',
            work_token='token',
            workspace='default',
        )

        with mock.patch('workflow_step_apply._load_plan') as load_plan:
            load_plan.return_value = (True, None, True)

            return workflow_step_apply.run(state, config).payload['visible_on']

    def test_run_defaults_visible_on_to_always(self):
        self.assertEqual(self._visible_on_of_run({}), 'always')

    def test_run_takes_visible_on_from_the_step_config(self):
        self.assertEqual(self._visible_on_of_run({'visible_on': 'failure'}), 'failure')


if __name__ == '__main__':
    unittest.main()
