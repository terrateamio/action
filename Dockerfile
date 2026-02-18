ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1771446270
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

ENTRYPOINT ["/entrypoint.sh"]
