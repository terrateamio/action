import json
import logging
import os
import re
import subprocess
import tarfile

import cmd
import engine_tf


CLI_REDESIGN_VERSION = (0, 88, 0)


def _parse_version(version):
    if not version:
        return None

    match = re.search(r'v?(\d+)\.(\d+)\.(\d+)', str(version))
    if not match:
        return None

    return tuple(int(part) for part in match.groups())


def _tar_dir(src_dir, dest_file):
    with tarfile.open(dest_file, 'w') as tar:
        tar.add(src_dir, arcname='.')


def _untar_dir(src_file, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    with tarfile.open(src_file, 'r') as tar:
        tar.extractall(dest_dir)


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

        # -detailed-exitcode must be forwarded via `--`, or `stack run` never
        # returns 2 for "has changes" -- confirmed against a real Terragrunt
        # 1.1.4 install; without `--` the process always exits 0/1.
        if proc.returncode in [0, 2]:
            _tar_dir(out_dir, state.env['TERRATEAM_PLAN_FILE'])

        return (proc.returncode in [0, 2], proc.returncode == 2, stdout, stderr)

    def apply(self, state, config):
        if not self._is_stack(state):
            return super().apply(state, config)

        logging.info(
            'APPLY : %s : engine=%s : stack=true',
            state.path,
            state.workflow['engine']['name'])

        out_dir = self._stack_units_dir(state)
        _untar_dir(state.env['TERRATEAM_PLAN_FILE'], out_dir)

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': [
                    self.tf_cmd, 'stack', 'run', 'apply',
                    '--out-dir', out_dir,
                    '--non-interactive',
                    '--',
                ] + config.get('extra_args', [])
            })

        # Terraform itself refuses to apply a saved plan if any input variable
        # no longer matches what was recorded at plan time ("Can't change
        # variable when applying a saved plan") -- confirmed by deliberately
        # changing a unit's input between plan and apply in local testing.
        # That guarantee is enforced by Terraform, not by this engine.
        return (proc.returncode == 0, stdout, stderr)

    def _stack_show(self, state, extra_args):
        out_dir = self._stack_units_dir(state)
        if not os.path.isdir(out_dir):
            _untar_dir(state.env['TERRATEAM_PLAN_FILE'], out_dir)

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


def make(**options):
    options.setdefault('override_tf_cmd', 'terragrunt')
    options['name'] = 'tf'
    return Engine(**options)
