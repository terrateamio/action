#!/usr/bin/env bash

flock /tmp/gcloud.install apt update
flock /tmp/gcloud.install apt -y install apt-transport-https ca-certificates gnupg curl
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | flock /tmp/gcloud.install gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | flock /tmp/gcloud.install tee /etc/apt/sources.list.d/google-cloud-sdk.list
flock /tmp/gcloud.install apt update && flock /tmp/gcloud.install apt-get install -y google-cloud-cli
