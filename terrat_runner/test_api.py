import unittest

import api
import run_state


def state():
    return run_state.create(api_base_url='https://app.terrateam.io',
                            api_token='token-abc',
                            repo_config={},
                            result_version=2,
                            runtime=None,
                            env={},
                            sha='deadbeef',
                            work_manifest={},
                            work_token='wm-123',
                            working_dir='/tmp')


class UrlTest(unittest.TestCase):
    def test_no_path_is_the_work_manifest_itself(self):
        self.assertEqual('https://app.terrateam.io/v1/work-manifests/wm-123',
                         api._url(state()))

    def test_path_is_appended(self):
        self.assertEqual('https://app.terrateam.io/v1/work-manifests/wm-123/plans',
                         api._url(state(), 'plans'))
        self.assertEqual('https://app.terrateam.io/v1/work-manifests/wm-123/access-token',
                         api._url(state(), 'access-token'))


class HeadersTest(unittest.TestCase):
    def test_api_token_is_sent_as_a_bearer_token(self):
        self.assertEqual({'authorization': 'bearer token-abc'}, api._headers(state()))


if __name__ == '__main__':
    unittest.main()
