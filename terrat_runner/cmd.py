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
    if config.get('log_output', True):
        return subprocess.run(cmd, cwd=state.working_dir, env=env)
    else:
        return subprocess.run(cmd, cwd=state.working_dir, env=env, stdout=subprocess.DEVNULL)


def run_with_output(state, config):
    cmd = config['cmd']
    env = _create_env(state.env, config.get('env', {}))
    # Replace any variables in the cmd
    cmd = [_replace_vars(s, env) for s in cmd]
    logging.debug('CMD : cmd=%r : cwd=%s', cmd, state.working_dir)
    proc = subprocess.Popen(cmd,
                            cwd=state.working_dir,
                            env=env,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)

    if 'input' in config:
        proc.stdin.write(config['input'].encode('utf-8'))

    proc.stdin.close()

    line = proc.stdout.readline()
    output = io.StringIO()
    while line:
        line = line.decode('utf-8', errors='backslashreplace')
        output.write(line)
        if config.get('log_output', True):
            sys.stderr.write('cwd={} : {}'.format(state.working_dir, line))
            sys.stderr.flush()
        line = proc.stdout.readline()

    proc.wait()
    return (proc, _strip_ansi(output.getvalue()))
