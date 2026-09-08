"""Terraform provider cache backed by the Terrateam KV store.

The runner fills the cache; the server never talks to a registry.  Before the
run, [setup] fetches the providers named by the lock files of the changed
directories and points both engines at a filesystem mirror holding them.  After
the run, [store] uploads whatever the engines had to download.

The key ends with the provider's h1 hash, so a fetched package is only ever used
when the repository's own lock file already records that exact package.  A
provider whose lock file has no usable h1 is left alone and comes from the
registry, as it does without this feature.
"""

import base64
import binascii
import glob
import hashlib
import io
import logging
import os
import platform
import re
import shutil
import urllib.parse
import zipfile

import repo_config as rc
import requests_retry


# Only public registries are cached.  A private registry host may serve a
# provider that is not public, and one copy of it would save nothing anyway.
CACHEABLE_HOSTS = frozenset(['registry.terraform.io', 'registry.opentofu.org'])

CAPABILITY = 'provider_cache'
KEY_PREFIX = 'provider-cache'

# Raw bytes per KV row.  Base64 grows this by a third, so the JSON body stays
# well under the server's 100 MB limit.
CHUNK_SIZE = 8 * 1024 * 1024

# kv_store.idx is a smallint.
MAX_CHUNKS = 32767

_PROVIDER_BLOCK_RE = re.compile(
    r'provider\s+"(?P<source>[^"]+)"\s*\{(?P<body>.*?)\n\}',
    re.DOTALL)
_VERSION_RE = re.compile(r'\n\s*version\s*=\s*"(?P<version>[^"]+)"')
_HASHES_RE = re.compile(r'\n\s*hashes\s*=\s*\[(?P<hashes>.*?)\]', re.DOTALL)
_HASH_RE = re.compile(r'"(?P<hash>[^"]+)"')


class Provider(object):
    """One provider requirement read out of a .terraform.lock.hcl."""

    def __init__(self, source, version, hashes):
        self.source = source
        self.version = version
        self.hashes = hashes

    @property
    def host(self):
        return self.source.split('/')[0]

    def h1_hashes(self):
        return [h for h in self.hashes if h.startswith('h1:')]

    def mirror_path(self, mirror_dir, platform_name):
        return os.path.join(mirror_dir, self.source, self.version, platform_name)

    def __repr__(self):
        return 'Provider({}, {})'.format(self.source, self.version)


def platform_name():
    machine = platform.machine().lower()
    arch = {
        'x86_64': 'amd64',
        'amd64': 'amd64',
        'aarch64': 'arm64',
        'arm64': 'arm64',
    }.get(machine, machine)

    return '{}_{}'.format(platform.system().lower(), arch)


def h1_of_dir(path):
    """The engines' h1 hash: Go's dirhash.Hash1 over the package directory.

    Each file contributes one "<sha256 hex>  <name>\\n" line, the lines are
    sorted, and the hash is the base64 sha256 of that text.
    """
    names = []
    for dirpath, _, filenames in os.walk(path):
        for filename in filenames:
            fname = os.path.join(dirpath, filename)
            names.append((os.path.relpath(fname, path), fname))

    summary = io.BytesIO()
    for (name, fname) in sorted(names):
        digest = hashlib.sha256()
        with open(fname, 'rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(block)

        summary.write('{}  {}\n'.format(digest.hexdigest(), name).encode('utf-8'))

    return 'h1:' + base64.b64encode(
        hashlib.sha256(summary.getvalue()).digest()).decode('ascii')


def h1_to_key_component(h1):
    """Hex of the digest inside an h1 hash, or None if it is not one.

    The lock file spells an h1 in base64, which carries '/' and '+' and cannot
    go in a URL path unescaped.  Hex is the same 32 bytes and is URL safe.
    """
    if not h1.startswith('h1:'):
        return None

    try:
        digest = base64.b64decode(h1[len('h1:'):], validate=True)
    except (binascii.Error, ValueError):
        return None

    if len(digest) != hashlib.sha256().digest_size:
        return None

    return digest.hex()


def cache_key(provider, platform_name_, h1):
    key_component = h1_to_key_component(h1)
    if key_component is None:
        return None

    return '/'.join([KEY_PREFIX,
                     provider.source,
                     provider.version,
                     platform_name_,
                     key_component])


def parse_lock_file(content):
    """Read the providers out of the text of a .terraform.lock.hcl."""
    providers = []
    for block in _PROVIDER_BLOCK_RE.finditer(content):
        body = block.group('body')
        version = _VERSION_RE.search(body)
        if version is None:
            continue

        hashes_match = _HASHES_RE.search(body)
        hashes = ([h.group('hash') for h in _HASH_RE.finditer(hashes_match.group('hashes'))]
                  if hashes_match is not None
                  else [])

        providers.append(Provider(block.group('source'), version.group('version'), hashes))

    return providers


def read_lock_files(working_dir, dirs):
    """Every distinct provider named by the lock files of [dirs].

    A directory with no lock file contributes nothing.  Without a lock file
    both engines re-resolve the provider from the registry anyway, so there is
    nothing the cache could serve.
    """
    providers = {}
    for d in dirs:
        path = os.path.join(working_dir, d, '.terraform.lock.hcl')
        if not os.path.exists(path):
            logging.debug('PROVIDER_CACHE : NO_LOCK_FILE : dir=%s', d)
            continue

        with open(path) as f:
            content = f.read()

        for provider in parse_lock_file(content):
            existing = providers.get((provider.source, provider.version))
            if existing is None:
                providers[(provider.source, provider.version)] = provider
            else:
                # The same provider version can be locked in several
                # directories with different hash sets.  Take the union so a
                # hit in any of them counts.
                for h in provider.hashes:
                    if h not in existing.hashes:
                        existing.hashes.append(h)

    return list(providers.values())


def cacheable(providers):
    return [p for p in providers if p.host in CACHEABLE_HOSTS]


def cli_config(mirror_dir, excluded_sources):
    """The provider_installation block pointing the engines at the mirror.

    Only the providers actually fetched are excluded from 'direct'.  Anything
    else falls through to the registry, so a miss degrades to today's
    behaviour rather than failing the run.
    """
    excludes = ', '.join('"{}"'.format(s) for s in sorted(excluded_sources))
    return (
        'provider_installation {\n'
        '  filesystem_mirror {\n'
        '    path = "' + mirror_dir + '"\n'
        '  }\n'
        '  direct {\n'
        '    exclude = [' + excludes + ']\n'
        '  }\n'
        '}\n')


def _headers(state):
    return {'authorization': 'bearer ' + state.api_token}


def _kv_base(state):
    """The KV store URL for this installation.

    [api_base_url] is <base>/api/<vcs>; the KV store is at
    <base>/api/v1/<vcs>/kv/<installation_id>.
    """
    base, _, vcs = state.api_base_url.rpartition('/')
    installation_id = state.work_manifest.get('installation_id')
    if not base or not vcs or not installation_id:
        return None

    return '{}/v1/{}/kv/{}'.format(base, vcs, installation_id)


def _key_url(kv_base, key):
    return '{}/key/{}'.format(kv_base, urllib.parse.quote(key, safe='/'))


def _get_chunk(state, kv_base, key, idx):
    """The bytes of one chunk, or None if it is not there or does not verify."""
    res = requests_retry.get(_key_url(kv_base, key),
                             headers=_headers(state),
                             params={'idx': idx})
    if res.status_code != 200:
        return None

    payload = res.json().get('data')
    if not isinstance(payload, dict):
        return None

    data = payload.get('data')
    chk = payload.get('chk')
    if not isinstance(data, str) or not isinstance(chk, str):
        return None

    if chk != 'sha256:' + hashlib.sha256(data.encode('utf-8')).hexdigest():
        logging.warning('PROVIDER_CACHE : CHUNK_CHECKSUM_MISMATCH : key=%s : idx=%d', key, idx)
        return None

    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


def _download(state, kv_base, key):
    """Every chunk of [key] joined, or None if the first chunk is missing."""
    chunks = []
    for idx in range(MAX_CHUNKS + 1):
        chunk = _get_chunk(state, kv_base, key, idx)
        if chunk is None:
            break

        chunks.append(chunk)

    if not chunks:
        return None

    return b''.join(chunks)


def _put_chunk(state, kv_base, key, idx, chunk):
    data = base64.b64encode(chunk).decode('ascii')
    res = requests_retry.put(
        _key_url(kv_base, key),
        headers=_headers(state),
        json={
            'data': {
                'chk': 'sha256:' + hashlib.sha256(data.encode('utf-8')).hexdigest(),
                'data': data,
            },
            'idx': idx,
            'committed': False,
        })

    return res.status_code == 200


def _commit(state, kv_base, key):
    res = requests_retry.post('{}/commit'.format(kv_base),
                              headers=_headers(state),
                              json={'keys': [{'key': key}]})
    return res.status_code == 200


def _unpack(blob, dst):
    """Extract a provider zip into [dst].  False if it is not a usable zip."""
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for name in zf.namelist():
                # Refuse absolute paths and anything climbing out of [dst].
                target = os.path.realpath(os.path.join(dst, name))
                if not target.startswith(os.path.realpath(dst) + os.sep):
                    logging.warning('PROVIDER_CACHE : UNSAFE_ZIP_ENTRY : %s', name)
                    return False

            for info in zf.infolist():
                zf.extract(info, dst)
                mode = info.external_attr >> 16
                if mode:
                    os.chmod(os.path.join(dst, info.filename), mode & 0o777)
    except (zipfile.BadZipFile, OSError) as exn:
        logging.warning('PROVIDER_CACHE : UNPACK_FAILED : %r', exn)
        return False

    return True


def _zip_dir(path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, filenames in os.walk(path):
            for filename in sorted(filenames):
                fname = os.path.join(dirpath, filename)
                zf.write(fname, os.path.relpath(fname, path))

    return buf.getvalue()


def _fetch_provider(state, kv_base, provider, plat, mirror_dir):
    """Put [provider] in the mirror.  True if it is there when we return.

    Tries every h1 the lock file records.  The bytes are only kept when they
    hash back to the h1 in the key, so a wrong or damaged object falls through
    to the registry rather than failing the run.
    """
    dst = provider.mirror_path(mirror_dir, plat)
    for h1 in provider.h1_hashes():
        key = cache_key(provider, plat, h1)
        if key is None:
            continue

        blob = _download(state, kv_base, key)
        if blob is None:
            continue

        if not _unpack(blob, dst):
            shutil.rmtree(dst, ignore_errors=True)
            continue

        actual = h1_of_dir(dst)
        if actual != h1:
            logging.warning('PROVIDER_CACHE : H1_MISMATCH : source=%s : version=%s : expected=%s : actual=%s',
                            provider.source,
                            provider.version,
                            h1,
                            actual)
            shutil.rmtree(dst, ignore_errors=True)
            continue

        logging.info('PROVIDER_CACHE : HIT : source=%s : version=%s',
                     provider.source,
                     provider.version)
        return True

    logging.info('PROVIDER_CACHE : MISS : source=%s : version=%s',
                 provider.source,
                 provider.version)
    return False


def downloaded_packages(cache_dir):
    """Every provider the engines downloaded into the plugin cache.

    A package installed from the mirror is a symbolic link, so a real directory
    is one that came from a registry and is not in the cache yet.
    """
    packages = []
    for path in sorted(glob.glob(os.path.join(cache_dir, '*', '*', '*', '*', '*'))):
        if not os.path.isdir(path) or os.path.islink(path):
            continue

        rest, plat = os.path.split(path)
        rest, version = os.path.split(rest)
        rest, type_ = os.path.split(rest)
        rest, namespace = os.path.split(rest)
        _, host = os.path.split(rest)
        packages.append((path, '/'.join([host, namespace, type_]), version, plat))

    return packages


def _store_package(state, kv_base, path, source, version, plat):
    h1 = h1_of_dir(path)
    key = cache_key(Provider(source, version, [h1]), plat, h1)
    if key is None:
        return False

    if _get_chunk(state, kv_base, key, 0) is not None:
        logging.debug('PROVIDER_CACHE : ALREADY_STORED : source=%s : version=%s', source, version)
        return False

    blob = _zip_dir(path)
    chunks = [blob[i:i + CHUNK_SIZE] for i in range(0, len(blob), CHUNK_SIZE)]
    if not chunks or len(chunks) > MAX_CHUNKS:
        logging.warning('PROVIDER_CACHE : UNSTORABLE_SIZE : source=%s : bytes=%d', source, len(blob))
        return False

    for idx, chunk in enumerate(chunks):
        if not _put_chunk(state, kv_base, key, idx, chunk):
            logging.warning('PROVIDER_CACHE : STORE_FAILED : source=%s : idx=%d', source, idx)
            return False

    if not _commit(state, kv_base, key):
        logging.warning('PROVIDER_CACHE : COMMIT_FAILED : source=%s', source)
        return False

    logging.info('PROVIDER_CACHE : STORED : source=%s : version=%s : bytes=%d',
                 source,
                 version,
                 len(blob))
    return True


def _conflicting_env(env):
    """Variables the user already set that this feature would overwrite."""
    return [k for k in ['TF_CLI_CONFIG_FILE', 'TF_PLUGIN_CACHE_DIR'] if env.get(k)]


def enabled(state):
    if CAPABILITY not in state.work_manifest.get('capabilities', []):
        return False

    if not rc.get_provider_cache(state.repo_config).get('enabled', False):
        return False

    conflicting = _conflicting_env(state.env)
    if conflicting:
        logging.info('PROVIDER_CACHE : DISABLED : env already set : %s', ','.join(conflicting))
        return False

    return True


def setup(state):
    """Fill the mirror and point the engines at it.  Returns the new state."""
    if not enabled(state):
        return state

    kv_base = _kv_base(state)
    if kv_base is None:
        logging.warning('PROVIDER_CACHE : DISABLED : could not build the KV store URL')
        return state

    plat = platform_name()
    mirror_dir = os.path.join(state.tmpdir, 'provider-mirror')
    cache_dir = os.path.join(state.tmpdir, 'provider-cache')
    os.makedirs(mirror_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    dirs = sorted({ds['path'] for ds in state.work_manifest.get('changed_dirspaces', [])})
    providers = cacheable(read_lock_files(state.working_dir, dirs))

    fetched = []
    for provider in providers:
        if _fetch_provider(state, kv_base, provider, plat, mirror_dir):
            fetched.append(provider.source)

    config_path = os.path.join(state.tmpdir, 'provider-cache.tfrc')
    with open(config_path, 'w') as f:
        f.write(cli_config(mirror_dir, set(fetched)))

    logging.info('PROVIDER_CACHE : SETUP : providers=%d : fetched=%d',
                 len(providers),
                 len(fetched))

    env = state.env.copy()
    env['TF_CLI_CONFIG_FILE'] = config_path
    env['TF_PLUGIN_CACHE_DIR'] = cache_dir
    return state._replace(env=env)


def store(state):
    """Upload every provider the engines had to download during this run."""
    if not enabled(state):
        return

    cache_dir = state.env.get('TF_PLUGIN_CACHE_DIR')
    if not cache_dir:
        return

    kv_base = _kv_base(state)
    if kv_base is None:
        return

    stored = 0
    for (path, source, version, plat) in downloaded_packages(cache_dir):
        if source.split('/')[0] not in CACHEABLE_HOSTS:
            continue

        try:
            if _store_package(state, kv_base, path, source, version, plat):
                stored += 1
        except Exception:
            # The cache must never fail a run that otherwise succeeded.
            logging.exception('PROVIDER_CACHE : STORE_FAILED : source=%s', source)

    logging.info('PROVIDER_CACHE : STORE : stored=%d', stored)
