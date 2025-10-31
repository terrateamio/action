FROM ghcr.io/terrateamio/action-base:latest

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

ENV TTM_DEV_IMAGE="ghcr.io/terrateamio/ttm-dev:20251009-208-add-kv-store-15c0eb4-amd64"

ENV SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"

ENTRYPOINT ["/entrypoint.sh"]
