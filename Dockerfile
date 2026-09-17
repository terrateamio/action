ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1788854514@sha256:23ec3f9be514189d2738c66687939c7cd9056cd6bdba071becaf27ecd1cf2803
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
