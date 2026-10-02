ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1790948636@sha256:137b1071b778032f572ad03e30f19f9a13bba39ec0e50456f9d7cbf174237aa5
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
