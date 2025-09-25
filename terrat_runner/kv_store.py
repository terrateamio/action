import hashlib
import string
import time


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
        'steps'
    ])


# This knows where keys are going to be put and ensures that there are no
# overlapping names.  This DOES NOT guarantee that concurrent runs might not
# generate an overlapping name, but rather in a sequence of operations, there
# are no existing names which overlap with the key path
def gen_unique_key_path(state, f, idx=0):
    timestamp = str(time.time_ns()).encode('utf-8') + '.' + str(idx).encode('utf-8')
    digest = hashlib.new('sha256').update(timestamp).hexdigest()[:6]
    path = os.path.join(state.outputs_dir, f(digest))
    if os.path.exists(path):
        return gen_unique_key_path(state, f, idx=idx + 1)
    else:
        return path
