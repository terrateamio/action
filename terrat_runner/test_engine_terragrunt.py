import pickle
import unittest
from types import SimpleNamespace
from unittest import mock

import engine_terragrunt
import engine_tf


def state(env=None, version=None):
    return SimpleNamespace(
        path='dir/space',
        env=env if env is not None else {},
        working_dir='/nonexistent',
        workflow={'engine': {'name': 'tf', 'version': version}},
        repo_config={}
    )


class LockInitTest(unittest.TestCase):
    def _lock(self, version, env=None):
        return engine_terragrunt.make(version=version).lock_init(state(env, version))

    def test_locked_when_the_cache_was_not_asked_for(self):
        self.assertTrue(self._lock('0.77.9'))

    def test_locked_when_the_cache_is_turned_off(self):
        self.assertTrue(self._lock('0.77.9', {'TG_PROVIDER_CACHE': 'false'}))

    def test_unlocked_when_asked_for_on_a_supported_version(self):
        self.assertFalse(self._lock('0.77.9', {'TG_PROVIDER_CACHE': '1'}))

    def test_the_introducing_version_is_supported(self):
        self.assertFalse(self._lock('v0.56.4', {'TG_PROVIDER_CACHE': '1'}))

    def test_one_patch_earlier_is_vetoed(self):
        # The flag would be ignored by this Terragrunt, so unlocking init would
        # leave concurrent inits racing with nothing protecting them.
        self.assertTrue(self._lock('0.56.3', {'TG_PROVIDER_CACHE': '1'}))

    def test_the_legacy_spelling_is_honoured(self):
        self.assertFalse(self._lock('0.77.9', {'TERRAGRUNT_PROVIDER_CACHE': 'true'}))

    def test_latest_is_assumed_new_enough(self):
        self.assertFalse(self._lock('latest', {'TG_PROVIDER_CACHE': '1'}))

    def test_the_veto_is_warned_about_once(self):
        engine = engine_terragrunt.make(version='0.50.0')
        st = state({'TG_PROVIDER_CACHE': '1'}, '0.50.0')
        with mock.patch('engine_terragrunt.logging.warning') as warn:
            engine.lock_init(st)
        self.assertEqual(warn.call_count, 1)


class PickleTest(unittest.TestCase):
    # Every dirspace gets its engine by pickling the run state into a
    # multiprocessing worker, so cached state has to survive the round trip.
    def test_an_engine_survives_a_round_trip_before_resolving(self):
        engine = pickle.loads(pickle.dumps(engine_terragrunt.make(version='0.77.9')))
        self.assertFalse(engine.lock_init(state({'TG_PROVIDER_CACHE': '1'}, '0.77.9')))

    def test_an_engine_survives_a_round_trip_after_resolving(self):
        engine = engine_terragrunt.make(version='0.77.9')
        engine.lock_init(state({'TG_PROVIDER_CACHE': '1'}, '0.77.9'))
        engine = pickle.loads(pickle.dumps(engine))
        self.assertFalse(engine.lock_init(state({'TG_PROVIDER_CACHE': '1'}, '0.77.9')))

    def test_workspace_selection_survives_a_round_trip(self):
        engine = pickle.loads(pickle.dumps(engine_terragrunt.make(version='0.77.9')))
        self.assertEqual(
            engine.workspace_cmd(state(version='0.77.9'), 'select', 'default'),
            ['terragrunt', 'workspace', 'select', 'default'])


class InitCommandTest(unittest.TestCase):
    def _calls(self, version, env):
        engine = engine_terragrunt.make(version=version)

        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
            with mock.patch('engine_tf.repo_config.get_create_and_select_workspace',
                            return_value=False):
                engine.init(state(env, version), {})

        return [c[0][1]['cmd'] for c in run.call_args_list]

    def test_default_is_unchanged_from_before(self):
        self.assertEqual(
            self._calls('0.77.9', {}),
            [['flock', engine_tf.INIT_LOCK, 'terragrunt', '--version'],
             ['flock', engine_tf.INIT_LOCK, 'terragrunt', 'init']])

    def test_opting_in_unlocks_init_but_not_the_install(self):
        self.assertEqual(
            self._calls('0.77.9', {'TG_PROVIDER_CACHE': '1'}),
            [['flock', engine_tf.INIT_LOCK, 'terragrunt', '--version'],
             ['terragrunt', 'init']])

    def test_an_old_version_keeps_both_locks(self):
        self.assertEqual(
            self._calls('0.50.0', {'TG_PROVIDER_CACHE': '1'}),
            [['flock', engine_tf.INIT_LOCK, 'terragrunt', '--version'],
             ['flock', engine_tf.INIT_LOCK, 'terragrunt', 'init']])


class NoVersionProbeRaceTest(unittest.TestCase):
    def test_the_version_is_probed_after_the_toolchain_install(self):
        # _detect_installed_version shells out to `terragrunt --version`, which
        # with TENV_AUTO_INSTALL is itself an install. It must not run before
        # the serialised install has happened.
        engine = engine_terragrunt.make()
        order = []

        with mock.patch('engine_tf.cmd.run_with_output') as run:
            run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
            run.side_effect = lambda s, c: (order.append(c['cmd'][-1]),
                                            (SimpleNamespace(returncode=0), 'o', 'e'))[1]
            with mock.patch.object(engine_terragrunt.Engine, '_detect_installed_version',
                                   side_effect=lambda s: order.append('probe')):
                with mock.patch('engine_tf.repo_config.get_create_and_select_workspace',
                                return_value=False):
                    engine.init(state({'TG_PROVIDER_CACHE': '1'}), {})

        self.assertEqual(order.index('--version') < order.index('probe'), True)


if __name__ == '__main__':
    unittest.main()
