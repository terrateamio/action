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
        # The engine's record of the transaction behind the plan file, as a
        # dict the server stores under the 'tx' key of the plan and apply
        # payloads, or None. Only an engine whose backend has transactions (e.g. stategraph)
        # sets it.
        'tx',
    ],
    defaults=(None,),
)
