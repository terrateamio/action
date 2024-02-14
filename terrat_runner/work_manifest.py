import logging

import requests_retry


class NoWorkManifestError(Exception):
    pass


def get(api_base_url, work_token, run_id, sha):
    r = requests_retry.post(url=api_base_url + '/v1/work-manifests/' + work_token + '/initiate',
                            json={
                                'run_id': run_id,
                                'sha': sha
                            })

    if r.status_code == 404:
        logging.error('%s', r.text)
        raise NoWorkManifestError()
    if r.status_code != 200:
        logging.error('%s', r.text)
        raise Exception('Invalid work manifest response code')

    work_manifest = r.json()

    return work_manifest
