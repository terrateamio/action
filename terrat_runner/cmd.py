import io
import logging
import re
import selectors
import string
import subprocess
import sys


class MissingEnvVar(Exception):
    pass


def _strip_ansi(s):
    return re.sub(r'\033\[(\d|;)+?m', '', s)


def replace_vars(s, env):
    try:
        v = string.Template(s).substitute(env)
        if s == v:
            return v
        else:
            return replace_vars(v, env)
    except KeyError as exn:
        raise MissingEnvVar(*exn.args)


def _create_env(env, additional_env):
    env = env.copy()
    # Replace any variables in the environment
    env.update({k: replace_vars(v, env) for k, v in additional_env.items()})
    return env


def run(state, config):
    cmd = config['cmd']
    env = _create_env(state.env, config.get('env', {}))
    if config.get('log_cmd_pre_replace', False):
        logging.debug('CMD : cmd=%r : cwd=%s', cmd, state.working_dir)
    # In some cases we may not want to replace variables (perhaps the caller did
    # this already, or they have specific variables they want to be passed it to
    # the calling program.)
    if config.get('replace_vars', True):
        cmd = [replace_vars(s, env) for s in cmd]
    if not config.get('log_cmd_pre_replace', False):
        logging.debug('CMD : cmd=%r : cwd=%s', cmd, state.working_dir)
    if config.get('log_output', True):
        return subprocess.run(cmd, cwd=state.working_dir, env=env)
    else:
        return subprocess.run(cmd, cwd=state.working_dir, env=env, stdout=subprocess.DEVNULL)


def _handle_line(state, config, name, stream, line):
    stream.write(line)
    if state.runtime.is_command(line):
        sys.stdout.write(line)
    elif config.get('log_output', True):
        sys.stderr.write('cwd={}: {}: {}'.format(state.working_dir, name, line))


def run_with_output(state, config):
    cmd = config['cmd']
    env = _create_env(state.env, config.get('env', {}))
    if config.get('log_cmd_pre_replace', False):
        logging.debug('CMD : cmd=%r : cwd=%s', cmd, state.working_dir)
    # In some cases we may not want to replace variables (perhaps the caller did
    # this already, or they have specific variables they want to be passed it to
    # the calling program.)
    if config.get('replace_vars', True):
        cmd = [replace_vars(s, env) for s in cmd]
    if not config.get('log_cmd_pre_replace', False):
        logging.debug('CMD : cmd=%r : cwd=%s', cmd, state.working_dir)
    proc = subprocess.Popen(cmd,
                            cwd=state.working_dir,
                            env=env,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

    if 'input' in config:
        proc.stdin.write(config['input'].encode('utf-8'))

    proc.stdin.close()

    sel = selectors.DefaultSelector()

    stdout_done = False
    stderr_done = False

    sel.register(proc.stdout, selectors.EVENT_READ, 'stdout')
    sel.register(proc.stderr, selectors.EVENT_READ, 'stderr')

    stdout = io.StringIO()
    stderr = io.StringIO()
    while not (stdout_done and stderr_done):
        events = sel.select()
        for key, _ in events:
            line = key.fileobj.readline().decode('utf-8', errors='backslashreplace')

            if not line:
                sel.unregister(key.fileobj)
                if key.data == 'stdout':
                    stdout_done = True
                elif key.data == 'stderr':
                    stderr_done = True
                else:
                    raise Exception('Unknown data: {}'.format(key.data))

            elif key.data == 'stdout':
                _handle_line(state, config, key.data, stdout, line)
            elif key.data == 'stderr':
                _handle_line(state, config, key.data, stderr, line)
            else:
                raise Exception('Unknown data: {}'.format(key.data))

    sel.close()

    proc.wait()
    return (proc, _strip_ansi(stdout.getvalue()), _strip_ansi(stderr.getvalue()))
