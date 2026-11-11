ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1793881455@sha256:cc9567be656bd86a693c46f5db4aadd3b838b5a06d8492c61d52593fc91f28d5
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY post_entrypoint_github.sh /post_entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
