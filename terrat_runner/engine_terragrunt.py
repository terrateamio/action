import engine_tf
import logging
import re
import subprocess


CLI_REDESIGN_VERSION = (0, 88, 0)

# Terragrunt's provider cache server, added in v0.56.4, downloads each provider
# once and serves every unit from a local registry. That makes concurrent init
# safe, so the init lock can be dropped -- it otherwise serialises each unit's
# source and module fetching too, none of which contends.
#
# Opt-in only. Providers served from the cache server install as
# `(unauthenticated)`: the recorded hashes still go into .terraform.lock.hcl and
# are verified on every later init, so integrity holds, but the signature is not
# checked against the origin registry on first install. That is the operator's
# call, so we act only when they ask for it.
PROVIDER_CACHE_VERSION = (0, 56, 4)

# Both spellings are recognised because the TG_ prefix replaced TERRAGRUNT_ in
# the CLI redesign.
PROVIDER_CACHE_ENV_VARS = ('TG_PROVIDER_CACHE', 'TERRAGRUNT_PROVIDER_CACHE')


def _is_enabled(value):
    return value is not None and str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _provider_cache_requested(env):
    return any(_is_enabled(env.get(k)) for k in PROVIDER_CACHE_ENV_VARS)


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
        # None means unresolved. The resolved value is always a 2-tuple, and
        # unlike an object() sentinel this survives being pickled into a
        # multiprocessing worker, which is how every dirspace gets its engine.
        self.__resolved_version = None

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

    def _resolve_version(self, state):
        if self.__resolved_version is None:
            version = self.version or state.workflow.get('engine', {}).get('version')
            if version is None:
                version = state.env.get('TG_DEFAULT_VERSION')

            parsed_version = _parse_version(version)
            if parsed_version is None:
                # Safe to shell out by now: init installs the toolchain under
                # the lock before anything asks for a version.
                parsed_version = self._detect_installed_version(state)

            self.__resolved_version = (parsed_version, version)

        return self.__resolved_version

    def _at_least(self, state, minimum):
        (parsed_version, version) = self._resolve_version(state)

        if parsed_version is None:
            # An unparseable version is only assumed new enough when it names a
            # moving target.
            return str(version).lower() in ['latest', 'current']

        return parsed_version >= minimum

    def _use_run_for_workspace(self, state):
        if self.__use_run_for_workspace is None:
            self.__use_run_for_workspace = self._at_least(state, CLI_REDESIGN_VERSION)

        return self.__use_run_for_workspace

    def lock_init(self, state):
        if not _provider_cache_requested(state.env):
            return True

        if self._at_least(state, PROVIDER_CACHE_VERSION):
            return False

        # Asked for, but this Terragrunt will ignore the flag. Unlocking init
        # here would leave concurrent inits racing in the shared plugin cache
        # with nothing protecting them, so keep the lock and say why.
        logging.warning(
            ('INIT : PROVIDER_CACHE : %s : '
             'requested but Terragrunt %r predates v%s, keeping the init lock'),
            state.path,
            self._resolve_version(state)[1],
            '.'.join(str(p) for p in PROVIDER_CACHE_VERSION))

        return True

    def workspace_cmd(self, state, *args):
        if self._use_run_for_workspace(state):
            return [self.tf_cmd, 'run', '--', 'workspace'] + list(args)
        else:
            return super().workspace_cmd(state, *args)


def make(**options):
    options.setdefault('override_tf_cmd', 'terragrunt')
    options['name'] = 'tf'
    return Engine(**options)
