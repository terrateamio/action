FROM ghcr.io/terrateamio/action-base:latest

COPY entrypoint.sh /entrypoint.sh
COPY terrat_runner /terrat_runner

RUN mkdir /usr/local/share/keys
COPY keys/hashicorp-pgp-key.txt /usr/local/share/keys

ENV TFENV_HASHICORP_PGP_KEY=/usr/local/share/keys/hashicorp-pgp-key.txt

ENTRYPOINT ["/entrypoint.sh"]
