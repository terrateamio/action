import base64
import hashlib
import io
import os
import shutil
import tempfile
import unittest
import zipfile
from types import SimpleNamespace

import provider_cache


LOCK_FILE = '''# This file is maintained automatically by "tofu init".
# Manual edits may be lost in future updates.

provider "registry.opentofu.org/hashicorp/null" {
  version     = "3.2.2"
  constraints = "3.2.2"
  hashes = [
    "h1:xN1tSeF/rUBfaddk/AVqk4i65z/MMM9uVZWd2cWCCH0=",
    "zh:00e5877d19fb1c1d8c4b3536334a46a5c86f57146fd115c7b7b4b5d2bf2de86d",
  ]
}

provider "terraform.example.com/acme/secret" {
  version = "1.0.0"
  hashes = [
    "h1:awfs6PFJcbrz3PtasIlQyi6mUP2rN/BUSnK8mnTskf8=",
  ]
}
'''


def _write(path, name, content, mode=None):
    fname = os.path.join(path, name)
    os.makedirs(os.path.dirname(fname), exist_ok=True)
    with open(fname, 'wb') as f:
        f.write(content)

    if mode is not None:
        os.chmod(fname, mode)

    return fname


class LockFileTest(unittest.TestCase):
    def test_parse_reads_source_version_and_hashes(self):
        providers = provider_cache.parse_lock_file(LOCK_FILE)
        self.assertEqual([p.source for p in providers],
                         ['registry.opentofu.org/hashicorp/null',
                          'terraform.example.com/acme/secret'])
        self.assertEqual(providers[0].version, '3.2.2')
        self.assertEqual(len(providers[0].hashes), 2)
        self.assertEqual(providers[0].h1_hashes(),
                         ['h1:xN1tSeF/rUBfaddk/AVqk4i65z/MMM9uVZWd2cWCCH0='])

    def test_parse_skips_a_block_without_a_version(self):
        content = 'provider "registry.opentofu.org/hashicorp/null" {\n  hashes = []\n}\n'
        self.assertEqual(provider_cache.parse_lock_file(content), [])

    def test_parse_handles_a_block_without_hashes(self):
        content = 'provider "registry.opentofu.org/hashicorp/null" {\n  version = "3.2.2"\n}\n'
        providers = provider_cache.parse_lock_file(content)
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].hashes, [])
        self.assertEqual(providers[0].h1_hashes(), [])

    def test_only_public_registries_are_cacheable(self):
        providers = provider_cache.parse_lock_file(LOCK_FILE)
        self.assertEqual([p.source for p in provider_cache.cacheable(providers)],
                         ['registry.opentofu.org/hashicorp/null'])

    def test_read_lock_files_unions_hashes_across_directories(self):
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path, True)
        one = 'provider "registry.opentofu.org/a/b" {\n  version = "1.0.0"\n  hashes = ["h1:one"]\n}\n'
        two = 'provider "registry.opentofu.org/a/b" {\n  version = "1.0.0"\n  hashes = ["h1:two"]\n}\n'
        _write(path, os.path.join('one', '.terraform.lock.hcl'), one.encode('utf-8'))
        _write(path, os.path.join('two', '.terraform.lock.hcl'), two.encode('utf-8'))

        providers = provider_cache.read_lock_files(path, ['one', 'two', 'no-lock-file'])

        self.assertEqual(len(providers), 1)
        self.assertEqual(sorted(providers[0].hashes), ['h1:one', 'h1:two'])


class H1Test(unittest.TestCase):
    """The h1 must be Go's dirhash.Hash1, which the engines compare against the
    lock file.  The values below were cross-checked against the h1 that
    Terraform 1.15.6 and OpenTofu 1.12.2 themselves wrote for hashicorp/null
    3.2.2."""

    def test_single_file_package(self):
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path, True)
        _write(path, 'terraform-provider-null_v3.2.2_x5', b'hello')

        digest = hashlib.sha256(b'hello').hexdigest()
        summary = '{}  terraform-provider-null_v3.2.2_x5\n'.format(digest).encode('utf-8')
        expected = 'h1:' + base64.b64encode(hashlib.sha256(summary).digest()).decode('ascii')

        self.assertEqual(provider_cache.h1_of_dir(path), expected)

    def test_files_are_ordered_by_name_not_by_hash(self):
        # 'a' hashes above 'b', so a hash-ordered summary differs from the
        # name-ordered one Hash1 specifies.  This is the defect that made the
        # computed h1 miss the lock file for every multi-file package.
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path, True)
        _write(path, 'a', b'a')
        _write(path, 'b', b'b')

        summary = ''.join(
            '{}  {}\n'.format(hashlib.sha256(c).hexdigest(), n)
            for (n, c) in [('a', b'a'), ('b', b'b')]).encode('utf-8')
        expected = 'h1:' + base64.b64encode(hashlib.sha256(summary).digest()).decode('ascii')

        self.assertEqual(provider_cache.h1_of_dir(path), expected)

    def test_nested_files_use_their_relative_path(self):
        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path, True)
        _write(path, os.path.join('docs', 'README.md'), b'x')

        summary = '{}  docs/README.md\n'.format(hashlib.sha256(b'x').hexdigest()).encode('utf-8')
        expected = 'h1:' + base64.b64encode(hashlib.sha256(summary).digest()).decode('ascii')

        self.assertEqual(provider_cache.h1_of_dir(path), expected)


class KeyTest(unittest.TestCase):
    def test_h1_becomes_hex_of_the_digest(self):
        digest = bytes(range(32))
        h1 = 'h1:' + base64.b64encode(digest).decode('ascii')
        self.assertEqual(provider_cache.h1_to_key_component(h1), digest.hex())

    def test_a_non_h1_hash_has_no_key_component(self):
        self.assertIsNone(provider_cache.h1_to_key_component('zh:00e5877d19fb'))

    def test_bad_base64_has_no_key_component(self):
        self.assertIsNone(provider_cache.h1_to_key_component('h1:not base64!'))

    def test_a_wrong_length_digest_has_no_key_component(self):
        self.assertIsNone(
            provider_cache.h1_to_key_component('h1:' + base64.b64encode(b'short').decode('ascii')))

    def test_cache_key_shape(self):
        digest = bytes(range(32))
        h1 = 'h1:' + base64.b64encode(digest).decode('ascii')
        provider = provider_cache.Provider('registry.opentofu.org/hashicorp/null', '3.2.2', [h1])

        self.assertEqual(
            provider_cache.cache_key(provider, 'linux_amd64', h1),
            'provider-cache/registry.opentofu.org/hashicorp/null/3.2.2/linux_amd64/' + digest.hex())

    def test_cache_key_is_none_when_the_hash_is_unusable(self):
        provider = provider_cache.Provider('registry.opentofu.org/hashicorp/null', '3.2.2', [])
        self.assertIsNone(provider_cache.cache_key(provider, 'linux_amd64', 'zh:abc'))

    def test_the_key_has_no_url_unsafe_characters(self):
        # A base64 h1 carries '/' and '+', which would break the URL path.
        h1 = 'h1:xN1tSeF/rUBfaddk/AVqk4i65z/MMM9uVZWd2cWCCH0='
        component = provider_cache.h1_to_key_component(h1)
        self.assertRegex(component, r'^[0-9a-f]{64}$')


class CliConfigTest(unittest.TestCase):
    def test_excludes_are_sorted_and_quoted(self):
        config = provider_cache.cli_config('/m', {'registry.opentofu.org/b/c',
                                                  'registry.terraform.io/a/b'})
        self.assertIn('path = "/m"', config)
        self.assertIn('exclude = ["registry.opentofu.org/b/c", "registry.terraform.io/a/b"]',
                      config)

    def test_no_hits_means_an_empty_exclude_list(self):
        # Every provider then falls through to 'direct', which is what a cold
        # cache must do.
        self.assertIn('exclude = []', provider_cache.cli_config('/m', set()))


class PackageTest(unittest.TestCase):
    def _cache_with(self, root, kind):
        path = os.path.join(root, 'registry.opentofu.org', 'hashicorp', 'null', '3.2.2')
        os.makedirs(path, exist_ok=True)
        target = os.path.join(path, 'linux_amd64')
        if kind == 'dir':
            os.makedirs(target, exist_ok=True)
            _write(target, 'terraform-provider-null', b'x')
        elif kind == 'link':
            os.symlink(root, target)

        return target

    def test_downloaded_packages_finds_real_directories(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self._cache_with(root, 'dir')
        # tofu writes a sibling lock file next to the platform directory.
        _write(os.path.join(root, 'registry.opentofu.org', 'hashicorp', 'null', '3.2.2'),
               'linux_amd64.lock', b'')

        packages = provider_cache.downloaded_packages(root)

        self.assertEqual([(p[1], p[2], p[3]) for p in packages],
                         [('registry.opentofu.org/hashicorp/null', '3.2.2', 'linux_amd64')])

    def test_downloaded_packages_skips_mirror_symlinks(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self._cache_with(root, 'link')

        self.assertEqual(provider_cache.downloaded_packages(root), [])

    def test_downloaded_packages_on_a_missing_directory(self):
        self.assertEqual(provider_cache.downloaded_packages('/nonexistent-cache-dir'), [])

    def test_zip_round_trip_keeps_content_hash_and_mode(self):
        src = tempfile.mkdtemp()
        dst = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, src, True)
        self.addCleanup(shutil.rmtree, dst, True)
        _write(src, 'terraform-provider-null', b'binary', mode=0o755)
        _write(src, 'LICENSE', b'text', mode=0o644)
        before = provider_cache.h1_of_dir(src)

        self.assertTrue(provider_cache._unpack(provider_cache._zip_dir(src), dst))

        self.assertEqual(provider_cache.h1_of_dir(dst), before)
        self.assertEqual(os.stat(os.path.join(dst, 'terraform-provider-null')).st_mode & 0o777,
                         0o755)

    def test_unpack_refuses_a_zip_that_escapes_the_destination(self):
        dst = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dst, True)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('../escaped', 'x')

        self.assertFalse(provider_cache._unpack(buf.getvalue(), dst))

    def test_unpack_refuses_something_that_is_not_a_zip(self):
        dst = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dst, True)
        self.assertFalse(provider_cache._unpack(b'not a zip', dst))


def _state(capabilities=None, repo_config=None, env=None, api_base_url=None, installation_id='42'):
    return SimpleNamespace(
        api_base_url=api_base_url or 'https://app.terrateam.io/api/github',
        api_token='tok',
        env={} if env is None else env,
        repo_config={'provider_cache': {'enabled': True}} if repo_config is None else repo_config,
        work_manifest={
            'capabilities': ['tenv', 'provider_cache'] if capabilities is None else capabilities,
            'installation_id': installation_id,
        })


class EnabledTest(unittest.TestCase):
    def test_enabled_when_the_server_offers_it_and_the_repo_asks_for_it(self):
        self.assertTrue(provider_cache.enabled(_state()))

    def test_disabled_without_the_capability(self):
        self.assertFalse(provider_cache.enabled(_state(capabilities=['tenv'])))

    def test_disabled_when_the_repo_config_does_not_ask_for_it(self):
        self.assertFalse(provider_cache.enabled(_state(repo_config={})))
        self.assertFalse(
            provider_cache.enabled(_state(repo_config={'provider_cache': {'enabled': False}})))

    def test_disabled_when_the_user_already_set_the_engine_variables(self):
        self.assertFalse(
            provider_cache.enabled(_state(env={'TF_CLI_CONFIG_FILE': '/etc/tfrc'})))
        self.assertFalse(
            provider_cache.enabled(_state(env={'TF_PLUGIN_CACHE_DIR': '/cache'})))


class KvBaseTest(unittest.TestCase):
    def test_the_kv_url_comes_from_the_api_base_url_and_the_installation(self):
        self.assertEqual(provider_cache._kv_base(_state()),
                         'https://app.terrateam.io/api/v1/github/kv/42')

    def test_gitlab(self):
        state = _state(api_base_url='https://tf.example.com/api/gitlab', installation_id='7')
        self.assertEqual(provider_cache._kv_base(state),
                         'https://tf.example.com/api/v1/gitlab/kv/7')

    def test_no_url_without_an_installation_id(self):
        self.assertIsNone(provider_cache._kv_base(_state(installation_id=None)))


class PlatformTest(unittest.TestCase):
    def test_platform_name_is_engine_shaped(self):
        self.assertRegex(provider_cache.platform_name(), r'^[a-z0-9]+_[a-z0-9]+$')


if __name__ == '__main__':
    unittest.main()
