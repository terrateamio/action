FROM ghcr.io/terrateamio/action-base:latest

COPY entrypoint.sh /entrypoint.sh
COPY entrypoint_gitlab.sh /entrypoint_gitlab.sh
COPY entrypoint_github.sh /entrypoint_github.sh
COPY terrat_runner /terrat_runner

COPY proxy/bin /usr/local/proxy/bin
COPY ./bin/ /usr/local/bin

# HashiCorp's signatures for old releases of Terraform have expired so we can only do hash checks
ENV TENV_VALIDATION=sha

ENTRYPOINT ["/entrypoint.sh"]
