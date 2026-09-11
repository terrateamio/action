import logging
import os
import re
import tempfile

# Terraform and OpenTofu install a provider into every directory they
# initialize, so a run over N dirspaces downloads the same provider N times.
# Pointing them at a shared cache directory makes only the first install hit the
# network, the rest link against the cached copy.
#
# This is opt-in because TF_PLUGIN_CACHE_DIR takes precedence over a
# [plugin_cache_dir] in a CLI configuration file, so enabling it unasked would
# take over a cache directory the repository chose deliberately.  For the same
# reason it declines whenever a cache directory is already configured, by
# either the environment or a CLI configuration file.
ENABLED_ENV_NAME = 'TERRATEAM_PLUGIN_CACHE'
DIR_ENV_NAME = 'TERRATEAM_PLUGIN_CACHE_DIR'
TF_PLUGIN_CACHE_DIR = 'TF_PLUGIN_CACHE_DIR'

# The CLI configuration files, in the order Terraform and OpenTofu look for
# them.  Tofu reads .tofurc first and falls back to .terraformrc.
CLI_CONFIG_FILE_ENV_NAMES = ['TF_CLI_CONFIG_FILE', 'TOFU_CLI_CONFIG_FILE']
CLI_CONFIG_FILE_NAMES = ['.terraformrc', '.tofurc']

# An HCL attribute at the start of a line, so a commented out setting does not
# count.
_PLUGIN_CACHE_DIR = re.compile(r'^\s*plugin_cache_dir\s*=', re.MULTILINE)


def _default_dir():
    return os.path.join(tempfile.gettempdir(), 'terrateam-plugin-cache')


def _cli_config_files(env):
    ret = []

    for name in CLI_CONFIG_FILE_ENV_NAMES:
        if env.get(name):
            ret.append(env[name])

    home = env.get('HOME')
    if home:
        ret.extend([os.path.join(home, name) for name in CLI_CONFIG_FILE_NAMES])

    return ret


def _configures_plugin_cache_dir(fname):
    try:
        with open(fname) as f:
            return _PLUGIN_CACHE_DIR.search(f.read()) is not None
    except OSError:
        # A file we cannot read is a file we cannot make a claim about, and the
        # safe claim is that it configures nothing of ours.
        return False


def _usable_dir(path):
    # A cache directory that exists but cannot be written to fails the whole
    # init, so test it here rather than find out from Terraform.
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exn:
        logging.info('PLUGIN_CACHE : DISABLED : mkdir failed : %s : %s', path, exn)
        return False

    if not os.access(path, os.W_OK | os.X_OK):
        logging.info('PLUGIN_CACHE : DISABLED : not writable : %s', path)
        return False

    return True


def init_env(env):
    """Return the environment additions that turn on the shared plugin cache.

    Returns an empty dict when the cache is off or when turning it on would
    override a cache directory the repository configured itself.
    """
    if env.get(ENABLED_ENV_NAME, '').lower() not in ('1', 'true'):
        return {}

    if env.get(TF_PLUGIN_CACHE_DIR):
        logging.info('PLUGIN_CACHE : DISABLED : %s is already set', TF_PLUGIN_CACHE_DIR)
        return {}

    for fname in _cli_config_files(env):
        if _configures_plugin_cache_dir(fname):
            logging.info('PLUGIN_CACHE : DISABLED : plugin_cache_dir set in %s', fname)
            return {}

    path = env.get(DIR_ENV_NAME) or _default_dir()

    if not _usable_dir(path):
        return {}

    logging.info('PLUGIN_CACHE : ENABLED : %s', path)

    return {TF_PLUGIN_CACHE_DIR: path}
