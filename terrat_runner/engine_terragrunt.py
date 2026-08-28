import engine_tf
import logging
import re


CLI_REDESIGN_VERSION = (0, 88, 0)

# Terragrunt's provider cache server downloads each provider once, under a
# lock file shared by every Terragrunt process on the machine, and serves every
# unit from a local registry. That makes concurrent init safe, so the init lock
# can be dropped -- it otherwise serialises each unit's source and module
# fetching too, none of which contends.
#
# It is opt-in. Providers served from the cache server install as
# `(unauthenticated)`: the recorded hashes still go into .terraform.lock.hcl and
# are verified on every later init, so integrity holds, but the signature is not
# checked against the origin registry on first install. That is the operator's
# call, so we act only when they ask for it.
#
# The request has two spellings, and each is read from a different version on.
# Verified by running every release from 0.50.0 through 1.1.4 with each one set
# (terrateamio/action#668): the legacy name is still honoured on 1.1.4, only
# with a deprecation warning. On a version that reads TG_PROVIDER_CACHE its
# value, even a false one, wins over the legacy name.
PROVIDER_CACHE_FLOORS = (
    ('TG_PROVIDER_CACHE', (0, 73, 0)),
    ('TERRAGRUNT_PROVIDER_CACHE', (0, 56, 4)),
)

# Terragrunt parses these with Go's strconv.ParseBool. Anything else, such as
# 'yes' or 'on', makes it exit with "invalid value" before doing anything, so
# treating those as a request would unlock init for a run that then fails.
_TRUE = ('1', 't', 'T', 'true', 'True', 'TRUE')


def _requested(env):
    return any(env.get(name) in _TRUE for (name, _) in PROVIDER_CACHE_FLOORS)


def _cache_server_will_run(env, version):
    # Mirrors Terragrunt's own precedence, so this says whether *this* binary
    # will start the cache server, not whether the operator meant it to.
    for (name, floor) in PROVIDER_CACHE_FLOORS:
        # Present but empty behaves as unset and falls through, as it does in
        # Terragrunt (tested on 0.77.9).
        if version >= floor and env.get(name, '') != '':
            return env[name] in _TRUE

    return False


def _parse_version(version):
    if not version:
        return None

    match = re.search(r'v?(\d+)\.(\d+)\.(\d+)', str(version))
    if not match:
        return None

    return tuple(int(part) for part in match.groups())


def _fmt(version):
    return '.'.join(str(part) for part in version)


class Engine(engine_tf.Engine):
    def __init__(self, name, override_tf_cmd, **options):
        super().__init__(name, override_tf_cmd, **options)
        self.version = options.get('version')
        self.__use_run_for_workspace = None
        # (parsed, configured) once known. None until then; a failed probe is
        # never cached, so a later caller gets another chance after init has
        # had its own go at installing the toolchain.
        self.__resolved_version = None

    def _configured_version(self, state):
        version = self.version or state.workflow.get('engine', {}).get('version')
        if version is None:
            version = state.env.get('TG_DEFAULT_VERSION')

        return version

    def _detect_installed_version(self, state):
        (returncode, stdout, stderr) = self.probe_toolchain(state, self.tf_cmd)

        if returncode != 0:
            return None

        return _parse_version('\n'.join([stdout, stderr]))

    def _resolve_version(self, state):
        if self.__resolved_version is None:
            configured = self._configured_version(state)
            parsed = _parse_version(configured)

            if parsed is None:
                parsed = self._detect_installed_version(state)

                if parsed is None:
                    return (None, configured)

            self.__resolved_version = (parsed, configured)

        return self.__resolved_version

    def _at_least(self, state, minimum):
        (parsed_version, version) = self._resolve_version(state)

        if parsed_version is None:
            # An unparseable version is only assumed new enough when it names a
            # moving target. A wrong guess here costs one failed command.
            return str(version).lower() in ['latest', 'current']

        return parsed_version >= minimum

    def _use_run_for_workspace(self, state):
        if self.__use_run_for_workspace is None:
            self.__use_run_for_workspace = self._at_least(state, CLI_REDESIGN_VERSION)

        return self.__use_run_for_workspace

    def lock_init(self, state):
        env = state.env

        if not _requested(env):
            return True

        # Opted in. Unlocking init hands us the lock's other job, so install
        # every binary init will reach, under the lock, before deciding
        # anything: the tofu or terraform that Terragrunt shells out to, then
        # Terragrunt itself. The second probe also tells us which Terragrunt is
        # really going to run -- a configured version is only a tenv default,
        # and a version file in the repository can quietly pick an older one.
        underlying = env.get('TERRATEAM_TF_CMD')
        if underlying:
            self.probe_toolchain(state, underlying)

        detected = self._detect_installed_version(state)

        if detected is None:
            logging.warning(
                ('INIT : PROVIDER_CACHE : %s : '
                 'requested but the Terragrunt version could not be determined, '
                 'keeping the init lock'),
                state.path)

            return True

        # The binary that will run is the one whose version matters, for the
        # workspace command as well as for this decision.
        self.__resolved_version = (detected, self._configured_version(state))

        if not _cache_server_will_run(env, detected):
            # A wrong guess here is not a failed command, it is concurrent
            # inits racing in a shared plugin cache with nothing protecting
            # them, so nothing short of certainty unlocks.
            logging.warning(
                ('INIT : PROVIDER_CACHE : %s : '
                 'requested but Terragrunt %s will not start the cache server '
                 'with this setting, keeping the init lock'),
                state.path,
                _fmt(detected))

            return True

        return False

    def workspace_cmd(self, state, *args):
        if self._use_run_for_workspace(state):
            return [self.tf_cmd, 'run', '--', 'workspace'] + list(args)
        else:
            return super().workspace_cmd(state, *args)


def make(**options):
    options.setdefault('override_tf_cmd', 'terragrunt')
    options['name'] = 'tf'
    return Engine(**options)
