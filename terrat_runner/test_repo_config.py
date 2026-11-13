import unittest

import repo_config


class PlanStorageTest(unittest.TestCase):
    def test_workflow_inherits_global_storage(self):
        storage = {
            'plans': {
                'bucket': 'plans',
                'method': 's3',
                'region': 'us-east-1',
            }
        }
        config = {
            'storage': storage,
            'workflows': [{'tag_query': ''}],
        }

        workflow = repo_config.get_workflow(config, 0)

        self.assertEqual(repo_config.get_plan_storage(workflow), storage['plans'])

    def test_workflow_overrides_global_storage(self):
        workflow_storage = {
            'method': 'none',
            'unsafe_apply_without_plan': True,
        }
        config = {
            'storage': {
                'plans': {
                    'bucket': 'plans',
                    'method': 's3',
                    'region': 'us-east-1',
                }
            },
            'workflows': [
                {
                    'storage': {
                        'plans': workflow_storage
                    },
                    'tag_query': '',
                }
            ],
        }

        workflow = repo_config.get_workflow(config, 0)

        self.assertEqual(repo_config.get_plan_storage(workflow), workflow_storage)

    def test_default_workflow_inherits_global_storage(self):
        storage = {
            'plans': {
                'method': 'none',
            }
        }
        config = {
            'storage': storage,
        }

        workflow = repo_config.get_default_workflow(config)

        self.assertEqual(repo_config.get_plan_storage(workflow), storage['plans'])


class PlanLogOutputTest(unittest.TestCase):
    def test_defaults_to_true(self):
        self.assertTrue(repo_config.get_plan_log_output({}))
        self.assertTrue(repo_config.get_plan_log_output({'workflows': [{'tag_query': ''}]}))

    def test_false_when_any_workflow_plan_step_sets_it(self):
        config = {
            'workflows': [
                {'tag_query': 'a', 'plan': [{'type': 'init'}, {'type': 'plan'}]},
                {'tag_query': 'b', 'plan': [{'type': 'init'}, {'type': 'plan', 'log_output': False}]},
            ]
        }

        self.assertFalse(repo_config.get_plan_log_output(config))

    def test_ignores_other_steps(self):
        config = {
            'workflows': [
                {'tag_query': '', 'plan': [{'type': 'init', 'log_output': False}, {'type': 'plan'}]},
            ]
        }

        self.assertTrue(repo_config.get_plan_log_output(config))


if __name__ == '__main__':
    unittest.main()
