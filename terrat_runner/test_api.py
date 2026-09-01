import unittest
import unittest.mock

import api
import requests_retry
import run_state
import work_manifest


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


class WorkManifestUrlTest(unittest.TestCase):
    def test_initiate_asks_the_compute_node(self):
        self.assertEqual('https://app.terrateam.io/v1/compute-node/cn-123/initiate',
                         work_manifest._url('https://app.terrateam.io', 'cn-123'))

    def test_the_fallback_asks_the_work_manifest(self):
        self.assertEqual('https://app.terrateam.io/v1/work-manifests/cn-123/initiate',
                         work_manifest._legacy_url('https://app.terrateam.io', 'cn-123'))


def _response(status_code, body=None):
    r = unittest.mock.Mock()
    r.status_code = status_code
    r.text = ''
    r.json.return_value = body if body is not None else {}
    return r


class WorkManifestGetTest(unittest.TestCase):
    # A server that has the compute node endpoint is asked one time only.
    def test_a_new_server_is_asked_once(self):
        wm = {'type': 'build-tree', 'id': 'wm-1'}
        with unittest.mock.patch.object(requests_retry, 'post',
                                        return_value=_response(200, wm)) as post:
            self.assertEqual(wm, work_manifest.get('https://x', 'cn-1', 'run-1', 'sha-1'))
        self.assertEqual(1, post.call_count)
        self.assertEqual('https://x/v1/compute-node/cn-1/initiate',
                         post.call_args.kwargs['url'])

    # A server that predates the endpoint gives 404, so the work manifest URL is
    # asked, and the run continues.
    def test_an_old_server_falls_back(self):
        wm = {'type': 'build-tree'}
        with unittest.mock.patch.object(
                requests_retry, 'post',
                side_effect=[_response(404), _response(200, wm)]) as post:
            self.assertEqual(wm, work_manifest.get('https://x', 'wm-1', 'run-1', 'sha-1'))
        self.assertEqual(2, post.call_count)
        self.assertEqual('https://x/v1/compute-node/wm-1/initiate',
                         post.call_args_list[0].kwargs['url'])
        self.assertEqual('https://x/v1/work-manifests/wm-1/initiate',
                         post.call_args_list[1].kwargs['url'])

    # An unknown work token gives 404 from both URLs, which still stops the run.
    def test_an_unknown_token_still_raises(self):
        with unittest.mock.patch.object(
                requests_retry, 'post',
                side_effect=[_response(404), _response(404)]):
            with self.assertRaises(work_manifest.NoWorkManifestError):
                work_manifest.get('https://x', 'nope', 'run-1', 'sha-1')


class HeadersTest(unittest.TestCase):
    def test_api_token_is_sent_as_a_bearer_token(self):
        self.assertEqual({'authorization': 'bearer token-abc'}, api._headers(state()))


if __name__ == '__main__':
    unittest.main()
