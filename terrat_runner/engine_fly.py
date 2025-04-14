import difflib
import logging
import toml
import yaml

import cmd


def _update_state(state, config_file):
    env = state.env.copy()
    env['FLY_TOML_PATH'] = config_file
    return state._replace(env=env)


def _normalize_mounts(config):
    mounts = config.get("mounts")
    if isinstance(mounts, dict):
        config["mounts"] = [mounts]


class Engine:
    def __init__(self, name, config_file, app_name='${TERRATEAM_WORKSPACE}'):
        self.name = name
        self.config_file = config_file
        self.app_name = app_name

    def init(self, state, config):
        logging.info(
            'INIT : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': ['flyctl', 'apps', 'create', '--name', self.app_name]
            })

        return (proc.returncode==0, stdout, stderr)

    def apply(self, state, config):
        logging.info(
            'APPLY : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        state = _update_state(state, self.config_file)
        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': ['flyctl', 'deploy', '--app', self.app_name
                        ] + config.get('extra_args', [])
            })

    def diff(self, state, config):
        with open(state.env['TERRATEAM_PLAN_FILE']) as f:
            return (True, f.read(), '')

    def plan(self, state, config):
        logging.info(
            'PLAN : %s : engine=%s',
            state.path,
            state.workflow['engine']['name'])

        state = _update_state(state, self.config_file)
        (proc, stdout, stderr) = cmd.run_with_output(
            state,
            {
                'cmd': ['flyctl', 'config', 'show', '--app', self.app_name
                        ] + config.get('extra_args', [])
            })

        if proc.returncode == 0:
            try:
                live_config = yaml.safe_load(stdout)
                desired_config = toml.load(self.config_File)
                _normalize_mounts(desired_config)

                live_yaml = yaml.dump(
                    live_config,
                    sort_keys=True,
                    indent=2)

                desired_yaml = yaml.dump(
                    desired_config,
                    sort_keys=True,
                    indent=2)

                diff = ''.join(difflib.unified_diff(
                    live_yaml.splitlines(),
                    desired_yaml.splitlines(),
                    fromfile='live (fly)',
                    tofile=self.config_file))

                with open(state.env['TERRATEAM_PLAN_FILE'], 'w') as f:
                    f.write(diff)

                return (True, live_yaml != desired_yaml, diff, '')
            except Exception as exn:
                return (False, False, '', str(exn))
        else:
            return (False, False, stdout, stderr)

    def unsafe_apply(self, state, config):
        return self.apply(state, config)

    def outputs(self, state, config):
        return None


def make(**kwargs):
    return Engine(name='fly', **kwargs)
