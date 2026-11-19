import unittest

import main

from runtime.github_actions import runtime as github_actions
from runtime.gitlab_ci import runtime as gitlab_ci


class ShouldLogRepoConfigTest(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(main.should_log_repo_config(github_actions.Runtime(), {}))
        self.assertFalse(main.should_log_repo_config(gitlab_ci.Runtime(), {}))

    def test_env_var(self):
        for value in ('true', 'TRUE', '1'):
            self.assertTrue(main.should_log_repo_config(
                github_actions.Runtime(),
                {'TERRATEAM_LOG_REPO_CONFIG': value}))

        for value in ('', 'false', '0', 'yes'):
            self.assertFalse(main.should_log_repo_config(
                github_actions.Runtime(),
                {'TERRATEAM_LOG_REPO_CONFIG': value}))

    def test_github_debug_logging(self):
        self.assertTrue(main.should_log_repo_config(github_actions.Runtime(),
                                                    {'RUNNER_DEBUG': '1'}))
        self.assertFalse(main.should_log_repo_config(github_actions.Runtime(),
                                                     {'RUNNER_DEBUG': '0'}))

    def test_gitlab_debug_trace(self):
        self.assertTrue(main.should_log_repo_config(gitlab_ci.Runtime(),
                                                    {'CI_DEBUG_TRACE': 'true'}))
        # Each runtime reads only its own CI's debug variable.
        self.assertFalse(main.should_log_repo_config(gitlab_ci.Runtime(),
                                                     {'RUNNER_DEBUG': '1'}))


if __name__ == '__main__':
    unittest.main()
