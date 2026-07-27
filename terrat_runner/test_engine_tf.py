import unittest

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


if __name__ == '__main__':
    unittest.main()
