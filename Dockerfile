FROM ghcr.io/terrateamio/action-base:latest

RUN curl -fsSL -o /tmp/infracost-linux-amd64.tar.gz https://github.com/infracost/infracost/releases/download/v0.10.7/infracost-linux-amd64.tar.gz && tar -C /tmp -xzf /tmp/infracost-linux-amd64.tar.gz && mv /tmp/infracost-linux-amd64 /usr/local/bin/infracost

COPY entrypoint.sh /entrypoint.sh
COPY terrat_runner /terrat_runner

ENTRYPOINT ["/entrypoint.sh"]
