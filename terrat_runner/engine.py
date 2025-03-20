import collections

Engine = collections.namedtuple('Engine', [
    'apply',
    'diff',
    'init',
    'name',
    'outputs',
    'plan',
    'unsafe_apply',
])
