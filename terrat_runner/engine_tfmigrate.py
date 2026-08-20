# tfmigrate (https://github.com/minamijoyo/tfmigrate) engine.
#
# tfmigrate performs Terraform/OpenTofu *state* migrations (state mv/rm/import/...)
# as a reviewable plan/apply step. `tfmigrate plan` applies the migration to a
# temporary copy of the real state and verifies the result is a clean, no-diff
# plan (it touches nothing remote); `tfmigrate apply` performs the real state
# surgery and pushes the new state to the remote backend.
#
# In Terrateam, migrations live in their own dirspace (conventionally
# `.terrateam/tfmigrate/`) and target a real terraform dir via a repo-relative
# `dir` in each migration file. The engine runs tfmigrate from the repository
# root (TERRATEAM_ROOT) because tfmigrate resolves both `migration_dir` and a
# migration's `dir` relative to the current working directory; running from the
# root lets users write clean repo-relative paths like `dir = "prod"`.
#
# History (which migrations have already been applied) is tracked with
# tfmigrate's "history mode" using local-file storage that the engine syncs to
# the Terrateam KV store via ttm. Users do NOT configure a `history {}` block or
# any S3/GCS backend: the engine writes an effective config that injects a
# managed local history file, downloads the history from the KV store before each
# operation, and uploads it again after a successful apply. The user's
# `.tfmigrate.hcl` only needs to exist (it is the opt-in marker); the engine owns
# the effective config.
#
# tfmigrate uses the process exit code as the signal: plan/apply exit zero when
# the migration reconciles to a clean, no-diff plan and non-zero otherwise. A
# bare `tfmigrate plan`/`apply` (history mode, no file argument) operates on all
# *unapplied* migrations; when there are none it still exits zero and logs
# "no unapplied migrations" (tfmigrate's default log level is INFO), which the
# engine uses to report has_changes=False instead of a spurious pending apply.

import hashlib
import logging
import os
import urllib.parse

import cmd
import engine
import ttm

CONFIG_FILE = '.tfmigrate.hcl'

# Logged by a bare history-mode `tfmigrate plan` when nothing is left to migrate.
_NO_PENDING_MIGRATIONS = 'no unapplied migrations'


def _root(state):
    # tfmigrate is run from the repository root so migration `dir` values resolve
    # as clean repo-relative paths.
    return state.env.get('TERRATEAM_ROOT', state.working_dir)


def _migration_dir(state):
    # tfmigrate resolves migration_dir relative to the cwd (the repo root), so it
    # is the migration dirspace's path relative to the root.
    return state.path or os.path.relpath(state.working_dir, _root(state))


def _history_key(state):
    # The KV namespace is `{vcs}:{installation_id}`, which is shared across every
    # repository in an installation, so the key must carry the repository and the
    # migration dirspace to stay collision-free. Components are URL-encoded so the
    # whole key remains a single safe token.
    repo = state.env.get('GITHUB_REPOSITORY') or state.env.get('CI_PROJECT_PATH') or ''
    if not repo:
        logging.warning(
            'TFMIGRATE : no repository identifier in env (GITHUB_REPOSITORY / '
            'CI_PROJECT_PATH); the tfmigrate history key may not be unique per repo')
    return '.'.join([
        'tfmigrate',
        'history',
        urllib.parse.quote(repo, safe=''),
        urllib.parse.quote(_migration_dir(state), safe=''),
    ])


def _managed_paths(state):
    # Per-dirspace files under the run's tmpdir so parallel dirspaces never clash
    # and nothing is written into the checked-out repository.
    base = state.tmpdir or state.working_dir
    tag = hashlib.sha256((state.path or state.working_dir).encode('utf-8')).hexdigest()[:12]
    config_path = os.path.join(base, 'tfmigrate-config-' + tag + '.hcl')
    history_path = os.path.join(base, 'tfmigrate-history-' + tag + '.json')
    return (config_path, history_path)


def _hcl_string(s):
    # Render a value as a double-quoted HCL string.
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _write_effective_config(state, config_path, history_path):
    # The effective config sets the (root-relative) migration_dir and injects
    # managed local history storage. tfmigrate reads it via TFMIGRATE_CONFIG, so
    # the user's own `.tfmigrate.hcl` is never parsed -- it is only the opt-in
    # marker that init checks for.
    lines = [
        'tfmigrate {',
        '  migration_dir = ' + _hcl_string(_migration_dir(state)),
        '  history {',
        '    storage "local" {',
        '      path = ' + _hcl_string(history_path),
        '    }',
        '  }',
        '}',
        '',
    ]
    with open(config_path, 'w') as f:
        f.write('\n'.join(lines))


def _download_history(state, history_path):
    # ttm writes an empty file for a missing key (and exits zero); tfmigrate reads
    # both a missing and an empty history file as "no history", so first runs need
    # no special handling.
    ttm.kv_download(
        state,
        state.work_manifest['api_base_url'],
        state.work_manifest['installation_id'],
        _history_key(state),
        history_path)


def _prepare(state):
    """Write the effective config and pull the latest history from the KV store."""
    (config_path, history_path) = _managed_paths(state)
    _write_effective_config(state, config_path, history_path)
    _download_history(state, history_path)
    return (config_path, history_path)


def _run(state, args, config_path):
    # Run tfmigrate from the repository root with the managed config.
    # TFMIGRATE_EXEC_PATH (the resolved tofu/terraform binary) is set globally by
    # set_engine_env. The workflow's extra_args are intentionally not forwarded:
    # tfmigrate's flags differ from terraform's.
    root_state = state._replace(working_dir=_root(state))
    (proc, stdout, stderr) = cmd.run_with_output(
        root_state,
        {
            'cmd': ['tfmigrate'] + args,
            'env': {'TFMIGRATE_CONFIG': config_path},
        })
    return (proc.returncode == 0, stdout, stderr)


def init(state, config):
    """Preflight: verify the dirspace is a tfmigrate config dir and the KV store is reachable."""
    logging.info('INIT : %s : engine=tfmigrate', state.path)
    if not os.path.exists(os.path.join(state.working_dir, CONFIG_FILE)):
        return (
            False,
            '',
            'No %s found in %s. A tfmigrate dirspace must contain a %s config file.'
            % (CONFIG_FILE, state.working_dir, CONFIG_FILE))
    try:
        _prepare(state)
    except Exception as exn:
        logging.exception('TFMIGRATE : INIT : failed to prepare')
        return (False, '', 'Failed to initialize tfmigrate: {}'.format(exn))
    return (True, 'tfmigrate ready for migration dir %s' % _migration_dir(state), '')


def plan(state, config):
    logging.info('PLAN : %s : engine=tfmigrate', state.path)
    try:
        (config_path, _history_path) = _prepare(state)
    except Exception as exn:
        logging.exception('TFMIGRATE : PLAN : failed to prepare')
        return (False, False, '', 'Failed to prepare tfmigrate: {}'.format(exn))

    (success, stdout, stderr) = _run(state, ['plan'], config_path)

    # A successful bare history-mode plan with nothing left to migrate logs
    # "no unapplied migrations" and is a no-op, so only report a pending apply
    # when there is actually a migration to apply.
    has_changes = success and _NO_PENDING_MIGRATIONS not in (stdout + stderr)
    return (success, has_changes, stdout, stderr)


def diff(state, config):
    # tfmigrate produces no terraform plan file, so there is nothing to `show`.
    # The human-readable migration plan is surfaced via the plan step's stdout.
    return None


def diff_json(state, config):
    return None


def apply(state, config):
    logging.info('APPLY : %s : engine=tfmigrate', state.path)
    try:
        (config_path, history_path) = _prepare(state)
    except Exception as exn:
        logging.exception('TFMIGRATE : APPLY : failed to prepare')
        return (False, '', 'Failed to prepare tfmigrate: {}'.format(exn))

    (success, stdout, stderr) = _run(state, ['apply'], config_path)

    # Persist the updated history only on success, and only if tfmigrate actually
    # wrote it (a no-op apply with nothing unapplied leaves no history file).
    if success and os.path.exists(history_path):
        try:
            key = _history_key(state)
            ttm.kv_upload(
                state,
                state.work_manifest['api_base_url'],
                state.work_manifest['installation_id'],
                key,
                history_path)
            ttm.kv_commit(
                state,
                state.work_manifest['api_base_url'],
                state.work_manifest['installation_id'],
                [key])
        except Exception as exn:
            logging.exception('TFMIGRATE : APPLY : failed to persist history')
            return (
                False,
                stdout,
                (stderr + '\n' if stderr else '')
                + 'Migration applied but failed to persist tfmigrate history to the '
                + 'Terrateam KV store: {}'.format(exn))

    return (success, stdout, stderr)


def unsafe_apply(state, config):
    logging.info('UNSAFE_APPLY : %s : engine=tfmigrate', state.path)
    return apply(state, config)


def outputs(state, config):
    return None


def make(**engine_config):
    return engine.Engine(
        name='tfmigrate',
        init=init,
        apply=apply,
        plan=plan,
        diff=diff,
        diff_json=diff_json,
        unsafe_apply=unsafe_apply,
        outputs=outputs)
