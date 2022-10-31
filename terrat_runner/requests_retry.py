import logging

import requests

import retry


TRIES = 5
INITIAL_SLEEP = 1
BACKOFF = 1.5


def _wrap_call(f):
    try:
        return (True, f())
    except Exception as exn:
        return (False, exn)


def _test_success(v):
    success, ret = v
    if not success or (ret.status_code >= 500 and ret.status_code < 600):
        logging.error('REQUESTS : FAILED : {}', ret)
        return False

    return True


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
