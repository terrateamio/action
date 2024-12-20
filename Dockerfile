FROM ghcr.io/terrateamio/action-base:latest
COPY terrat_runner /terrat_runner
ENTRYPOINT ["/usr/local/bin/entrypoint"]
