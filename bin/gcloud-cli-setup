#!/usr/bin/env bash

flock /tmp/gcloud.install apt update
flock /tmp/gcloud.install apt -y install apt-transport-https ca-certificates gnupg curl
echo "deb https://packages.cloud.google.com/apt cloud-sdk main" | flock /tmp/gcloud.install tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | flock /tmp/gcloud.install apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | flock /tmp/gcloud.install apt-key add -
flock /tmp/gcloud.install apt update && flock /tmp/gcloud.install apt-get install -y google-cloud-cli
