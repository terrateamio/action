import logging

import requests

import retry

TIMEOUT = 120
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
    if not success or (ret.status_code >= 500 and ret.status_code < 600) or ret.status_code == 429:
        logging.error('REQUESTS : FAILED : %r', ret)
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
    return _wrap(lambda: requests.post(*args, timeout=TIMEOUT, **kwargs))


def put(*args, **kwargs):
    return _wrap(lambda: requests.put(*args, timeout=TIMEOUT, **kwargs))


def get(*args, **kwargs):
    return _wrap(lambda: requests.get(*args, timeout=TIMEOUT, **kwargs))
