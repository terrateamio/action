import logging
import os
import workflow
import subprocess

SSH_KEY_NAME_MATCH = "TERRATEAM_SSH_KEY"


def ssh_keys(env):
    return [(key, val) for key, val in env.items() if key.startswith(SSH_KEY_NAME_MATCH)]


def setup(state):
    logging.info('TERRATEAM_SSH_KEY : SETUP')
    env = state.env

    # Create the ssh directory
    ssh_dir_path = "/root/.ssh/"
    if not os.path.exists(ssh_dir_path):
        os.makedirs(ssh_dir_path)

    # Iterate through environment variables that start with SSH_KEY_NAME_MATCH
    for ssh_key_name, ssh_key_value in ssh_keys(env):
        ssh_key_path = os.path.join(ssh_dir_path, ssh_key_name)
        # Write the ssh key to a file
        with open(ssh_key_path, 'w') as f:
            f.write(ssh_key_value)
            f.write('\n')
        os.chmod(ssh_key_path, 0o600)
        # Add the ssh key to the ssh-agent
        subprocess.check_call(['ssh-add', ssh_key_path])

    # Keyscan github.com and append to known_hosts
    subprocess.check_call(['ssh-keyscan-pre-hook', 'github.com'])

    return workflow.make(
        payload={
            'text': 'Writing TERRATEAM_SSH_KEY.* to ~/.ssh/',
            'visible_on': 'error',
        },
        state=state,
        step='tf/terrateam_ssh_key_setup',
        success=True)


def run(state, config):
    try:
        return setup(state)
    except subprocess.CalledProcessError as exn:
        logging.error('TERRATEAM_SSH_KEY : FAIL : %s', exn)
        return workflow.make(
            payload={
                'text': 'TERRATEAM_SSH_KEY : FAIL : {}'.format(exn),
                'visible_on': 'error',
            },
            state=state,
            step='tf/terrateam_ssh_key_setup',
            success=False)
    except Exception as exn:
        logging.error('TERRATEAM_SSH_KEY : FAIL : %s', exn)
        return workflow.make(
            payload={
                'text': 'TERRATEAM_SSH_KEY : FAIL : {}'.format(exn),
                'visible_on': 'error'
            },
            state=state,
            step='tf/terrateam_ssh_key_setup',
            success=False)
