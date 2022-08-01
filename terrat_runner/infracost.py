import hashlib


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
