import hashlib
import os
import string
import time
import urllib


def mk_dirspace_key(state, typ):
    return string.Template(
        '.'.join([
            'wm',
            state.work_token,
            'scope',
            'ds',
            '${TERRATEAM_DIR}',
            '${TERRATEAM_WORKSPACE}',
            typ])).substitute(state.env)


def mk_hooks_key(state, s, typ):
    return string.Template(
        '.'.join([
            'wm',
            state.work_token,
            'scope',
            'hook',
            s,
            typ])).substitute(state.env)

def mk_steps_key(state):
    return '.'.join([
        'wm',
        state.work_token,
        'steps'])


# This knows where keys are going to be put and ensures that there are no
# overlapping names.  This DOES NOT guarantee that concurrent runs might not
# generate an overlapping name, but rather in a sequence of operations, there
# are no existing names which overlap with the key path
#
# The paths are URL encoded to ensure that even if a key has a slash in it, it
# is a valid file name.
def gen_unique_key_path(state, f, idx=0):
    timestamp = (str(time.time_ns()) + '.' + str(idx)).encode('utf-8')
    digest = hashlib.new('sha256', timestamp).hexdigest()[:6]
    path = os.path.join(state.outputs_dir, urllib.parse.quote(f(digest), safe=''))
    if os.path.exists(path):
        return gen_unique_key_path(state, f, idx=idx + 1)
    else:
        return path
