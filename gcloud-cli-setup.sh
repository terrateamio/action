#!/usr/bin/env bash

apt update
apt -y install apt-transport-https ca-certificates gnupg curl
echo "deb https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
apt update && apt-get install google-cloud-cli
