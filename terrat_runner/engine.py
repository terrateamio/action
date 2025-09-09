import collections

Engine = collections.namedtuple('Engine', [
    'apply',
    'diff',
    'diff_json',
    'init',
    'name',
    'outputs',
    'plan',
    'unsafe_apply',
])
