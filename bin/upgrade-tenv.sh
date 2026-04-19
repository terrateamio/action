#! /usr/bin/env bash
set -e

set -x
export TENV_LATEST_VERSION=v4.10.1
echo "TENV_LATEST_VERSION: ${TENV_LATEST_VERSION}" && \
    ARCH=$(dpkg --print-architecture) && \
    curl -O -L "https://github.com/tofuutils/tenv/releases/download/${TENV_LATEST_VERSION}/tenv_${TENV_LATEST_VERSION}_${ARCH}.deb" && \
    dpkg -i "tenv_${TENV_LATEST_VERSION}_${ARCH}.deb" && \
    tenv terraform install 1.5.7

set +x
