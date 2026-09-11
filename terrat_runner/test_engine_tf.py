import pickle
import unittest
from types import SimpleNamespace
from unittest import mock

import engine_tf

def fmt(lines):
    return engine_tf.format_diff('\n'.join(lines))


def joined(lines):
    return '\n'.join(lines)


class FormatDiffTest(unittest.TestCase):
    def test_promotes_markers_outside_heredoc(self):
        # The original behaviour: a leading +/-/~ (with its indent) moves to
        # column 0 so the diff highlighter colours the line, and ~ becomes !.
        plan = [
            '  + resource "x" {',
            '      + id = 1',
            '    }',
            '  ~ resource "y" {',
            '      - id = 2',
            '    }',
        ]
        expected = [
            '+   resource "x" {',
            '+       id = 1',
            '    }',
            '!   resource "y" {',
            '-       id = 2',
            '    }',
        ]
        self.assertEqual(fmt(plan), joined(expected))

    def test_unchanged_heredoc_body_is_verbatim(self):
        # A heredoc whose value did not change is shown with its YAML body at a
        # fixed indent and no per-line gutter; the `- ` list items must not be
        # promoted to removals.
        plan = [
            '  ~ values = <<-EOT',
            '        "appListenPorts":',
            '        - "name": "http"',
            '          "port": 8000',
            '    EOT',
        ]
        expected = [
            '!   values = <<-EOT',
            '        "appListenPorts":',
            '        - "name": "http"',
            '          "port": 8000',
            '    EOT',
        ]
        self.assertEqual(fmt(plan), joined(expected))

    def test_inplace_heredoc_diff_uses_gutter(self):
        # An in-place (~) change renders the body as a line-by-line diff with a
        # 2-char gutter. Real +/- markers sit in the gutter, to the left of the
        # YAML content; unchanged list items sit at the content column and must
        # be left alone.
        plan = [
            '  ~ v = <<-EOT',
            '        "env":',
            '        - "name": "ENV"',
            '          "value": "preview"',
            '      + - "name": "NEW"',
            '      +   "value": "x"',
            '      - - "name": "OLD"',
            '      -   "value": "y"',
            '    EOT',
        ]
        expected = [
            '!   v = <<-EOT',
            '        "env":',
            '        - "name": "ENV"',
            '          "value": "preview"',
            '+       - "name": "NEW"',
            '+         "value": "x"',
            '-       - "name": "OLD"',
            '-         "value": "y"',
            '    EOT',
        ]
        self.assertEqual(fmt(plan), joined(expected))

    def test_inplace_heredoc_with_nested_yaml_list(self):
        # Regression for nested YAML: the real removals sit two columns left of
        # the unchanged `- ` list items, so the gutter must be found from the
        # shallowest column, not "content minus two".
        plan = [
            '  ~ data = <<-EOT',
            '                - "name": "keep"',
            '                  "rolearn": "arn:aws:iam::111:role/keep"',
            '              -   "rolearn": "arn:aws:iam::111:role/gone"',
            '              - - "groups":',
            '              -   - "system:masters"',
            '                  "rolearn": "arn:aws:iam::111:role/keep2"',
            '    EOT',
        ]
        expected = [
            '!   data = <<-EOT',
            '                - "name": "keep"',
            '                  "rolearn": "arn:aws:iam::111:role/keep"',
            '-                 "rolearn": "arn:aws:iam::111:role/gone"',
            '-               - "groups":',
            '-                 - "system:masters"',
            '                  "rolearn": "arn:aws:iam::111:role/keep2"',
            '    EOT',
        ]
        self.assertEqual(fmt(plan), joined(expected))

    def test_whole_value_removal_keeps_body_verbatim(self):
        # When the whole value is removed (`-` opener) the body is emitted
        # verbatim -- Terraform does not diff inside it, so its `- ` list items
        # must not be promoted.
        plan = [
            '  - maproles = <<-EOT',
            '        - "name": "a"',
            '          "rolearn": "arn:aws:iam::111:role/a"',
            '        - "name": "b"',
            '          "rolearn": "arn:aws:iam::111:role/b"',
            '    EOT',
        ]
        expected = [
            '-   maproles = <<-EOT',
            '        - "name": "a"',
            '          "rolearn": "arn:aws:iam::111:role/a"',
            '        - "name": "b"',
            '          "rolearn": "arn:aws:iam::111:role/b"',
            '    EOT',
        ]
        self.assertEqual(fmt(plan), joined(expected))

    def test_whole_value_add_keeps_body_verbatim(self):
        plan = [
            '  + cfg = <<-EOT',
            '        - "a"',
            '        - "b"',
            '    EOT',
        ]
        expected = [
            '+   cfg = <<-EOT',
            '        - "a"',
            '        - "b"',
            '    EOT',
        ]
        self.assertEqual(fmt(plan), joined(expected))

    def test_multiple_heredocs_and_custom_delimiter(self):
        # Several heredocs in one diff, with a non-EOT delimiter; the body of one
        # must not swallow the opener of the next.
        plan = [
            '  ~ a = <<-EOF',
            '        "x": 1',
            '        - "item"',
            '    EOF',
            '  ~ b = <<HD',
            '        "y": 2',
            '      - - "gone"',
            '    HD',
        ]
        expected = [
            '!   a = <<-EOF',
            '        "x": 1',
            '        - "item"',
            '    EOF',
            '!   b = <<HD',
            '        "y": 2',
            '-       - "gone"',
            '    HD',
        ]
        self.assertEqual(fmt(plan), joined(expected))


class ApplyTest(unittest.TestCase):
    def test_apply_without_plan_does_not_pass_plan_file(self):
        state = SimpleNamespace(
            path='.',
            workflow={'engine': {'name': 'terraform'}}
        )
        engine = engine_tf.make(override_tf_cmd='terraform')

        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')

            result = engine.apply_without_plan(state, {'extra_args': ['-target=module.foo']})

        self.assertEqual(result, (True, 'out', 'err'))
        self.assertEqual(
            run.call_args[0][1]['cmd'],
            ['terraform', 'apply', '-auto-approve', '-target=module.foo'])


class Unlocked(engine_tf.Engine):
    # The way a real engine opts out: by overriding the hook, not by poking an
    # attribute. Keeps the engine picklable, which the run state requires.
    def lock_init(self, state):
        return False


def _state():
    return SimpleNamespace(
        path='dir/space',
        env={},
        working_dir='/nonexistent',
        workflow={'engine': {'name': 'terraform'}},
        repo_config={}
    )


class InitTest(unittest.TestCase):
    def _calls(self, engine, config=None):
        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
            with mock.patch('engine_tf.repo_config.get_create_and_select_workspace',
                            return_value=False):
                engine.init(_state(), config or {})

        return [c[0][1]['cmd'] for c in run.call_args_list]

    def test_the_default_path_is_byte_identical_to_before(self):
        # A locked init already serialises the tenv install, which is the whole
        # of terrateam#393, so nothing is added for anyone who changes nothing.
        # This is the blast radius of the change: none.
        self.assertEqual(
            self._calls(engine_tf.make(override_tf_cmd='terraform')),
            [['flock', engine_tf.INIT_LOCK, 'terraform', 'init']])

    def test_tofu_is_the_same(self):
        self.assertEqual(
            self._calls(engine_tf.make(override_tf_cmd='tofu')),
            [['flock', engine_tf.INIT_LOCK, 'tofu', 'init']])

    def test_an_engine_that_unlocks_gets_a_bare_init(self):
        # And nothing else: the contract puts the toolchain install on the
        # engine that chose to unlock, not on this base class.
        self.assertEqual(
            self._calls(Unlocked('tf', 'terraform')),
            [['terraform', 'init']])

    def test_extra_args_on_the_locked_path(self):
        self.assertEqual(
            self._calls(engine_tf.make(override_tf_cmd='terraform'), {'extra_args': ['-upgrade']}),
            [['flock', engine_tf.INIT_LOCK, 'terraform', 'init', '-upgrade']])

    def test_extra_args_on_the_unlocked_path(self):
        self.assertEqual(
            self._calls(Unlocked('tf', 'terraform'), {'extra_args': ['-upgrade']}),
            [['terraform', 'init', '-upgrade']])


class ProbeToolchainTest(unittest.TestCase):
    def _probe(self, tf_cmd, returncode, stdout='', stderr=''):
        engine = engine_tf.make(override_tf_cmd='terraform')

        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=returncode), stdout, stderr)
            with mock.patch('engine_tf.logging.warning') as warn:
                result = engine.probe_toolchain(_state(), tf_cmd)

        return (run.call_args[0][1], warn, result)

    def test_the_probe_takes_the_init_lock(self):
        (config, _, _) = self._probe('tofu', 0)
        self.assertEqual(config['cmd'], ['flock', engine_tf.INIT_LOCK, 'tofu', '--version'])

    def test_the_probe_is_quiet_in_the_job_log(self):
        (config, _, _) = self._probe('tofu', 0)
        self.assertFalse(config['log_output'])

    def test_a_successful_probe_does_not_warn(self):
        (_, warn, result) = self._probe('tofu', 0, 'OpenTofu v1.6.3')
        self.assertEqual(warn.call_count, 0)
        self.assertEqual(result, (0, 'OpenTofu v1.6.3', ''))

    def test_an_install_is_reported_at_info(self):
        # tenv says nothing when the binary is already there, so this line
        # appears only on the dirspace that actually installed it.
        engine = engine_tf.make(override_tf_cmd='terraform')
        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), 'OpenTofu v1.8.1',
                                'Resolved version from TOFUENV_TOFU_DEFAULT_VERSION : 1.8.1\nInstalling OpenTofu 1.8.1\n')
            with mock.patch('engine_tf.logging.info') as info:
                engine.probe_toolchain(_state(), 'tofu')
        self.assertEqual(info.call_count, 1)
        self.assertIn('Installing OpenTofu 1.8.1', ' '.join(str(a) for a in info.call_args[0]))

    def test_an_already_installed_binary_is_silent(self):
        # Including when the tool itself grumbles on stderr, as Terragrunt does
        # about TF_INPUT: that is not an install and must not look like one.
        for stderr in ('', 'WARN   The `TF_INPUT` environment variable is deprecated'):
            engine = engine_tf.make(override_tf_cmd='terraform')
            with mock.patch('engine_tf.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), 'OpenTofu v1.8.1', stderr)
                with mock.patch('engine_tf.logging.info') as info:
                    engine.probe_toolchain(_state(), 'tofu')
            self.assertEqual(info.call_count, 0, stderr)

    def test_a_failed_probe_warns_with_the_reason(self):
        # log_output is False, so this is otherwise invisible and the operator
        # only sees the init failure that follows, which looks unrelated.
        (_, warn, result) = self._probe('tofu', 42, '', 'no such version')
        self.assertEqual(warn.call_count, 1)
        self.assertIn('no such version', ' '.join(str(a) for a in warn.call_args[0]))
        self.assertEqual(result[0], 42)


class PickleTest(unittest.TestCase):
    # The run state, engine included, is pickled into a multiprocessing.Pool
    # for every dirspace, so an engine that cannot be pickled breaks the run
    # before init is reached.
    def test_engines_are_picklable(self):
        for engine in (engine_tf.make(override_tf_cmd='terraform'), Unlocked('tf', 'terraform')):
            self.assertEqual(pickle.loads(pickle.dumps(engine)).tf_cmd, 'terraform')


if __name__ == '__main__':
    unittest.main()
