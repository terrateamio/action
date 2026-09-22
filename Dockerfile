ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1790075266@sha256:52b4ea63c3be3955caa1efdba7969dd79ffbe4d1fc0f04a9ea2662a8858d0551
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
