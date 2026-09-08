import json
import unittest
from types import SimpleNamespace
from unittest import mock

import engine_custom
import engine_tf
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

    def _visible_on_of_failed_run(self, config):
        # A plan that fails returns its payload straight away, which is the shortest path through
        # run() that still builds one.
        engine = SimpleNamespace(
            name='tf',
            plan=lambda _state, _config: (False, False, 'stdout', 'stderr'),
        )
        state = SimpleNamespace(engine=engine)

        return workflow_step_plan.run(state, config).payload['visible_on']

    def test_run_defaults_visible_on_to_always(self):
        self.assertEqual(self._visible_on_of_failed_run({}), 'always')

    def test_run_takes_visible_on_from_the_step_config(self):
        self.assertEqual(self._visible_on_of_failed_run({'visible_on': 'success'}), 'success')


class ResourceSummaryTest(unittest.TestCase):
    PLAN_JSON = {
        'resource_changes': [
            {'change': {'actions': ['create']}},
            {'change': {'actions': ['create']}},
            {'change': {'actions': ['update']}},
            {'change': {'actions': ['delete']}},
            {'change': {'actions': ['create', 'delete']}},
            {'change': {'actions': ['delete', 'create']}},
            {'change': {'actions': ['no-op']}},
            {'change': {'actions': ['read']}},
            {'change': {}},
            {},
        ],
    }

    def test_counts_are_split_per_action_with_replacements_in_their_own_bucket(self):
        self.assertEqual(
            engine_tf._resource_summary_from_plan_json(self.PLAN_JSON),
            {'created': 2, 'updated': 1, 'deleted': 1, 'replaced': 2})

    def test_plan_without_resource_changes_counts_zeros(self):
        self.assertEqual(
            engine_tf._resource_summary_from_plan_json({}),
            {'created': 0, 'updated': 0, 'deleted': 0, 'replaced': 0})
        self.assertEqual(
            engine_tf._resource_summary_from_plan_json({'resource_changes': []}),
            {'created': 0, 'updated': 0, 'deleted': 0, 'replaced': 0})

    def test_unparseable_plan_json_is_none(self):
        self.assertIsNone(engine_tf._resource_summary_from_plan_json(None))
        self.assertIsNone(engine_tf._resource_summary_from_plan_json([]))

    def test_engine_resource_summary_returns_none_when_show_json_fails(self):
        engine = engine_tf.Engine('tf', 'terraform')
        state = SimpleNamespace(path='foo', workflow={'engine': {'name': 'tf'}})
        config = {}

        with mock.patch.object(engine, 'diff_json') as diff_json:
            diff_json.return_value = (False, 'stdout', 'stderr')
            self.assertIsNone(engine.resource_summary(state, config))

    def test_engine_resource_summary_counts_plan_json(self):
        engine = engine_tf.Engine('tf', 'terraform')
        state = SimpleNamespace(path='foo', workflow={'engine': {'name': 'tf'}})
        config = {}

        with mock.patch.object(engine, 'diff_json') as diff_json:
            diff_json.return_value = (True, self.PLAN_JSON)
            self.assertEqual(
                engine.resource_summary(state, config),
                {'created': 2, 'updated': 1, 'deleted': 1, 'replaced': 2})

    def _run_with_summary(self, engine):
        state = SimpleNamespace(
            engine=engine,
            workflow={'engine': {'name': 'tf'}, 'storage': {'plans': {'method': 'none'}}},
            env={
                'TERRATEAM_DIR': 'foo',
                'TERRATEAM_WORKSPACE': 'default',
                'TERRATEAM_PLAN_FILE': '/tmp/plan.out',
            })

        with mock.patch('workflow_step_plan._store_plan') as store_plan:
            store_plan.return_value = (True, '')
            with mock.patch('workflow_step_plan.os.path.exists') as exists:
                exists.return_value = True
                return workflow_step_plan.run(state, {})

    def test_run_attaches_resource_summary_to_the_payload(self):
        engine = SimpleNamespace(
            name='tf',
            plan=lambda _state, _config: (True, True, 'stdout', 'stderr'),
            diff=lambda _state, _config: (True, 'diff', ''),
            resource_summary=lambda _state, _config: {'created': 1,
                                                      'updated': 0,
                                                      'deleted': 0,
                                                      'replaced': 0})

        result = self._run_with_summary(engine)
        self.assertEqual(result.payload['resource_summary'],
                         {'created': 1, 'updated': 0, 'deleted': 0, 'replaced': 0})

    def test_run_omits_resource_summary_when_the_engine_returns_none(self):
        engine = SimpleNamespace(
            name='tf',
            plan=lambda _state, _config: (True, True, 'stdout', 'stderr'),
            diff=lambda _state, _config: (True, 'diff', ''),
            resource_summary=lambda _state, _config: None)

        result = self._run_with_summary(engine)
        self.assertNotIn('resource_summary', result.payload)

    def test_run_skips_resource_summary_when_there_are_no_changes(self):
        resource_summary = mock.Mock()
        engine = SimpleNamespace(
            name='tf',
            plan=lambda _state, _config: (True, False, 'stdout', 'stderr'),
            diff=lambda _state, _config: (True, 'diff', ''),
            resource_summary=resource_summary)

        result = self._run_with_summary(engine)
        resource_summary.assert_not_called()
        self.assertNotIn('resource_summary', result.payload)


class CustomEngineResourceSummaryTest(unittest.TestCase):
    SUMMARY = {'created': 1, 'updated': 2, 'deleted': 3, 'replaced': 4}

    def _engine(self, **overrides):
        kwargs = {
            'init_args': None,
            'apply_args': None,
            'diff_args': None,
            'diff_json_args': None,
            'resource_summary_args': None,
            'plan_args': None,
            'unsafe_apply_args': None,
            'outputs_args': None,
        }
        kwargs.update(overrides)

        return engine_custom.make(**kwargs)

    def _state(self):
        return SimpleNamespace(path='foo', workflow={'engine': {'name': 'custom'}})

    def test_runs_the_summary_program_and_returns_its_json(self):
        engine = self._engine(resource_summary_args=['summary', '--json'])

        with mock.patch('engine_custom.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0),
                                json.dumps(self.SUMMARY), '')

            self.assertEqual(engine.resource_summary(self._state(), {}), self.SUMMARY)

        self.assertEqual(run.call_args[0][1]['cmd'], ['summary', '--json'])

    def test_returns_none_when_no_summary_program_is_set(self):
        engine = self._engine()

        with mock.patch('engine_custom.cmd.run_with_output') as run:
            self.assertIsNone(engine.resource_summary(self._state(), {}))

        run.assert_not_called()

    def test_returns_none_when_the_summary_program_fails(self):
        engine = self._engine(resource_summary_args=['summary'])

        with mock.patch('engine_custom.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=1), 'out', 'err')

            self.assertIsNone(engine.resource_summary(self._state(), {}))

    def test_returns_none_when_the_summary_program_prints_bad_json(self):
        engine = self._engine(resource_summary_args=['summary'])

        with mock.patch('engine_custom.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), 'not json', '')

            self.assertIsNone(engine.resource_summary(self._state(), {}))

    def test_returns_none_when_the_summary_program_prints_a_non_object(self):
        engine = self._engine(resource_summary_args=['summary'])

        with mock.patch('engine_custom.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), '[1, 2]', '')

            self.assertIsNone(engine.resource_summary(self._state(), {}))


if __name__ == '__main__':
    unittest.main()
