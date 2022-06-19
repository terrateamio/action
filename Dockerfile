FROM terrateam/action-base:latest
RUN apk add --update-cache \
    aws-cli \
    && rm -rf /var/cache/apk/*

COPY entrypoint.sh /entrypoint.sh
COPY terrat_runner /terrat_runner

ENTRYPOINT ["/entrypoint.sh"]
