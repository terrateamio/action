#!/usr/bin/env bash

set -e

curl -fsSL -o /tmp/node-v18.14.0.tar.gz "https://github.com/terrateamio/packages/raw/main/node/node-v18.14.0-linux-x64.tar.gz"
tar -C /usr/local/ -xzf /tmp/node-v18.14.0.tar.gz
ln -s /usr/local/node-v18.14.0-linux-x64 /usr/local/node
ln -s /usr/local/node/bin/* /usr/local/bin/
rm -f /tmp/node-v18.14.0.tar.gz

# Retry a few times, incase the network is fickle
npm install cdktf-cli@latest \
    || npm install cdktf-cli@latest \
    || npm install cdktf-cli@latest \
    || npm install cdktf-cli@latest
