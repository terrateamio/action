import cmd


def _fixup_api_base(api_base):
    if api_base.endswith('/api'):
        return api_base[:-len('/api')]
    else:
        return api_base

def kv_upload(state, api_base, installation_id, key, path, draft=False, read_caps=[], write_caps=[]):
    proc = cmd.run(
        state,
        {
            'cmd': [
                'ttm',
                'kv',
                'cp',
                '-vvv',
                '--api-base', _fixup_api_base(api_base),
                '--installation-id', installation_id,
                '--vcs', state.runtime.name(),
            ] + [
                '--read-cap={}'.format(c)
                for c in read_caps
            ] + [
                '--write-cap={}'.format(c)
                for c in write_caps
            ] + ([] if not draft else ['-d']) + [path, 'kv://' + key]
        })
    if proc.returncode != 0:
        raise Exception('Failed to upload')


def kv_download(state, api_base, installation_id, key, path):
    proc = cmd.run(
        state,
        {
            'cmd': [
                'ttm',
                'kv',
                'cp',
                '-vvv',
                '--api-base', _fixup_api_base(api_base),
                '--installation-id', installation_id,
                '--vcs', state.runtime.name(),
                'kv://' + key,
                path]
        })
    if proc.returncode != 0:
        raise Exception('Failed to upload')


def kv_set(state, api_base, installation_id, key, data, idx=0, draft=False, read_caps=[], write_caps=[]):
    proc = cmd.run(
        state,
        {
            'cmd': [
                'ttm',
                'kv',
                'set',
                '-vvv',
                '--api-base', _fixup_api_base(api_base),
                '--installation-id', installation_id,
                '--vcs', state.runtime.name(),
                '--idx', str(idx),
            ] + [
                '--read-cap={}'.format(c)
                for c in read_caps
            ] + [
                '--write-cap={}'.format(c)
                for c in write_caps
            ] + ([] if not draft else ['-d']) + [key],
            'input': data
        })
    if proc.returncode != 0:
        raise Exception('Failed to set')


def kv_commit(state, api_base, installation_id, keys):
    proc = cmd.run(
        state,
        {
            'cmd': [
                'ttm',
                'kv',
                'commit',
                '-vvv',
                '--api-base', _fixup_api_base(api_base),
                '--installation-id', installation_id,
                '--vcs', state.runtime.name()] + keys
        }
    )
    if proc.returncode != 0:
        raise Exception('Failed to commit')


def kv_delete(state, api_base, installation_id, key):
    proc = cmd.run(
        state,
        {
            'cmd': [
                'ttm',
                'kv',
                'delete',
                '-vvv',
                '--api-base', _fixup_api_base(api_base),
                '--installation-id', installation_id,
                '--vcs', state.runtime.name(),
                key]
        }
    )
    if proc.returncode != 0:
        raise Exception('Failed to delete')


def secrets_mask(state, secrets, unmasks, fname):
    proc = cmd.run(
        state,
        {
            'cmd': [
                'ttm',
                'secrets',
                'mask',
                '-s', secrets,
                '--unmask', unmasks,
                '--in-place',
                fname
            ]
        }
    )
    if proc.returncode != 0:
        raise Exception('Failed to mask secrets')
