import collections

Engine = collections.namedtuple(
    'Engine',
    [
        'apply',
        'diff',
        'diff_json',
        'init',
        'name',
        'outputs',
        'plan',
        'unsafe_apply',
        # Per-resource plan change counts as a dict with keys
        # 'created', 'updated', 'deleted', 'replaced', or None when the
        # engine cannot produce them.
        'resource_summary',
    ],
)
