import io
import logging
import re
import string
import subprocess
import sys


class MissingEnvVar(Exception):
    pass


def _strip_ansi(s):
    return re.sub(r'\033\[(\d|;)+?m', '', s)


def _replace_vars(s, env):
    try:
        return string.Template(s).substitute(env)
    except KeyError as exn:
        raise MissingEnvVar(*exn.args)


def _create_env(env, additional_env):
    env = env.copy()
    # Replace any variables in the environment
    env.update({k: _replace_vars(v, env) for k, v in additional_env.items()})
    return env


def run(state, config):
    cmd = config['cmd']
    env = _create_env(state.env, config.get('env', {}))
    # Replace any variables in the cmd
    cmd = [_replace_vars(s, env) for s in cmd]
    logging.debug('CMD : cmd=%r : cwd=%s', cmd, state.working_dir)
    return subprocess.run(cmd, cwd=state.working_dir, env=env)


def run_with_output(state, config):
    cmd = config['cmd']
    env = _create_env(state.env, config.get('env', {}))
    # Replace any variables in the cmd
    cmd = [_replace_vars(s, env) for s in cmd]
    logging.debug('CMD : cmd=%r : cwd=%s', cmd, state.working_dir)
    proc = subprocess.Popen(cmd,
                            cwd=state.working_dir,
                            env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)

    line = proc.stdout.readline()
    output = io.StringIO()
    while line:
        line = line.decode('utf-8')
        output.write(line)
        sys.stdout.write(line)
        sys.stdout.flush()
        line = proc.stdout.readline()

    proc.wait()
    return (proc, _strip_ansi(output.getvalue()))
