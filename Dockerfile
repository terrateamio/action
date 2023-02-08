FROM ghcr.io/terrateamio/action-base:latest

COPY ./cdktf-setup.sh /cdktf-setup.sh
COPY entrypoint.sh /entrypoint.sh
COPY terrat_runner /terrat_runner

RUN     curl -fsSL -o /tmp/infracost-linux-amd64.tar.gz "https://github.com/terrateamio/packages/raw/main/infracost/infracost-v0.10.17-linux-amd64.tar.gz" \
        && tar -C /tmp -xzf /tmp/infracost-linux-amd64.tar.gz \
        && mv /tmp/infracost-linux-amd64 /usr/local/bin/infracost \
        && rm -f /tmp/infracost-linux-amd64.tar.gz

ENTRYPOINT ["/entrypoint.sh"]
