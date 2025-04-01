import collections


Result2 = collections.namedtuple('Result2',
                                 [
                                     'payload',
                                     'state',
                                     'step',
                                     'success',
                                 ])


def make(payload, state, step, success):
    return Result2(payload=payload, state=state, step=step, success=success)
