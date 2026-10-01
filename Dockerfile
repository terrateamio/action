ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1790862252@sha256:6e6062b2931c26d75fc942f47ab1de847aaebe3eca456cf85b908b2047d22108
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
