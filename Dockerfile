FROM ghcr.io/terrateamio/action-base:latest

COPY entrypoint.sh /entrypoint.sh
COPY terrat_runner /terrat_runner
COPY ./bin/terraform /usr/local/bin/terraform

ENTRYPOINT ["/entrypoint.sh"]
