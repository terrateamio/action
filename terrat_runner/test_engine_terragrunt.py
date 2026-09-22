import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import engine_terragrunt


def _state(working_dir, **extra):
    return SimpleNamespace(
        path='.',
        working_dir=working_dir,
        workflow={'engine': {'name': 'terragrunt'}},
        env={'TERRATEAM_PLAN_FILE': '/tmp/plan', 'TG_DEFAULT_VERSION': 'latest'},
        **extra)


class IsStackTest(unittest.TestCase):
    def test_true_when_stack_file_present(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            self.assertTrue(engine._is_stack(_state(d)))

    def test_false_when_stack_file_absent(self):
        with tempfile.TemporaryDirectory() as d:
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            self.assertFalse(engine._is_stack(_state(d)))

    def test_result_is_cached(self):
        with tempfile.TemporaryDirectory() as d:
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)
            self.assertFalse(engine._is_stack(state))
            # Even if a stack file shows up afterwards, the cached engine
            # instance should not re-detect -- one Engine is used for one
            # dirspace for the lifetime of a job.
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            self.assertFalse(engine._is_stack(state))


class InitTest(unittest.TestCase):
    def test_non_stack_dir_delegates_to_base_engine(self):
        with tempfile.TemporaryDirectory() as d:
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
                result = engine.init(state, {}, create_and_select_workspace=False)

            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['flock', '/tmp/tf-init.lock', 'terragrunt', 'init'])
            self.assertEqual(result, (True, 'out', 'err'))

    def test_stack_dir_skips_init(self):
        # terragrunt init in the Stack root fails the same way outputs()/show
        # do (no terragrunt.hcl there); `stack run plan`/`apply` initialize
        # each generated unit themselves, so this step is a no-op for a
        # Stack, not just unsafe to run as written.
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                result = engine.init(state, {})

            self.assertEqual(result, (True, '', ''))
            run.assert_not_called()


class PlanTest(unittest.TestCase):
    def test_non_stack_dir_delegates_to_base_engine(self):
        with tempfile.TemporaryDirectory() as d:
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
                engine.plan(state, {})

            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['terragrunt', 'plan', '-detailed-exitcode', '-out', '${TERRATEAM_PLAN_FILE}'])

    def test_stack_dir_uses_stack_run_plan(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run, \
                 mock.patch.object(engine, '_tar_stack_artifact') as tar_stack_artifact:
                run.return_value = (SimpleNamespace(returncode=2), 'out', 'err')
                result = engine.plan(state, {'extra_args': ['-var=foo=bar']})

            out_dir = os.path.join(d, '.terrateam-stack-plans')
            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['terragrunt', 'stack', 'run', 'plan',
                 '--out-dir', out_dir,
                 '--non-interactive',
                 '--',
                 '-detailed-exitcode',
                 '-var=foo=bar'])
            # exit code 2 == has changes, and must still be treated as success.
            self.assertEqual(result, (True, True, 'out', 'err'))
            tar_stack_artifact.assert_called_once_with(state)

    def test_stack_plan_failure_does_not_tar(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run, \
                 mock.patch.object(engine, '_tar_stack_artifact') as tar_stack_artifact:
                run.return_value = (SimpleNamespace(returncode=1), 'out', 'err')
                result = engine.plan(state, {})

            self.assertEqual(result, (False, False, 'out', 'err'))
            tar_stack_artifact.assert_not_called()

    def test_stack_plan_inspects_unit_plans_when_exit_code_is_zero(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run, \
                 mock.patch.object(engine, '_tar_stack_artifact') as tar_stack_artifact, \
                 mock.patch.object(engine, '_stack_plan_has_changes', return_value=(True, True, '')) as inspect:
                run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
                result = engine.plan(state, {})

            self.assertEqual(result, (True, True, 'out', 'err'))
            inspect.assert_called_once_with(state)
            tar_stack_artifact.assert_called_once_with(state)

    def test_stack_plan_fails_safely_when_zero_exit_code_cannot_be_inspected(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run, \
                 mock.patch.object(engine, '_tar_stack_artifact') as tar_stack_artifact, \
                 mock.patch.object(engine, '_stack_plan_has_changes', return_value=(False, False, 'show failed')):
                run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
                result = engine.plan(state, {})

            self.assertEqual(result, (False, False, 'out', 'err\nshow failed'))
            tar_stack_artifact.assert_not_called()


class StackArtifactTest(unittest.TestCase):
    def test_artifact_contains_manifest_root_config_and_plans_only(self):
        with tempfile.TemporaryDirectory() as d:
            plan_file = os.path.join(d, 'plan.tar')
            state = _state(d)
            state.env['TERRATEAM_PLAN_FILE'] = plan_file
            with open(os.path.join(d, 'terragrunt.stack.hcl'), 'w') as f:
                f.write('unit "app" {}')
            plan_dir = os.path.join(d, '.terrateam-stack-plans', 'app')
            os.makedirs(plan_dir)
            open(os.path.join(plan_dir, 'tfplan.tfplan'), 'w').close()
            runtime_dir = os.path.join(d, '.terragrunt-stack', 'app', '.terraform')
            os.makedirs(runtime_dir)
            open(os.path.join(runtime_dir, 'provider'), 'w').close()

            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            engine._tar_stack_artifact(state)

            with tarfile.open(plan_file) as tar:
                names = tar.getnames()
            self.assertIn('.terrateam-stack-artifact.json', names)
            self.assertIn('stack/terragrunt.stack.hcl', names)
            self.assertIn('.terrateam-stack-plans/app/tfplan.tfplan', names)
            self.assertFalse(any('.terraform' in name for name in names))
            self.assertEqual(engine._load_stack_artifact_manifest(state)['engine'], 'terragrunt-stack')


class RestoreStackArtifactTest(unittest.TestCase):
    def _make_artifact(self, plan_file, stack_config, manifest_config_for_hash=None):
        manifest_bytes = json.dumps({
            'format_version': engine_terragrunt.STACK_ARTIFACT_VERSION,
            'engine': 'terragrunt-stack',
            'stack_root': '.',
            'stack_config_sha256': hashlib.sha256(manifest_config_for_hash or stack_config).hexdigest(),
        }).encode('utf-8')
        with tarfile.open(plan_file, 'w') as tar:
            info = tarfile.TarInfo(engine_terragrunt.STACK_ARTIFACT_MANIFEST)
            info.size = len(manifest_bytes)
            tar.addfile(info, io.BytesIO(manifest_bytes))
            info = tarfile.TarInfo('stack/terragrunt.stack.hcl')
            info.size = len(stack_config)
            tar.addfile(info, io.BytesIO(stack_config))
            plans_dir_info = tarfile.TarInfo('.terrateam-stack-plans')
            plans_dir_info.type = tarfile.DIRTYPE
            tar.addfile(plans_dir_info)

    def test_rejects_when_checksum_does_not_match_manifest(self):
        # Simulates a corrupted or hand-edited artifact: the manifest's
        # recorded hash doesn't match what's actually stored in the tar.
        with tempfile.TemporaryDirectory() as d:
            plan_file = os.path.join(d, 'plan.tar')
            state = _state(d)
            state.env['TERRATEAM_PLAN_FILE'] = plan_file
            self._make_artifact(
                plan_file,
                stack_config=b'unit "app" {}',
                manifest_config_for_hash=b'unit "other" {}')

            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            manifest = engine._load_stack_artifact_manifest(state)

            with self.assertRaisesRegex(ValueError, 'checksum does not match'):
                engine._restore_stack_artifact(state, manifest)

    def test_rejects_when_root_config_changed_after_plan(self):
        # Simulates a later commit landing on the apply checkout's branch
        # between plan and apply that edits the Stack root config -- applying
        # the old saved plan against a changed root config could apply
        # against the wrong values/units.
        with tempfile.TemporaryDirectory() as d:
            plan_file = os.path.join(d, 'plan.tar')
            state = _state(d)
            state.env['TERRATEAM_PLAN_FILE'] = plan_file
            self._make_artifact(plan_file, stack_config=b'unit "app" {}')

            with open(os.path.join(d, 'terragrunt.stack.hcl'), 'wb') as f:
                f.write(b'unit "app" {}\nunit "extra" {}')

            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            manifest = engine._load_stack_artifact_manifest(state)

            with self.assertRaisesRegex(ValueError, 'changed after plan'):
                engine._restore_stack_artifact(state, manifest)

    def test_rejects_symlink_member_escaping_workspace(self):
        # A member's own name can look safe (no "..", stays under
        # .terrateam-stack-plans/) while still being a symlink whose link
        # target escapes the workspace -- a later apply() run reuses this
        # same directory as Terragrunt's --out-dir, so a symlink planted here
        # would redirect Terragrunt's real writes outside the checkout
        # (CVE-2007-4559-class). The name-only commonpath check does not
        # catch this; extractall's filter='data' does.
        with tempfile.TemporaryDirectory() as d:
            plan_file = os.path.join(d, 'plan.tar')
            state = _state(d)
            state.env['TERRATEAM_PLAN_FILE'] = plan_file
            self._make_artifact(plan_file, stack_config=b'unit "app" {}')

            with tarfile.open(plan_file, 'a') as tar:
                link_info = tarfile.TarInfo('.terrateam-stack-plans/evil')
                link_info.type = tarfile.SYMTYPE
                link_info.linkname = '/etc'
                tar.addfile(link_info)

            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            manifest = engine._load_stack_artifact_manifest(state)

            with self.assertRaises(tarfile.TarError):
                engine._restore_stack_artifact(state, manifest)


class StackPlanChangesTest(unittest.TestCase):
    def test_resource_change_is_detected(self):
        engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
        payload = json.dumps({
            'resource_changes': [{'change': {'actions': ['create']}}],
        })

        with mock.patch.object(engine, '_stack_show', return_value=(True, [('unit', True, payload, '')])):
            self.assertEqual(engine._stack_plan_has_changes(_state('/tmp')), (True, True, ''))

    def test_output_change_is_detected(self):
        engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
        payload = json.dumps({
            'output_changes': {'endpoint': {'actions': ['update']}},
        })

        with mock.patch.object(engine, '_stack_show', return_value=(True, [('unit', True, payload, '')])):
            self.assertEqual(engine._stack_plan_has_changes(_state('/tmp')), (True, True, ''))

    def test_noop_plans_are_not_changes(self):
        engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
        payload = json.dumps({
            'resource_changes': [{'change': {'actions': ['no-op']}}],
        })

        with mock.patch.object(engine, '_stack_show', return_value=(True, [('unit', True, payload, '')])):
            self.assertEqual(engine._stack_plan_has_changes(_state('/tmp')), (True, False, ''))


class ApplyTest(unittest.TestCase):
    def test_non_stack_dir_delegates_to_base_engine(self):
        with tempfile.TemporaryDirectory() as d:
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
                engine.apply(state, {})

            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['terragrunt', 'apply', '${TERRATEAM_PLAN_FILE}'])

    def test_stack_dir_restores_artifact_then_runs_stack_apply(self):
        with tempfile.TemporaryDirectory() as d:
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run, \
                 mock.patch.object(engine, '_load_stack_artifact_manifest', return_value={
                     'stack_root': '.',
                 }), \
                 mock.patch.object(engine, '_restore_stack_artifact') as restore_stack_artifact:
                run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
                result = engine.apply(state, {})

            out_dir = os.path.join(d, '.terrateam-stack-plans')
            restore_stack_artifact.assert_called_once_with(state, {'stack_root': '.'})
            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['terragrunt', 'stack', 'run', 'apply',
                 '--out-dir', out_dir,
                 '--non-interactive'])
            self.assertEqual(result, (True, 'out', 'err'))


class ApplyWithoutPlanTest(unittest.TestCase):
    def test_non_stack_dir_delegates_to_base_engine(self):
        with tempfile.TemporaryDirectory() as d:
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
                engine.apply_without_plan(state, {})

            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['terragrunt', 'apply', '-auto-approve'])

    def test_stack_dir_uses_stack_run_apply_without_restoring_artifact(self):
        # There's no saved plan artifact for apply_without_plan by definition
        # -- `stack run apply` generates the units and applies live in one
        # step, the Stack equivalent of plain `terraform apply -auto-approve`.
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run, \
                 mock.patch.object(engine, '_restore_stack_artifact') as restore_stack_artifact:
                run.return_value = (SimpleNamespace(returncode=0), 'out', 'err')
                result = engine.apply_without_plan(state, {})

            out_dir = os.path.join(d, '.terrateam-stack-plans')
            restore_stack_artifact.assert_not_called()
            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['terragrunt', 'stack', 'run', 'apply',
                 '--out-dir', out_dir,
                 '--non-interactive'])
            self.assertEqual(result, (True, 'out', 'err'))


class StackShowTest(unittest.TestCase):
    def _make_unit_plan(self, out_dir, unit):
        unit_dir = os.path.join(out_dir, unit)
        os.makedirs(unit_dir, exist_ok=True)
        open(os.path.join(unit_dir, 'tfplan.tfplan'), 'w').close()

    def test_diff_concatenates_all_units(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            out_dir = os.path.join(d, '.terrateam-stack-plans')
            self._make_unit_plan(out_dir, 'vpc')
            self._make_unit_plan(out_dir, 'app')

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), 'no changes', 'err')
                (ok, stdout, stderr) = engine.diff(state, {})

            self.assertTrue(ok)
            self.assertIn('# unit: vpc', stdout)
            self.assertIn('# unit: app', stdout)
            self.assertEqual(run.call_count, 2)

    def test_diff_json_returns_dict_keyed_by_unit(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            out_dir = os.path.join(d, '.terrateam-stack-plans')
            self._make_unit_plan(out_dir, 'vpc')

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), '{"format_version": "1.0"}', 'err')
                (ok, payload) = engine.diff_json(state, {})

            self.assertTrue(ok)
            self.assertEqual(payload, {'vpc': {'format_version': '1.0'}})

    def test_show_cmd_uses_working_dir_flag_pointing_at_generated_unit(self):
        # --out-dir only copies the plan file, not the unit's terragrunt.hcl
        # (that stays where `stack generate` originally wrote it, under
        # working_dir/<unit>, not under out_dir/<unit>). Plain `terragrunt
        # show` run with cwd=working_dir (the stack root, which only has
        # terragrunt.stack.hcl) fails outright, so the command must pass
        # --working-dir pointing at the real generated unit directory.
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            out_dir = os.path.join(d, '.terrateam-stack-plans')
            self._make_unit_plan(out_dir, 'vpc')

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), 'no changes', 'err')
                engine.diff(state, {})

            plan_path = os.path.join(out_dir, 'vpc', 'tfplan.tfplan')
            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['terragrunt', '--working-dir', os.path.join(d, 'vpc'), 'show', plan_path])

    def test_diff_untars_when_units_dir_missing(self):
        # Simulates a fresh job (e.g. a re-run) where the plan directory was
        # never populated by plan() in this process and must come back from
        # TERRATEAM_PLAN_FILE instead.
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)
            out_dir = os.path.join(d, '.terrateam-stack-plans')

            def fake_restore(_state, _manifest):
                self._make_unit_plan(out_dir, 'vpc')

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run, \
                 mock.patch.object(engine, '_load_stack_artifact_manifest', return_value={}), \
                 mock.patch.object(engine, '_restore_stack_artifact', side_effect=fake_restore) as restore_stack_artifact:
                run.return_value = (SimpleNamespace(returncode=0), 'no changes', 'err')
                engine.diff(state, {})

            restore_stack_artifact.assert_called_once_with(state, {})


class OutputsTest(unittest.TestCase):
    def test_non_stack_dir_delegates_to_base_engine(self):
        with tempfile.TemporaryDirectory() as d:
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                run.return_value = (SimpleNamespace(returncode=0), '{}', 'err')
                engine.outputs(state, {})

            self.assertEqual(
                run.call_args[0][1]['cmd'],
                ['terragrunt', 'output', '-json'])

    def test_stack_dir_skips_collection(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'terragrunt.stack.hcl'), 'w').close()
            engine = engine_terragrunt.make(override_tf_cmd='terragrunt')
            state = _state(d)

            with mock.patch('engine_terragrunt.cmd.run_with_output') as run:
                result = engine.outputs(state, {})

            self.assertIsNone(result)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
