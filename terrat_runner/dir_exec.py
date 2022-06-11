import multiprocessing


def _order_dirs_by_rank(dirs):
    ret = {}

    for d in dirs:
        ret.setdefault(d['rank'], []).append(d)

    return [sorted(ret[k], key=lambda d: (d['path'], d['workspace']))
            for k in sorted(ret.keys())]


def _run(args):
    return args[0](*args[1:])


def run(parallel, dirs, f, args):
    dirs = _order_dirs_by_rank(dirs)
    for ds in dirs:
        with multiprocessing.Pool(parallel) as p:
            return p.map(_run, [(f,) + args + (d,) for d in ds])
