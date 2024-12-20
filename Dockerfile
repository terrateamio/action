FROM ghcr.io/terrateamio/action-base:369
COPY terrat_runner /terrat_runner
ENTRYPOINT ["/usr/local/bin/entrypoint"]
