import os
import tempfile
import unittest

import plugin_cache


class InitEnvTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmpdir.name, 'home')
        self.cache = os.path.join(self.tmpdir.name, 'cache')
        os.makedirs(self.home)
        self.addCleanup(self.tmpdir.cleanup)

    def env(self, **kwargs):
        env = {
            'HOME': self.home,
            plugin_cache.ENABLED_ENV_NAME: 'true',
            plugin_cache.DIR_ENV_NAME: self.cache
        }
        env.update(kwargs)
        return env

    def write_config(self, fname, content):
        path = os.path.join(self.home, fname)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_off_by_default(self):
        env = self.env()
        del env[plugin_cache.ENABLED_ENV_NAME]
        self.assertEqual(plugin_cache.init_env(env), {})
        self.assertFalse(os.path.exists(self.cache))

    def test_off_when_not_true(self):
        self.assertEqual(plugin_cache.init_env(self.env(TERRATEAM_PLUGIN_CACHE='false')), {})
        self.assertEqual(plugin_cache.init_env(self.env(TERRATEAM_PLUGIN_CACHE='no')), {})

    def test_on_when_one(self):
        self.assertEqual(plugin_cache.init_env(self.env(TERRATEAM_PLUGIN_CACHE='1')),
                         {'TF_PLUGIN_CACHE_DIR': self.cache})

    def test_enabled_creates_the_dir(self):
        self.assertEqual(plugin_cache.init_env(self.env()),
                         {'TF_PLUGIN_CACHE_DIR': self.cache})
        self.assertTrue(os.path.isdir(self.cache))

    def test_default_dir(self):
        env = self.env()
        del env[plugin_cache.DIR_ENV_NAME]
        self.assertEqual(plugin_cache.init_env(env),
                         {'TF_PLUGIN_CACHE_DIR': plugin_cache._default_dir()})

    # A cache directory the repository set itself must win: TF_PLUGIN_CACHE_DIR
    # takes precedence over a plugin_cache_dir in a CLI configuration file, so
    # setting ours would silently move their cache.
    def test_declines_when_env_var_already_set(self):
        self.assertEqual(
            plugin_cache.init_env(self.env(TF_PLUGIN_CACHE_DIR='/somewhere/else')),
            {})

    def test_declines_on_terraformrc(self):
        self.write_config('.terraformrc', 'plugin_cache_dir = "/somewhere/else"\n')
        self.assertEqual(plugin_cache.init_env(self.env()), {})

    def test_declines_on_tofurc(self):
        self.write_config('.tofurc', 'plugin_cache_dir = "/somewhere/else"\n')
        self.assertEqual(plugin_cache.init_env(self.env()), {})

    def test_declines_on_cli_config_file_env_var(self):
        path = self.write_config('myrc', 'plugin_cache_dir = "/somewhere/else"\n')
        self.assertEqual(plugin_cache.init_env(self.env(TF_CLI_CONFIG_FILE=path)), {})

    def test_declines_on_tofu_cli_config_file_env_var(self):
        path = self.write_config('myrc', 'plugin_cache_dir = "/somewhere/else"\n')
        self.assertEqual(plugin_cache.init_env(self.env(TOFU_CLI_CONFIG_FILE=path)), {})

    def test_a_commented_setting_is_not_a_setting(self):
        self.write_config('.terraformrc', '# plugin_cache_dir = "/somewhere/else"\n')
        self.assertEqual(plugin_cache.init_env(self.env()),
                         {'TF_PLUGIN_CACHE_DIR': self.cache})

    # Everything else a repository puts in its CLI configuration file is left
    # alone, because the environment variable adds a setting rather than
    # replacing the file.
    def test_other_settings_do_not_decline(self):
        self.write_config('.terraformrc',
                          'credentials "app.terraform.io" {\n  token = "xxx"\n}\n')
        self.assertEqual(plugin_cache.init_env(self.env()),
                         {'TF_PLUGIN_CACHE_DIR': self.cache})

    def test_missing_config_file_does_not_decline(self):
        self.assertEqual(
            plugin_cache.init_env(self.env(TF_CLI_CONFIG_FILE='/no/such/file')),
            {'TF_PLUGIN_CACHE_DIR': self.cache})

    def test_no_home(self):
        env = self.env()
        del env['HOME']
        self.assertEqual(plugin_cache.init_env(env),
                         {'TF_PLUGIN_CACHE_DIR': self.cache})

    # An existing but unwritable cache directory fails the init outright, so we
    # must never hand one to Terraform.
    def test_declines_when_dir_is_not_writable(self):
        os.makedirs(self.cache)
        os.chmod(self.cache, 0o555)
        self.addCleanup(os.chmod, self.cache, 0o755)
        self.assertEqual(plugin_cache.init_env(self.env()), {})

    def test_declines_when_dir_cannot_be_created(self):
        blocker = os.path.join(self.tmpdir.name, 'blocker')
        with open(blocker, 'w') as f:
            f.write('')
        self.assertEqual(
            plugin_cache.init_env(self.env(TERRATEAM_PLUGIN_CACHE_DIR=os.path.join(blocker, 'c'))),
            {})


if __name__ == '__main__':
    unittest.main()
