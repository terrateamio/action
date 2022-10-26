import logging
import requests


def get(api_base_url, work_token, run_id, sha):
    r = requests.post(url=api_base_url + '/v1/work-manifests/' + work_token + '/initiate',
                      json={
                          'run_id': run_id,
                          'sha': sha
                      })

    if r.status_code != 200:
        logging.error('%s', r.text)
        raise Exception('Invalid work manifest response code')

    work_manifest = r.json()

    if work_manifest['type'] in ['unsafe-apply', 'apply', 'plan']:
        return work_manifest
    else:
        raise Exception('Unknown work manifest type: {}'.format(work_manifest['type']))
