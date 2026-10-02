ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1790877481@sha256:47db4486d4f12d812b183fc2c8e029ebf3961446572ac0bb17b7ef66611bd2b6
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
