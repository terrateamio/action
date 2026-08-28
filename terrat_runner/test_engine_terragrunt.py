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


class Toolchain:
    # Stands in for cmd.run_with_output. Answers `--version` per binary the
    # way tenv-installed ones do, records every command, and lets a probe fail.
    def __init__(self, terragrunt='terragrunt version v0.77.9', terragrunt_rc=0):
        self.terragrunt = terragrunt
        self.terragrunt_rc = terragrunt_rc
        self.calls = []

    def __call__(self, st, config):
        cmd = config['cmd']
        self.calls.append(cmd)

        if cmd[-1] == '--version':
            if cmd[-2] == 'terragrunt':
                return (SimpleNamespace(returncode=self.terragrunt_rc), self.terragrunt, '')
            return (SimpleNamespace(returncode=0), 'OpenTofu v1.6.3', '')

        return (SimpleNamespace(returncode=0), 'out', 'err')


def run_init(env, binary='terragrunt version v0.77.9', rc=0, version=None):
    toolchain = Toolchain(binary, rc)
    engine = engine_terragrunt.make(version=version)

    with mock.patch('engine_tf.cmd.run_with_output', side_effect=toolchain):
        with mock.patch('engine_tf.repo_config.get_create_and_select_workspace',
                        return_value=False):
            with mock.patch('engine_terragrunt.logging.warning') as warn:
                engine.init(state(dict(env), version), {})

    return (toolchain.calls, warn, engine)


LOCKED = ['flock', engine_tf.INIT_LOCK, 'terragrunt', 'init']
UNLOCKED = ['terragrunt', 'init']
PROBE_TG = ['flock', engine_tf.INIT_LOCK, 'terragrunt', '--version']
PROBE_TOFU = ['flock', engine_tf.INIT_LOCK, 'tofu', '--version']
OPTED_IN = {'TG_PROVIDER_CACHE': '1', 'TERRATEAM_TF_CMD': 'tofu'}


class DefaultPathTest(unittest.TestCase):
    def test_nothing_set_is_byte_identical_to_before(self):
        (calls, warn, _) = run_init({})
        self.assertEqual(calls, [LOCKED])
        self.assertEqual(warn.call_count, 0)

    def test_a_value_terragrunt_would_reject_is_not_a_request(self):
        # 'yes' and 'on' make Terragrunt exit with "invalid value", so the safe
        # thing is the default path, where init reports that error itself.
        for value in ('yes', 'on', 'false', '0', ''):
            (calls, _, _) = run_init({'TG_PROVIDER_CACHE': value, 'TERRATEAM_TF_CMD': 'tofu'})
            self.assertEqual(calls, [LOCKED], value)


class OptInTest(unittest.TestCase):
    def test_both_binaries_are_installed_under_the_lock_before_init(self):
        # Terragrunt shells out to tofu/terraform, which tenv installs on first
        # use. Unlocked, that install would race across dirspaces
        # (terrateam#393), so both are probed under the lock first, and in
        # that order.
        (calls, warn, _) = run_init(OPTED_IN)
        self.assertEqual(calls, [PROBE_TOFU, PROBE_TG, UNLOCKED])
        self.assertEqual(warn.call_count, 0)

    def test_without_an_underlying_command_only_terragrunt_is_probed(self):
        (calls, _, _) = run_init({'TG_PROVIDER_CACHE': '1'})
        self.assertEqual(calls, [PROBE_TG, UNLOCKED])

    def test_every_spelling_go_parsebool_accepts(self):
        for value in ('1', 't', 'T', 'true', 'True', 'TRUE'):
            (calls, _, _) = run_init({'TG_PROVIDER_CACHE': value})
            self.assertEqual(calls[-1], UNLOCKED, value)


class VersionFloorTest(unittest.TestCase):
    # Floors come from running every release 0.50.0 -> 1.1.4 with each spelling
    # set and checking whether the cache directory was populated.
    def _init_cmd(self, env, binary):
        return run_init(env, 'terragrunt version %s' % binary)[0][-1]

    def test_tg_spelling_is_read_from_0_73_0(self):
        self.assertEqual(self._init_cmd({'TG_PROVIDER_CACHE': '1'}, 'v0.73.0'), UNLOCKED)

    def test_tg_spelling_is_ignored_on_0_72_0(self):
        self.assertEqual(self._init_cmd({'TG_PROVIDER_CACHE': '1'}, 'v0.72.0'), LOCKED)

    def test_legacy_spelling_is_read_from_0_56_4(self):
        self.assertEqual(self._init_cmd({'TERRAGRUNT_PROVIDER_CACHE': '1'}, 'v0.56.4'), UNLOCKED)

    def test_legacy_spelling_is_ignored_on_0_56_3(self):
        self.assertEqual(self._init_cmd({'TERRAGRUNT_PROVIDER_CACHE': '1'}, 'v0.56.3'), LOCKED)

    def test_legacy_spelling_carries_a_0_72_user(self):
        # The window where only the legacy name exists.
        self.assertEqual(self._init_cmd({'TERRAGRUNT_PROVIDER_CACHE': '1'}, 'v0.72.0'), UNLOCKED)

    def test_legacy_spelling_is_still_honoured_on_1_1_4(self):
        self.assertEqual(self._init_cmd({'TERRAGRUNT_PROVIDER_CACHE': '1'}, 'v1.1.4'), UNLOCKED)


class PrecedenceTest(unittest.TestCase):
    # Verified against 0.77.9 and 1.1.4: a TG_ value that is present wins over
    # the legacy name, even when it is false; an empty TG_ falls through.
    def _init_cmd(self, env, binary='v0.77.9'):
        return run_init(env, 'terragrunt version %s' % binary)[0][-1]

    def test_a_false_tg_value_beats_a_true_legacy_one(self):
        self.assertEqual(
            self._init_cmd({'TG_PROVIDER_CACHE': 'false', 'TERRAGRUNT_PROVIDER_CACHE': 'true'}),
            LOCKED)

    def test_but_not_on_a_version_that_does_not_read_tg(self):
        self.assertEqual(
            self._init_cmd({'TG_PROVIDER_CACHE': 'false', 'TERRAGRUNT_PROVIDER_CACHE': 'true'},
                           'v0.72.0'),
            UNLOCKED)

    def test_an_empty_tg_value_falls_through_to_legacy(self):
        self.assertEqual(
            self._init_cmd({'TG_PROVIDER_CACHE': '', 'TERRAGRUNT_PROVIDER_CACHE': '1'}),
            UNLOCKED)


class TheBinaryDecidesTest(unittest.TestCase):
    def test_the_configured_version_is_not_trusted(self):
        # engine.version only sets a tenv default. A version file in the
        # repository can pick an older binary, and that older binary ignores
        # the flag, so the decision is made from what actually runs.
        (calls, warn, _) = run_init(OPTED_IN, 'terragrunt version v0.50.0', version='0.77.9')
        self.assertEqual(calls[-1], LOCKED)
        self.assertIn('0.50.0', ' '.join(str(a) for a in warn.call_args[0]))

    def test_latest_is_not_a_guess_here(self):
        # For workspace_cmd, 'latest' may be assumed new; for the lock it may
        # not, and there is no need: the probe says what 'latest' resolved to.
        (calls, _, _) = run_init(OPTED_IN, 'terragrunt version v0.50.0', version='latest')
        self.assertEqual(calls[-1], LOCKED)

    def test_a_failed_probe_keeps_the_lock(self):
        (calls, warn, _) = run_init(OPTED_IN, rc=1)
        self.assertEqual(calls[-1], LOCKED)
        self.assertIn('could not be determined', ' '.join(str(a) for a in warn.call_args[0]))

    def test_a_failed_probe_is_not_remembered(self):
        # init has its own three tries at installing the toolchain. If one of
        # those succeeds, workspace_cmd must look again rather than run the
        # legacy command against a Terragrunt that no longer accepts it.
        (_, _, engine) = run_init(OPTED_IN, rc=1)
        toolchain = Toolchain('terragrunt version v0.88.0')

        with mock.patch('engine_tf.cmd.run_with_output', side_effect=toolchain):
            cmd = engine.workspace_cmd(state(OPTED_IN), 'select', 'default')

        self.assertEqual(toolchain.calls, [PROBE_TG])
        self.assertEqual(cmd, ['terragrunt', 'run', '--', 'workspace', 'select', 'default'])

    def test_the_detected_version_is_reused_by_workspace_cmd(self):
        (_, _, engine) = run_init(OPTED_IN, 'terragrunt version v0.88.0')
        toolchain = Toolchain()

        with mock.patch('engine_tf.cmd.run_with_output', side_effect=toolchain):
            cmd = engine.workspace_cmd(state(OPTED_IN), 'select', 'default')

        self.assertEqual(toolchain.calls, [])
        self.assertEqual(cmd, ['terragrunt', 'run', '--', 'workspace', 'select', 'default'])

    def test_the_veto_names_the_detected_version(self):
        (_, warn, _) = run_init(OPTED_IN, 'terragrunt version v0.72.0', version='latest')
        self.assertEqual(warn.call_count, 1)
        self.assertIn('0.72.0', ' '.join(str(a) for a in warn.call_args[0]))


class WorkspaceCommandTest(unittest.TestCase):
    # Pre-existing behaviour on the default path, untouched.
    def _cmd(self, version, binary=None):
        toolchain = Toolchain(binary or 'terragrunt version v0.77.9')
        engine = engine_terragrunt.make(version=version)

        with mock.patch('engine_tf.cmd.run_with_output', side_effect=toolchain):
            return (engine.workspace_cmd(state({}, version), 'select', 'x'), toolchain.calls)

    def test_a_parseable_configured_version_needs_no_probe(self):
        (cmd, calls) = self._cmd('0.88.0')
        self.assertEqual(cmd, ['terragrunt', 'run', '--', 'workspace', 'select', 'x'])
        self.assertEqual(calls, [])

    def test_an_unparseable_version_probes_under_the_lock(self):
        (cmd, calls) = self._cmd('latest', 'terragrunt version v0.77.9')
        self.assertEqual(cmd, ['terragrunt', 'workspace', 'select', 'x'])
        self.assertEqual(calls, [PROBE_TG])


class PickleTest(unittest.TestCase):
    def test_the_engine_is_picklable(self):
        engine = pickle.loads(pickle.dumps(engine_terragrunt.make(version='0.77.9')))
        self.assertEqual(engine.tf_cmd, 'terragrunt')


if __name__ == '__main__':
    unittest.main()
