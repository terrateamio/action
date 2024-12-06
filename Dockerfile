FROM ghcr.io/terrateamio/action-base:latest

ENV TENV_LATEST_VERSION=v3.2.10
RUN curl -O -L "https://github.com/tofuutils/tenv/releases/latest/download/tenv_${TENV_LATEST_VERSION}_amd64.deb" && \
    dpkg -i "tenv_${TENV_LATEST_VERSION}_amd64.deb"

RUN rm /usr/local/bin/terraform /usr/local/bin/tofu /usr/local/bin/terragrunt

COPY entrypoint.sh /entrypoint.sh
COPY terrat_runner /terrat_runner

ENTRYPOINT ["/entrypoint.sh"]
