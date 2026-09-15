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


if __name__ == '__main__':
    unittest.main()
