#!/usr/bin/env bash

set -e
set -u

KUBECTL_VERSION="$1"

curl -sSL -o /tmp/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
install -m 0755 /tmp/kubectl /usr/bin/kubectl
