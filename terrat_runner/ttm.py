import cmd

# ttm is a statically-linked binary whose bundled libcurl has no usable built-in
# CA bundle path; without an explicit one, every HTTPS call fails TLS
# verification with "Problem with the SSL CA cert". Point it at the image's
# system CA bundle. This is scoped to ttm's own subprocesses (rather than a
# global image environment variable) so no other tool's TLS behavior is changed.
CA_BUNDLE = '/etc/ssl/certs/ca-certificates.crt'


def _run(state, config):
    # Inject the CA bundle into every ttm invocation without clobbering any env
    # the caller already provided.
    config = dict(config)
    config['env'] = dict(config.get('env', {}), SSL_CERT_FILE=CA_BUNDLE)
    return cmd.run(state, config)


def _fixup_api_base(api_base):
    if api_base.endswith('/api'):
        return api_base[:-len('/api')]
    else:
        return api_base

def kv_upload(state, api_base, installation_id, key, path, draft=False, read_caps=[], write_caps=[]):
    proc = _run(
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
    proc = _run(
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
        raise Exception('Failed to download')


def kv_set(state, api_base, installation_id, key, data, idx=0, draft=False, read_caps=[], write_caps=[]):
    proc = _run(
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
    proc = _run(
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
    proc = _run(
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
    proc = _run(
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
