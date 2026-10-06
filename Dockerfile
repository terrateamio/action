ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1791316306@sha256:988bb86a5a2f112fc727161d788f86ce8c153624ae9f48ae15e6daf7b11d1387
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
