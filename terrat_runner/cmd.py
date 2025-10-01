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
        return subprocess.run(
            cmd,
            cwd=state.working_dir,
            env=env,
            input=config.get('input'))
    else:
        return subprocess.run(
            cmd,
            cwd=state.working_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            input=config.get('input'))


def _handle_line(state, config, name, stream, line):
    stream.write(line)
    if state.runtime.is_command(line):
        sys.stdout.write(line)
    elif config.get('log_output', True):
        sys.stderr.write('cwd={}: {}: {}'.format(state.working_dir, name, line))


class OutputCtxMgr:
    def __init__(self, stdout_path, stderr_path, tee_append):
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path
        self.mode = 'a' if tee_append else 'w'

    def __enter__(self):
        if self.stdout_path:
            self.stdout_fileobj = open(self.stdout_path, self.mode)
        else:
            self.stdout_fileobj = io.StringIO()

        if self.stderr_path:
            self.stderr_fileobj = open(self.stderr_path, self.mode)
        else:
            self.stderr_fileobj = io.StringIO()

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if self.stdout_path:
            self.stdout_fileobj.close()

        if self.stderr_path:
            self.stderr_fileobj.close()

        return False


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

    tee_base = config.get('tee')
    if tee_base:
        stdout_path = tee_base + '.stdout'
        stderr_path = tee_base + '.stderr'
    else:
        stdout_path = None
        stderr_path = None

    with OutputCtxMgr(stdout_path, stderr_path, config.get('tee_append', False)) as out:
        stdout = out.stdout_fileobj
        stderr = out.stderr_fileobj

        while not (stdout_done and stderr_done):
            events = sel.select()
            for key, _ in events:
                line = key.fileobj.readline().decode('utf-8', errors='backslashreplace')

                if line:
                    line = _strip_ansi(line)

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

        if tee_base:
            return (proc, stdout_path, stderr_path)
        else:
            return (proc, stdout.getvalue(), stderr.getvalue())
