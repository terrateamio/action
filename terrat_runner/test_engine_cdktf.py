import unittest
from types import SimpleNamespace
from unittest import mock

import engine_cdktf
import engine_tf


class InitDelegationTest(unittest.TestCase):
    # engine_cdktf.Engine.init runs `cdktf get` and `cdktf synth` and then hands
    # off to engine_tf.Engine.init, so it inherits the serialized toolchain
    # install and the init lock. This asserts that handoff, because cdktf is the
    # engine least likely to be exercised end to end.
    #
    # engine_cdktf and engine_tf share the same `cmd` module object, so one
    # patch captures the whole sequence.
    def _sequence(self):
        state = SimpleNamespace(
            path='cdktf/dir',
            env={},
            working_dir='/nonexistent',
            workflow={'engine': {'name': 'tf'}},
            repo_config={}
        )
        engine = engine_cdktf.make(override_tf_cmd='terraform')

        with mock.patch('engine_tf.cmd.run_with_output') as run, \
             mock.patch('engine_cdktf._run', side_effect=lambda s, c, f: f(s, c)):
            run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
            engine.init(state, {})

        return [c[0][1]['cmd'] for c in run.call_args_list]

    def test_the_whole_init_sequence(self):
        self.assertEqual(
            self._sequence(),
            [['cdktf', 'get'],
             ['cdktf', 'synth'],
             ['flock', engine_tf.INIT_LOCK, 'terraform', 'init']])

    def test_init_is_still_locked_for_cdktf(self):
        self.assertIn(['flock', engine_tf.INIT_LOCK, 'terraform', 'init'], self._sequence())
