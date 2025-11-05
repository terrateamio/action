FROM ghcr.io/terrateamio/action-base:latest

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin

ENV TTM_DEV_IMAGE="ghcr.io/terrateamio/ttm-dev:20251105-971-add-kv-store-caps-0dac2d4-amd64"

ENV SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"

ENTRYPOINT ["/entrypoint.sh"]
