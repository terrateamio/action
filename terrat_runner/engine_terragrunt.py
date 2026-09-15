import engine_tf
import re
import subprocess


CLI_REDESIGN_VERSION = (0, 88, 0)


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


def make(**options):
    options.setdefault('override_tf_cmd', 'terragrunt')
    options['name'] = 'tf'
    return Engine(**options)
