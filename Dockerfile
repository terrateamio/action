ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1795467766@sha256:9c736e9a81f93369a34d5c051dbd53b434d38513a21a6c5d26e06c30d1158a1e
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY post_entrypoint_github.sh /post_entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
