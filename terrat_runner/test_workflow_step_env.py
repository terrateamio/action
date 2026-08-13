import unittest

import workflow_step_env


class FilterShellVarsTest(unittest.TestCase):
    def test_removes_vars_bash_injects(self):
        # bash sets these itself in the environment of the command it runs, so
        # they look "introduced by this step" even though the sourced script
        # never mentioned them.
        env = {
            '_': '/usr/bin/env',
            'OLDPWD': '/home/user',
            'PWD': '/work',
            'SHLVL': '2',
            'FOO': 'bar',
        }
        self.assertEqual(workflow_step_env.filter_shell_vars(env), {'FOO': 'bar'})

    def test_keeps_user_vars_with_similar_names(self):
        env = {
            'MY_PWD': 'secret',
            'PWD_': 'secret',
            'SHLVL_OVERRIDE': 'secret',
            'PWD': '/work',
        }
        self.assertEqual(workflow_step_env.filter_shell_vars(env),
                         {'MY_PWD': 'secret',
                          'PWD_': 'secret',
                          'SHLVL_OVERRIDE': 'secret'})

    def test_empty(self):
        self.assertEqual(workflow_step_env.filter_shell_vars({}), {})


if __name__ == '__main__':
    unittest.main()
