import hashlib
import io
import json
import logging
import os
import re
import subprocess
import tarfile

import cmd
import engine_tf


CLI_REDESIGN_VERSION = (0, 88, 0)
STACK_ARTIFACT_MANIFEST = '.terrateam-stack-artifact.json'
STACK_ARTIFACT_VERSION = 1


def _parse_version(version):
    if not version:
        return None

    match = re.search(r'v?(\d+)\.(\d+)\.(\d+)', str(version))
    if not match:
        return None

    return tuple(int(part) for part in match.groups())


class Engine(engine_tf.Engine):
    def __init__(self, name, override_tf_cmd, **options):
        super().__init__(name, override_tf_cmd, **options)
        self.version = options.get('version')
        self.__use_run_for_workspace = None
        self.__is_stack = None

    def _detect_installed_version(self, state):
        try:
            proc = subprocess.run(
                [self.tf_cmd, '--version'],
                cwd=state.working_dir,
                env=state.env,
                capture_output=True,
                text=True)
        except OSError:
            return None

        return _parse_version('\n'.join([proc.stdout, proc.stderr]))

    def _use_run_for_workspace(self, state):
        if self.__use_run_for_workspace is not None:
            return self.__use_run_for_workspace

        version = self.version or state.workflow.get('engine', {}).get('version')
        if version is None:
            version = state.env.get('TG_DEFAULT_VERSION')

        parsed_version = _parse_version(version)
        if parsed_version is None:
            parsed_version = self._detect_installed_version(state)

        if parsed_version is None:
            self.__use_run_for_workspace = str(version).lower() in ['latest', 'current']
        else:
            self.__use_run_for_workspace = parsed_version >= CLI_REDESIGN_VERSION

        return self.__use_run_for_workspace

    def workspace_cmd(self, state, *args):
        if self._use_run_for_workspace(state):
            return [self.tf_cmd, 'run', '--', 'workspace'] + list(args)
        else:
            return super().workspace_cmd(state, *args)

    def _is_stack(self, state):
        # Terragrunt Stacks (terragrunt.stack.hcl) have no terragrunt.hcl of
        # their own, so plain `terragrunt plan`/`apply` cannot run there at
        # all -- they need `terragrunt stack run <verb>` instead. Detecting
        # this here (at command-construction time, from the filesystem)
        # rather than via repo config works because by the time plan/apply
        # run, the directory is always already checked out on disk.
        if self.__is_stack is None:
            self.__is_stack = os.path.exists(
                os.path.join(state.working_dir, 'terragrunt.stack.hcl'))
        return self.__is_stack

    def _stack_units_dir(self, state):
        # A stack's `stack run` produces one plan file per unit, not the
        # single file Terrateam's plan-storage plumbing (TERRATEAM_PLAN_FILE)
        # assumes. Rather than teach the storage layer about directories, we
        # keep the directory of per-unit plan files local to this job (under
        # the checkout, alongside Terragrunt's own .terragrunt-stack/
        # .terragrunt-cache/) and tar/untar it into TERRATEAM_PLAN_FILE at the
        # plan/apply boundary, so every other engine and the storage layer
        # (terrateam/cmd/s3 plan storage) need no changes at all.
        return os.path.join(state.working_dir, '.terrateam-stack-plans')

    def _stack_config_path(self, state):
        return os.path.join(state.working_dir, 'terragrunt.stack.hcl')

    def _stack_artifact_manifest(self, state, stack_config):
        return {
            'format_version': STACK_ARTIFACT_VERSION,
            'engine': 'terragrunt-stack',
            'stack_root': state.path,
            'stack_config_sha256': hashlib.sha256(stack_config).hexdigest(),
        }

    def _tar_stack_artifact(self, state):
        # A Stack plan is a collection of Terraform plans plus the root Stack
        # configuration that evaluates `values` during `stack run apply`.
        # Runtime directories (.terraform and .terragrunt-cache) are neither
        # portable nor needed: Terragrunt recreates them in the apply worker.
        with open(self._stack_config_path(state), 'rb') as f:
            stack_config = f.read()

        manifest = json.dumps(self._stack_artifact_manifest(state, stack_config)).encode('utf-8')
        with tarfile.open(state.env['TERRATEAM_PLAN_FILE'], 'w') as tar:
            tar.add(self._stack_units_dir(state), arcname='.terrateam-stack-plans')
            info = tarfile.TarInfo(STACK_ARTIFACT_MANIFEST)
            info.size = len(manifest)
            tar.addfile(info, io.BytesIO(manifest))
            info = tarfile.TarInfo('stack/terragrunt.stack.hcl')
            info.size = len(stack_config)
            tar.addfile(info, io.BytesIO(stack_config))

    def _load_stack_artifact_manifest(self, state):
        try:
            with tarfile.open(state.env['TERRATEAM_PLAN_FILE'], 'r') as tar:
                member = tar.getmember(STACK_ARTIFACT_MANIFEST)
                content = tar.extractfile(member).read()
                manifest = json.loads(content)
        except (KeyError, OSError, tarfile.TarError, json.JSONDecodeError, AttributeError):
            return None

        if (not isinstance(manifest, dict)
                or manifest.get('format_version') != STACK_ARTIFACT_VERSION
                or manifest.get('engine') != 'terragrunt-stack'
                or not isinstance(manifest.get('stack_root'), str)
                or not isinstance(manifest.get('stack_config_sha256'), str)):
            return None

        return manifest

    def _restore_stack_artifact(self, state, manifest):
        with tarfile.open(state.env['TERRATEAM_PLAN_FILE'], 'r') as tar:
            plan_members = [member for member in tar.getmembers()
                            if member.name == '.terrateam-stack-plans'
                            or member.name.startswith('.terrateam-stack-plans/')]
            workspace = os.path.abspath(state.working_dir)
            for member in plan_members:
                target = os.path.abspath(os.path.join(workspace, member.name))
                if os.path.commonpath([workspace, target]) != workspace:
                    raise ValueError('Stack plan artifact contains an unsafe path')
            # filter='data' additionally rejects symlink/hardlink members whose
            # link target escapes the extraction directory (CVE-2007-4559-class),
            # and device/fifo members -- the commonpath check above only covers
            # a member's own name, not what a symlink member points at.
            tar.extractall(state.working_dir, members=plan_members, filter='data')
            stack_config = tar.extractfile('stack/terragrunt.stack.hcl').read()

        if hashlib.sha256(stack_config).hexdigest() != manifest['stack_config_sha256']:
            raise ValueError('Stack artifact configuration checksum does not match its manifest')

        config_path = self._stack_config_path(state)
        if os.path.exists(config_path):
            with open(config_path, 'rb') as f:
                current_config = f.read()
            if current_config != stack_config:
                raise ValueError('Stack root configuration changed after plan; run a new plan before apply')
        else:
            with open(config_path, 'wb') as f:
                f.write(stack_config)

    def _stack_plan_has_changes(self, state):
        # Some Terragrunt versions return zero from `stack run plan` even
        # when -detailed-exitcode is forwarded and the generated unit plans
        # contain changes. Inspect those saved plans as a safe fallback: a
        # false negative here would make Terrateam silently skip apply.
        (ok, results) = self._stack_show(state, ['-json'])
        if not ok:
            stderr = '\n'.join(
                err for (_unit, unit_ok, _out, err) in results if not unit_ok)
            return (False, False, stderr or 'Unable to inspect Terragrunt stack plans')

        try:
            for (_unit, _unit_ok, stdout, _stderr) in results:
                plan = json.loads(stdout)
                changes = plan.get('resource_changes', []) + list(plan.get('output_changes', {}).values())
                for change in changes:
                    if change.get('change', {}).get('actions', []) != ['no-op']:
                        return (True, True, '')
        except (AttributeError, json.JSONDecodeError) as exn:
            return (False, False, 'Unable to parse Terragrunt stack plan JSON: {}'.format(exn))

        return (True, False, '')

    def init(self, state, config, create_and_select_workspace=None):
        if not self._is_stack(state):
            return super().init(state, config, create_and_select_workspace)

        # engine_tf.Engine.init() runs plain `terragrunt init` (plus workspace
        # select/new) with cwd=state.working_dir, i.e. the Stack root -- same
        # "does not contain a terragrunt.hcl file" failure as outputs()/show,
        # for the same reason. `terragrunt stack run plan`/`apply` initialize
        # each generated unit themselves, so this step is redundant for a
        # Stack, not just unsafe to run as-is. This only matters for repo
        # configs that don't override the default `plan`/`apply` workflows --
        # those default to `[{type: init}, {type: plan/apply}]`.
        logging.info(
            'INIT : %s : engine=%s : stack=true : skipped (stack run plan/apply initialize each unit themselves)',
            state.path,
            state.workflow['engine']['name'])
        return (True, '', '')

    def plan(self, state, config):
        if not self._is_stack(state):
            return super().plan(state, config)

        logging.info(
            'PLAN : %s : engine=%s : stack=true',
            state.path,
            state.workflow['engine']['name'])

        out_dir = self._stack_units_dir(state)

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [
                    self.tf_cmd, 'stack', 'run', 'plan',
                    '--out-dir', out_dir,
                    '--non-interactive',
                    '--',
                    '-detailed-exitcode',
                ] + config.get('extra_args', [])
            })

        # -detailed-exitcode must be forwarded via `--`. Some Terragrunt
        # versions nevertheless return zero for stack plans with changes, so
        # use the generated unit plan JSON as a fallback before recording
        # has_changes=false.
        if proc.returncode not in [0, 2]:
            return (False, False, stdout, stderr)

        has_changes = proc.returncode == 2
        if not has_changes:
            (ok, has_changes, inspect_stderr) = self._stack_plan_has_changes(state)
            if not ok:
                return (False, False, stdout, '\n'.join(v for v in [stderr, inspect_stderr] if v))

        self._tar_stack_artifact(state)
        return (True, has_changes, stdout, stderr)

    def apply(self, state, config):
        manifest = self._load_stack_artifact_manifest(state)
        if manifest is None:
            if self._is_stack(state):
                return (False, '', 'Terragrunt Stack plan artifact is missing or invalid; run a new plan before apply')
            return super().apply(state, config)

        if manifest['stack_root'] != state.path:
            return (False, '', 'Stack plan belongs to a different directory; run a new plan before apply')

        logging.info(
            'APPLY : %s : engine=%s : stack=true',
            state.path,
            state.workflow['engine']['name'])

        try:
            self._restore_stack_artifact(state, manifest)
        except (OSError, tarfile.TarError, ValueError) as exn:
            return (False, '', 'Unable to restore Terragrunt Stack plan artifact: {}'.format(exn))
        out_dir = self._stack_units_dir(state)

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [
                    self.tf_cmd, 'stack', 'run', 'apply',
                    '--out-dir', out_dir,
                    '--non-interactive',
                ] + config.get('extra_args', [])
            })

        # `stack run` regenerates the units with the root Stack's values and
        # preserves their dependency order. Terraform refuses a saved plan if
        # its recorded inputs or state are stale.
        return (proc.returncode == 0, stdout, stderr)

    def apply_without_plan(self, state, config):
        if not self._is_stack(state):
            return super().apply_without_plan(state, config)

        logging.info(
            'APPLY_WITHOUT_PLAN : %s : engine=%s : stack=true',
            state.path,
            state.workflow['engine']['name'])

        # There is no saved plan artifact to restore here (that's the whole
        # point of apply_without_plan) -- `stack run apply` generates the
        # units and applies live in one step, same as plain `terraform apply
        # -auto-approve` does for a non-stack directory.
        out_dir = self._stack_units_dir(state)

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [
                    self.tf_cmd, 'stack', 'run', 'apply',
                    '--out-dir', out_dir,
                    '--non-interactive',
                ] + config.get('extra_args', [])
            })

        return (proc.returncode == 0, stdout, stderr)

    def _stack_show(self, state, extra_args):
        out_dir = self._stack_units_dir(state)
        if not os.path.isdir(out_dir):
            manifest = self._load_stack_artifact_manifest(state)
            if manifest is None:
                return (False, [])
            self._restore_stack_artifact(state, manifest)

        results = []
        overall_ok = True
        for dirpath, _dirnames, filenames in os.walk(out_dir):
            if 'tfplan.tfplan' not in filenames:
                continue

            unit = os.path.relpath(dirpath, out_dir)
            plan_path = os.path.join(dirpath, 'tfplan.tfplan')

            # --out-dir only copies the plan file, not the unit's
            # terragrunt.hcl -- that only exists where `terragrunt stack
            # generate` originally wrote it, under working_dir itself, not
            # under out_dir. Plain `terragrunt show` run with cwd=working_dir
            # (cmd.run_with_output always uses state.working_dir, it has no
            # per-call cwd override) fails with "does not contain a
            # terragrunt.hcl file" because that's the stack root, which only
            # has terragrunt.stack.hcl. --working-dir points terragrunt at
            # the real generated unit directory instead, without needing to
            # touch cwd at all. Confirmed against a real Terragrunt 1.1.4
            # install; the flag must come before the `show` subcommand.
            unit_config_dir = os.path.join(state.working_dir, unit)

            (proc, stdout, stderr) = cmd.run_with_output(
                state,
                {'cmd': [self.tf_cmd, '--working-dir', unit_config_dir, 'show'] + extra_args + [plan_path]})

            overall_ok = overall_ok and proc.returncode == 0
            results.append((unit, proc.returncode == 0, stdout, stderr))

        return (overall_ok, results)

    def diff(self, state, config):
        if not self._is_stack(state):
            return super().diff(state, config)

        logging.info(
            'DIFF : %s : engine=%s : stack=true',
            state.path,
            state.workflow['engine']['name'])

        (ok, results) = self._stack_show(state, [])

        stdout = '\n\n'.join(
            '# unit: {}\n{}'.format(unit, engine_tf.format_diff(out))
            for (unit, unit_ok, out, _err) in results if unit_ok)
        stderr = '\n'.join(err for (_unit, unit_ok, _out, err) in results if not unit_ok)

        return (ok, stdout, stderr)

    def diff_json(self, state, config):
        if not self._is_stack(state):
            return super().diff_json(state, config)

        logging.info(
            'DIFF_JSON : %s : engine=%s : stack=true',
            state.path,
            state.workflow['engine']['name'])

        (ok, results) = self._stack_show(state, ['-json'])

        if not ok:
            stdout = '\n'.join(out for (_unit, _unit_ok, out, _err) in results)
            stderr = '\n'.join(err for (_unit, unit_ok, _out, err) in results if not unit_ok)
            return (False, stdout, stderr)

        try:
            return (True, {unit: json.loads(out) for (unit, _ok, out, _err) in results})
        except json.JSONDecodeError as exn:
            stdout = '\n'.join(out for (_unit, _unit_ok, out, _err) in results)
            return (False, stdout, str(exn))

    def outputs(self, state, config):
        if not self._is_stack(state):
            return super().outputs(state, config)

        # engine_tf.Engine.outputs() runs plain `terragrunt output -json` with
        # cwd=state.working_dir, i.e. the Stack root -- which only ever has
        # terragrunt.stack.hcl, never terragrunt.hcl, so it always fails with
        # "does not contain a terragrunt.hcl file". A Stack has no single
        # root-level output set (each unit has its own); skipping collection
        # entirely -- the same `None` the base class itself returns when
        # outputs collection is disabled via config -- is already handled
        # correctly by workflow_step_apply.py. Aggregating per-unit outputs is
        # a separate, bigger feature (namespacing, rendering) left for later.
        logging.info(
            'OUTPUTS : %s : engine=%s : stack=true : skipped (no single root-level output set for a stack)',
            state.path,
            state.workflow['engine']['name'])
        return None


def make(**options):
    options.setdefault('override_tf_cmd', 'terragrunt')
    options['name'] = 'tf'
    return Engine(**options)
