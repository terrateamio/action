import io
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

import cmd


def _state():
    return SimpleNamespace(
        env=dict(os.environ),
        runtime=SimpleNamespace(is_command=lambda _line: False),
        working_dir='.')


class RunWithOutputTest(unittest.TestCase):
    CMD = ['sh', '-c', 'echo out; echo err >&2']

    def _run(self, config):
        with mock.patch('cmd.sys.stderr', new_callable=io.StringIO) as log:
            (proc, stdout, stderr) = cmd.run_with_output(_state(), config)

        self.assertEqual(proc.returncode, 0)
        self.assertEqual(stdout, 'out\n')
        self.assertEqual(stderr, 'err\n')
        return log.getvalue()

    def test_logs_output_by_default(self):
        log = self._run({'cmd': self.CMD})

        self.assertIn('stdout: out', log)
        self.assertIn('stderr: err', log)

    def test_log_output_false_captures_without_logging(self):
        self.assertEqual(self._run({'cmd': self.CMD, 'log_output': False}), '')


class RunTest(unittest.TestCase):
    def test_log_output_false_discards_stdout_and_stderr(self):
        with mock.patch('cmd.subprocess.run') as run:
            cmd.run(_state(), {'cmd': ['true'], 'log_output': False})

        self.assertIs(run.call_args[1]['stdout'], subprocess.DEVNULL)
        self.assertIs(run.call_args[1]['stderr'], subprocess.DEVNULL)

    def test_inherits_stdout_and_stderr_by_default(self):
        with mock.patch('cmd.subprocess.run') as run:
            cmd.run(_state(), {'cmd': ['true']})

        self.assertNotIn('stdout', run.call_args[1])
        self.assertNotIn('stderr', run.call_args[1])


if __name__ == '__main__':
    unittest.main()
