import hashlib
import yaml


def json_filename_of_dirspace(dirspace):
    filename_str = ','.join([dirspace['path'], dirspace['workspace']]).encode('utf-8')
    return hashlib.sha256(filename_str).hexdigest() + '.json'


def convert_cost(cost):
    if cost is not None:
        try:
            return float(cost)
        except ValueError:
            return 0.0
    else:
        return 0.0


def create_infracost_yml(outname, dirspaces):
    # We want to configure infracost with the most minimal configuration, so we
    # find the set of base directories that we'll run in (with a check for if
    # "." is in there) and create a new set of dirspaces just for those, and
    # then build the config.
    by_workspace = {}
    for ds in dirspaces:
        by_workspace.setdefault(ds['workspace'], []).append(ds)

    dirspaces = []
    for ws, dspaces in by_workspace.items():
        ds = set([d['path'].split('/')[0] for d in dspaces])
        if '.' in ds:
            dirspaces.append({'path': '.', 'workspace': ws})
        else:
            dirspaces.extend([{'path': d, 'workspace': ws} for d in ds])

    config = {
        'version': '0.1',
        'projects': [
            {
                'path': ds['path'],
                'terraform_workspace': ds['workspace'],
            }
            for ds in dirspaces
        ]
    }

    with open(outname, 'w') as f:
        yaml.dump(config, f)
