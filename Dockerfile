ARG BASE_IMAGE=ghcr.io/terrateamio/action-base:1790673205@sha256:877b12c216cef40d15713548618ed5c0099a064c894a7ce9ba529897bc24aefa
FROM ${BASE_IMAGE}

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

COPY bin/ /usr/local/bin

ENTRYPOINT ["/entrypoint.sh"]
