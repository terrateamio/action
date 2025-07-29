#!/usr/bin/env bash

set -e

# Detect architecture and map to Node.js naming convention
ARCH=$(uname -m | sed 's/x86_64/x64/g' | sed 's/aarch64/arm64/g')

curl -fsSL -o /tmp/node-v18.14.0.tar.gz "https://nodejs.org/dist/v18.14.0/node-v18.14.0-linux-${ARCH}.tar.gz"
tar -C /usr/local/ -xzf /tmp/node-v18.14.0.tar.gz
ln -s /usr/local/node-v18.14.0-linux-${ARCH} /usr/local/node
ln -s /usr/local/node/bin/* /usr/local/bin/
rm -f /tmp/node-v18.14.0.tar.gz

# Retry a few times, incase the network is fickle
npm install cdktf-cli@latest \
    || npm install cdktf-cli@latest \
    || npm install cdktf-cli@latest \
    || npm install cdktf-cli@latest
