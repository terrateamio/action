import io
import json
import os
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from unittest import mock


def _load_builder():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'bin',
        'terragrunt-config-builder')
    loader = SourceFileLoader('terragrunt_config_builder', path)
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


builder = _load_builder()


def generate(dirs, **kwargs):
    return builder.generate_terrateam_config(
        {},
        dirs,
        {d: {} for d in dirs},
        {},
        '/repo',
        **kwargs)


class ParseArgsTest(unittest.TestCase):
    def test_default_is_opt_out(self):
        # No flag: the builder leaves workspace handling alone.
        self.assertTrue(builder.parse_args([]).create_and_select_workspace)

    def test_flag_disables_workspace(self):
        args = builder.parse_args(['--no-create-and-select-workspace'])
        self.assertFalse(args.create_and_select_workspace)

    def test_flag_composes_with_scan_tf_files(self):
        args = builder.parse_args(['--scan-tf-files', '--no-create-and-select-workspace'])
        self.assertTrue(args.scan_tf_files)
        self.assertFalse(args.create_and_select_workspace)


class GenerateConfigTest(unittest.TestCase):
    def test_key_absent_by_default(self):
        config = generate(['prod/vpc', 'prod/app'])
        for dir_config in config['dirs'].values():
            self.assertNotIn('create_and_select_workspace', dir_config)

    def test_key_absent_when_explicitly_enabled(self):
        config = generate(['prod/vpc'], create_and_select_workspace=True)
        self.assertNotIn('create_and_select_workspace', config['dirs']['prod/vpc'])

    def test_key_false_on_every_dir_when_disabled(self):
        config = generate(['prod/vpc', 'prod/app', ''], create_and_select_workspace=False)
        self.assertEqual(sorted(config['dirs']), ['.', 'prod/app', 'prod/vpc'])
        for dir_config in config['dirs'].values():
            self.assertIs(dir_config['create_and_select_workspace'], False)

    def test_rest_of_the_dir_entry_is_unchanged(self):
        enabled = generate(['prod/vpc'])['dirs']['prod/vpc']
        disabled = generate(['prod/vpc'], create_and_select_workspace=False)['dirs']['prod/vpc']
        self.assertEqual(disabled.pop('create_and_select_workspace'), False)
        self.assertEqual(disabled, enabled)


class MainTest(unittest.TestCase):
    def run_main(self, argv):
        stdout = io.StringIO()

        with mock.patch.object(builder.sys, 'argv', ['terragrunt-config-builder'] + argv), \
             mock.patch.object(builder.sys, 'stdin', io.StringIO(json.dumps({'dirs': {}}))), \
             mock.patch.object(builder.sys, 'stdout', stdout), \
             mock.patch.dict(builder.os.environ, {'TERRATEAM_ROOT': '/repo'}), \
             mock.patch.object(builder, 'configure_terragrunt_env'), \
             mock.patch.object(builder, 'discover_terragrunt_files', return_value=['prod/vpc']), \
             mock.patch.object(builder, 'get_terragrunt_dependencies', return_value={}), \
             mock.patch.object(builder, 'parse_terragrunt_dependencies', return_value={}):
            builder.main()

        return json.loads(stdout.getvalue())

    def test_flag_reaches_stdout(self):
        config = self.run_main(['--no-create-and-select-workspace'])
        self.assertIs(config['dirs']['prod/vpc']['create_and_select_workspace'], False)

    def test_no_flag_leaves_stdout_alone(self):
        config = self.run_main([])
        self.assertNotIn('create_and_select_workspace', config['dirs']['prod/vpc'])


if __name__ == '__main__':
    unittest.main()
