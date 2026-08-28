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


class InitTest(unittest.TestCase):
    def _calls(self, engine, config=None):
        state = SimpleNamespace(
            path='.',
            env={},
            working_dir='/nonexistent',
            workflow={'engine': {'name': 'terraform'}},
            repo_config={}
        )

        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
            with mock.patch('engine_tf.repo_config.get_create_and_select_workspace',
                            return_value=False):
                engine.init(state, config or {})

        return [c[0][1]['cmd'] for c in run.call_args_list]

    def _unlocked(self, tf_cmd='terraform'):
        engine = engine_tf.make(override_tf_cmd=tf_cmd)
        engine.lock_init = lambda state: False
        return engine

    def test_the_default_path_is_byte_identical_to_before(self):
        # A locked init already serialises the tenv install, which is the whole
        # of terrateam#393, so nothing is added for anyone who changes nothing.
        # This is the blast radius of the change: none.
        self.assertEqual(
            self._calls(engine_tf.make(override_tf_cmd='terraform')),
            [['flock', engine_tf.INIT_LOCK, 'terraform', 'init']])

    def test_the_default_path_adds_no_extra_subprocess(self):
        self.assertEqual(len(self._calls(engine_tf.make(override_tf_cmd='terraform'))), 1)

    def test_unlocking_init_adds_the_serialised_install(self):
        # Without the lock on init, nothing else serialises the tenv install.
        self.assertEqual(
            self._calls(self._unlocked()),
            [['flock', engine_tf.INIT_LOCK, 'terraform', '--version'],
             ['terraform', 'init']])

    def test_extra_args_reach_init_and_not_the_probe(self):
        self.assertEqual(
            self._calls(self._unlocked(), {'extra_args': ['-upgrade']}),
            [['flock', engine_tf.INIT_LOCK, 'terraform', '--version'],
             ['terraform', 'init', '-upgrade']])

    def test_extra_args_on_the_locked_path(self):
        self.assertEqual(
            self._calls(engine_tf.make(override_tf_cmd='terraform'), {'extra_args': ['-upgrade']}),
            [['flock', engine_tf.INIT_LOCK, 'terraform', 'init', '-upgrade']])

    def test_tofu_probes_its_own_toolchain(self):
        self.assertEqual(self._calls(self._unlocked('tofu'))[0],
                         ['flock', engine_tf.INIT_LOCK, 'tofu', '--version'])

    def test_a_failed_toolchain_install_is_reported(self):
        # log_output is False, so a failure here is otherwise invisible and the
        # operator only sees a confusing init failure afterwards.
        state = SimpleNamespace(path='dir/space', env={}, working_dir='/nonexistent',
                                workflow={'engine': {'name': 'terraform'}}, repo_config={})
        engine = engine_tf.make(override_tf_cmd='terraform')

        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=1), 'out', 'boom')
            with mock.patch('engine_tf.logging.warning') as warn:
                engine.install_toolchain(state)

        self.assertEqual(warn.call_count, 1)
        self.assertIn('boom', ' '.join(str(a) for a in warn.call_args[0]))

    def test_a_successful_toolchain_install_is_quiet(self):
        state = SimpleNamespace(path='dir/space', env={}, working_dir='/nonexistent',
                                workflow={'engine': {'name': 'terraform'}}, repo_config={})
        engine = engine_tf.make(override_tf_cmd='terraform')

        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), 'out', '')
            with mock.patch('engine_tf.logging.warning') as warn:
                engine.install_toolchain(state)

        self.assertEqual(warn.call_count, 0)


if __name__ == '__main__':
    unittest.main()
