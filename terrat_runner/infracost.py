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
