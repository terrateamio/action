import time


def betwixt_sleep_with_backoff(initial_sleep, backoff):
    """Given an initial sleep and a backup, sleep for the time and increase it
    by the backoff time.

    """
    sleep_time = [initial_sleep]

    def _f():
        time.sleep(sleep_time[0])
        sleep_time[0] = sleep_time[0] * backoff

    return _f


def finite_tries(tries, f):
    """Try for a number of tries and once reached, return whatever the value is.
    [f] should return [False] if another try should be attempted.

    """
    count = [0]

    def _f(ret):
        count[0] += 1
        if count[0] < tries:
            return f(ret)
        else:
            return True

    return _f


def run(f, test, betwixt):
    """Run a function and collect its return, then test the result.  If the test
    returns [True] then return the value, otherwise run the [betwixt] function
    and retry.

    This does NOT catch any exceptions.

    """
    ret = f()
    if test(ret):
        return ret
    else:
        betwixt()
        return run(f, test, betwixt)
