FROM alpine:3.13


RUN apk add --no-cache \
    ca-certificates \
    gnupg \
    curl \
    git \
    git-lfs \
    unzip \
    bash \
    openssh \
    libcap \
    openssl \
    python3 \
    py3-pycryptodome \
    py3-requests \
    py3-yaml \
    openssh

COPY install-terraform-version /install-terraform-version

ENV DEFAULT_TERRAFORM_VERSION=1.1.2

# Other versions
# 0.8.8 0.9.11 0.10.8 0.11.15 0.12.31 0.13.7 0.14.11 0.15.5 1.0.7

RUN /install-terraform-version latest

ADD https://github.com/gruntwork-io/terragrunt/releases/download/v0.36.10/terragrunt_linux_amd64 /usr/local/bin/terragrunt

RUN chmod +x /usr/local/bin/terragrunt

COPY entrypoint.sh /entrypoint.sh
COPY terrat_runner /terrat_runner

ENTRYPOINT ["/entrypoint.sh"]
