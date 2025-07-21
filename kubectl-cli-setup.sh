#!/usr/bin/env bash

set -e
set -u

KUBECTL_VERSION="$1"

# Detect architecture
ARCH=$(uname -m | sed 's/x86_64/amd64/g' | sed 's/aarch64/arm64/g')

curl -sSL -o /tmp/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}/kubectl"
install -m 0755 /tmp/kubectl /usr/bin/kubectl
