FROM ghcr.io/terrateamio/action-base:latest

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

ENTRYPOINT ["/entrypoint.sh"]
