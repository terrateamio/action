FROM ghcr.io/terrateamio/action-base:latest

RUN git clone https://github.com/asdf-vm/asdf.git /usr/local/share/asdf --branch v0.14.1

COPY entrypoint.sh /entrypoint.sh
COPY terrat_runner /terrat_runner

ENTRYPOINT ["/entrypoint.sh"]
