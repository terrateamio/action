import io
import json
import os
import re
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


def generate(dirs, deps=None, **kwargs):
    return builder.generate_terrateam_config(
        {},
        dirs,
        deps if deps is not None else {d: {} for d in dirs},
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

    def test_no_exclude_file_patterns_by_default(self):
        # No flag: nothing is dropped from the generated file_patterns.
        self.assertEqual(builder.parse_args([]).exclude_file_patterns, [])

    def test_exclude_file_pattern_repeats(self):
        args = builder.parse_args([
            '--exclude-file-pattern', 'provider*.hcl',
            '--exclude-file-pattern', 'provisioning/modules/**'])
        self.assertEqual(
            args.exclude_file_patterns,
            ['provider*.hcl', 'provisioning/modules/**'])

    def test_exclude_file_pattern_composes_with_the_other_flags(self):
        args = builder.parse_args([
            '--scan-tf-files',
            '--no-create-and-select-workspace',
            '--exclude-file-pattern', 'root.hcl'])
        self.assertTrue(args.scan_tf_files)
        self.assertFalse(args.create_and_select_workspace)
        self.assertEqual(args.exclude_file_patterns, ['root.hcl'])


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


class GlobToRegexTest(unittest.TestCase):
    def matches(self, glob, path):
        return bool(re.match(builder.glob_to_regex(glob), path))

    def test_star_stops_at_a_separator(self):
        self.assertTrue(self.matches('provider*.hcl', 'provider_aws.hcl'))
        self.assertFalse(self.matches('a/*/c.hcl', 'a/b/x/c.hcl'))

    def test_double_star_spans_separators(self):
        self.assertTrue(self.matches('provisioning/modules/**', 'provisioning/modules/vpc/main.tf'))

    def test_leading_double_star_matches_a_bare_name(self):
        # '**/root.hcl' has to match 'root.hcl' as well as 'a/b/root.hcl'.
        self.assertTrue(self.matches('**/root.hcl', 'root.hcl'))
        self.assertTrue(self.matches('**/root.hcl', 'a/b/root.hcl'))

    def test_question_mark_is_one_character(self):
        self.assertTrue(self.matches('a?c.hcl', 'abc.hcl'))
        self.assertFalse(self.matches('a?c.hcl', 'abbc.hcl'))

    def test_the_match_is_anchored_at_both_ends(self):
        self.assertFalse(self.matches('root.hcl', 'a/root.hcl'))
        self.assertFalse(self.matches('root.hcl', 'root.hcl.bak'))

    def test_regex_metacharacters_are_literal(self):
        self.assertTrue(self.matches('${DIR}/terragrunt.hcl', '${DIR}/terragrunt.hcl'))
        self.assertFalse(self.matches('a.hcl', 'axhcl'))


class MatchesExcludeTest(unittest.TestCase):
    def test_a_bare_name_glob_matches_the_file_name_anywhere(self):
        self.assertTrue(builder.matches_exclude('a/b/provider.hcl', ['provider*.hcl']))
        self.assertTrue(builder.matches_exclude('provider.hcl', ['provider*.hcl']))

    def test_a_path_glob_matches_the_repo_relative_path(self):
        self.assertTrue(
            builder.matches_exclude('provisioning/modules/vpc/main.tf', ['provisioning/modules/**']))
        self.assertFalse(
            builder.matches_exclude('other/modules/vpc/main.tf', ['provisioning/modules/**']))

    def test_no_globs_never_matches(self):
        self.assertFalse(builder.matches_exclude('root.hcl', []))

    def test_any_one_glob_is_enough(self):
        self.assertTrue(builder.matches_exclude('root.hcl', ['nope.hcl', 'root.hcl']))

    def test_it_does_not_warn_per_pattern(self):
        # Unusable globs are reported once by validate_exclude_globs; this runs
        # per file_pattern per dir and has to stay quiet.
        with mock.patch.object(builder, 'log') as log:
            builder.matches_exclude('root.hcl', ['', '{a,b}.hcl', 'root.hcl'])
        log.assert_not_called()


class ValidateExcludeGlobsTest(unittest.TestCase):
    def validate(self, globs):
        with mock.patch.object(builder, 'log') as log:
            kept = builder.validate_exclude_globs(globs)
        return kept, [c.args[0] for c in log.call_args_list if c.args[1] == 'WARN']

    def test_usable_globs_pass_through_quietly(self):
        globs = ['provider*.hcl', 'provisioning/modules/**', 'a?c.hcl']
        self.assertEqual(self.validate(globs), (globs, []))

    def test_nothing_to_validate(self):
        self.assertEqual(self.validate([]), ([], []))

    def test_an_empty_glob_is_dropped_and_warned_once(self):
        kept, warnings = self.validate(['', 'root.hcl'])
        self.assertEqual(kept, ['root.hcl'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('empty', warnings[0])

    def test_each_empty_glob_warns_once(self):
        kept, warnings = self.validate(['', ''])
        self.assertEqual(kept, [])
        self.assertEqual(len(warnings), 2)

    def test_untranslated_syntax_is_kept_but_called_out(self):
        # Path_glob understands these; glob_to_regex does not, so the user has
        # to hear about it rather than silently keeping the fan-out.
        for glob in ['{root,provider}.hcl', 'root.[hj]cl', '!root.hcl']:
            kept, warnings = self.validate([glob])
            self.assertEqual(kept, [glob])
            self.assertEqual(len(warnings), 1, glob)
            self.assertIn(repr(glob), warnings[0])

    def test_a_plain_glob_is_not_called_out(self):
        for glob in ['provider*.hcl', '**/root.hcl', '${DIR}/terragrunt.hcl',
                     '${DIR}/${WORKSPACE}.tfvars']:
            self.assertEqual(self.validate([glob])[1], [], glob)


class ApplyExclusionsTest(unittest.TestCase):
    patterns = [
        '${DIR}/terragrunt.hcl',
        '${DIR}/*.tf',
        'root.hcl',
        'provider.hcl',
        'provisioning/modules/vpc/**/*.tf',
        'prod/db/terragrunt.hcl',
    ]

    def apply(self, globs, dir_path='prod/app'):
        with mock.patch.object(builder, 'log') as log:
            kept = builder.apply_exclusions(list(self.patterns), globs, dir_path)
        warnings = [c.args[0] for c in log.call_args_list if c.args[1] == 'WARN']
        return kept, warnings

    def test_no_globs_keeps_every_pattern(self):
        kept, warnings = self.apply([])
        self.assertEqual(kept, self.patterns)
        self.assertEqual(warnings, [])

    def test_a_shared_include_is_dropped_and_the_rest_kept(self):
        kept, warnings = self.apply(['root.hcl'])
        self.assertNotIn('root.hcl', kept)
        self.assertEqual(kept, [p for p in self.patterns if p != 'root.hcl'])
        self.assertEqual(warnings, [])

    def test_order_is_preserved(self):
        kept, _ = self.apply(['provider*.hcl'])
        self.assertEqual(kept, [p for p in self.patterns if p != 'provider.hcl'])

    def test_dropping_the_units_own_terragrunt_hcl_warns(self):
        kept, warnings = self.apply(['terragrunt.hcl'])
        self.assertNotIn('${DIR}/terragrunt.hcl', kept)
        self.assertEqual(len(warnings), 1)
        self.assertIn('autoplan', warnings[0])
        self.assertIn('prod/app', warnings[0])

    def test_the_root_unit_is_named_in_the_warning(self):
        _, warnings = self.apply(['terragrunt.hcl'], dir_path='')
        self.assertIn('from .;', warnings[0])

    def test_dropping_everything_warns_too(self):
        kept, warnings = self.apply(['**'])
        self.assertEqual(kept, [])
        self.assertEqual(len(warnings), 2)
        self.assertIn('every file_pattern', warnings[1])


class GenerateConfigExclusionsTest(unittest.TestCase):
    deps = {
        'prod/app': {'includes': ['root.hcl', 'provider.hcl']},
        'prod/vpc': {'includes': ['root.hcl', 'provider.hcl']},
    }

    def file_patterns(self, **kwargs):
        config = generate(list(self.deps), deps=self.deps, **kwargs)
        return {d: config['dirs'][d]['when_modified']['file_patterns'] for d in self.deps}

    def test_nothing_is_dropped_by_default(self):
        for patterns in self.file_patterns().values():
            self.assertIn('root.hcl', patterns)
            self.assertIn('provider.hcl', patterns)

    def test_an_empty_list_is_the_same_as_no_flag(self):
        self.assertEqual(self.file_patterns(exclude_file_patterns=[]), self.file_patterns())

    def test_a_shared_include_is_dropped_from_every_unit(self):
        for patterns in self.file_patterns(exclude_file_patterns=['root.hcl']).values():
            self.assertNotIn('root.hcl', patterns)
            self.assertIn('provider.hcl', patterns)
            self.assertIn('${DIR}/terragrunt.hcl', patterns)

    def test_the_rest_of_the_dir_entry_is_unchanged(self):
        plain = generate(list(self.deps), deps=self.deps)['dirs']['prod/app']
        excluded = generate(
            list(self.deps),
            deps=self.deps,
            exclude_file_patterns=['root.hcl'])['dirs']['prod/app']
        self.assertNotEqual(
            excluded['when_modified']['file_patterns'],
            plain['when_modified']['file_patterns'])
        excluded['when_modified'] = plain['when_modified']
        self.assertEqual(excluded, plain)


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

    def test_exclude_file_pattern_reaches_stdout(self):
        config = self.run_main(['--exclude-file-pattern', 'terragrunt.hcl'])
        patterns = config['dirs']['prod/vpc']['when_modified']['file_patterns']
        self.assertNotIn('${DIR}/terragrunt.hcl', patterns)
        self.assertIn('${DIR}/*.tf', patterns)

    def test_no_exclude_file_pattern_leaves_stdout_alone(self):
        patterns = self.run_main([])['dirs']['prod/vpc']['when_modified']['file_patterns']
        self.assertEqual(patterns, ['${DIR}/terragrunt.hcl', '${DIR}/*.tf', '${DIR}/*.tfvars'])

    def test_an_empty_glob_never_reaches_the_dirs(self):
        with mock.patch.object(builder, 'log', wraps=builder.log) as log:
            config = self.run_main(['--exclude-file-pattern', '', '--exclude-file-pattern', 'terragrunt.hcl'])
        warnings = [c.args[0] for c in log.call_args_list if c.args[1:] == ('WARN',)]
        self.assertEqual(len([w for w in warnings if 'empty' in w]), 1)
        self.assertNotIn(
            '${DIR}/terragrunt.hcl',
            config['dirs']['prod/vpc']['when_modified']['file_patterns'])


if __name__ == '__main__':
    unittest.main()
