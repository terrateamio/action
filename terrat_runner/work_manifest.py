import logging

import requests_retry


class NoWorkManifestError(Exception):
    pass


# The work token names a compute node.  A compute node can perform more than one
# work manifest, so the response names the work manifest that this iteration must
# operate on.  See [main.run].
def _url(api_base_url, work_token):
    return api_base_url + '/v1/compute-node/' + work_token + '/initiate'


# A server that predates the compute node endpoint.  Such a server gives a work
# token that is a work manifest id, and it answers this URL.
def _legacy_url(api_base_url, work_token):
    return api_base_url + '/v1/work-manifests/' + work_token + '/initiate'


def get(api_base_url, work_token, run_id, sha):
    body = {'run_id': run_id, 'sha': sha}
    r = requests_retry.post(url=_url(api_base_url, work_token), json=body)

    if r.status_code == 404:
        # The compute node endpoint and an unknown work token both give 404, so
        # ask the older URL before the run stops.  A server that has the compute
        # node endpoint answers it, thus this second call happens one time only,
        # against a server that predates the endpoint.
        logging.info('COMPUTE_NODE_INITIATE_NOT_FOUND : trying the work manifest URL')
        r = requests_retry.post(url=_legacy_url(api_base_url, work_token), json=body)

    if r.status_code == 404:
        logging.error('%s', r.text)
        raise NoWorkManifestError()
    if r.status_code != 200:
        logging.error('%s', r.text)
        raise Exception('Invalid work manifest response code')

    work_manifest = r.json()

    return work_manifest
