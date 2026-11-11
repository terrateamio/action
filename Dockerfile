ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1793881459@sha256:f20778d22ccba202a2ebbeb212d01161f1f4efb935d59f4cb48d80ab5142addb
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY post_entrypoint_github.sh /post_entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
