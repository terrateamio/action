import multiprocessing


# Need to order dirs by rank, but also, want to run one workspace at a time for
# a dir.  So we fake it by increasing the rank on dirs that have multiple
# workspaces.
def _order_dirs_by_rank(dirs):
    ranking = {}

    for d in dirs:
        ranking.setdefault(d['rank'], {}).setdefault(d['path'], []).append(d)

    # ranking is a dict where the key is the numerical rank and the value is a
    # dictionary of the dir path to all entries.  There will only be multiple
    # entries for the path if there are multiple workspaces.
    #
    # We iterate the ranking, in order, and then for each list of values, we
    # consume any dirspaces that we can and at the end of each iteration add the
    # row to the final result.  Once there are no more values to add, then
    # [added] will be false, and we exit.
    #
    # For example, if we have dirs [(1, d1, w1), (1, d1, w2), (2, d2,w1)]
    #
    # ranking would be {1: {d1: [(1, d1, w1), (1, d1, w2)]}, 2: [(2, d2, w1)]}
    #
    # Then the result would be [[(1, d1, w1)], [(1, d1, w2)], [(2, d2, w1)]]
    ret = []
    for k in sorted(ranking.keys()):
        row = []
        vs = ranking[k].values()

        added = True
        while added:
            added = False
            for v in vs:
                if v:
                    row.append(v.pop())
                    added = True

            ret.append(row)
            row = []

    return ret


def _run(args):
    return args[0](*args[1:])


def run(parallel, dirs, f, args):
    dirs = _order_dirs_by_rank(dirs)
    res = []
    for ds in dirs:
        with multiprocessing.Pool(parallel) as p:
            res.extend(p.map(_run, [(f,) + args + (d,) for d in ds]))

    return res
