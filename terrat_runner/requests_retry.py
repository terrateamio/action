import logging

import requests

import retry


TRIES = 3
INITIAL_SLEEP = 1
BACKOFF = 1.5


def _wrap_call(f):
    try:
        return (True, f())
    except Exception as exn:
        return (False, exn)


def _test_success(v):
    if not v[0]:
        logging.error('REQUESTS : FAILED : {}', v[1])

    return v[0]


def _wrap(f):
    (success, res) = retry.run(
        lambda: _wrap_call(f),
        retry.finite_tries(TRIES, _test_success),
        retry.betwixt_sleep_with_backoff(INITIAL_SLEEP, BACKOFF))

    if not success:
        raise res

    return res


def post(*args, **kwargs):
    return _wrap(lambda: requests.post(*args, **kwargs))


def put(*args, **kwargs):
    return _wrap(lambda: requests.put(*args, **kwargs))


def get(*args, **kwargs):
    return _wrap(lambda: requests.get(*args, **kwargs))
