#!/usr/bin/env bash

if command -v apk > /dev/null; then
    flock /tmp/azure.install sh -c \
        'python3 -m venv /opt/azure-cli \
             && /opt/azure-cli/bin/pip install --no-cache-dir azure-cli \
             && ln -sf /opt/azure-cli/bin/az /usr/bin/az'
    exit 0
fi

flock /tmp/azure.install curl -sL https://aka.ms/InstallAzureCLIDeb | bash
