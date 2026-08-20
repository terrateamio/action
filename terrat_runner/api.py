import requests_retry


def _url(state, path=None):
    url = state.api_base_url + '/v1/work-manifests/' + state.work_token
    if path:
        url += '/' + path

    return url


def _headers(state):
    return {'authorization': 'bearer ' + state.api_token}


def work_manifest_get(state, path=None, params=None):
    return requests_retry.get(_url(state, path), headers=_headers(state), params=params)


def work_manifest_post(state, path=None, json=None):
    return requests_retry.post(_url(state, path), headers=_headers(state), json=json)


def work_manifest_put(state, path=None, json=None):
    return requests_retry.put(_url(state, path), headers=_headers(state), json=json)
