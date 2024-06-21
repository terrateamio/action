#!/usr/bin/env bash
set -x

export PATH="$PATH":/usr/local/proxy/bin

if [ -n "$HTTPS_PROXY" ] && [ -n "$HTTPS_PROXY_DOMAINS" ]; then
  /usr/local/bin/http-proxy-add-self-signed-certs
fi

WORK_TOKEN="$1"
API_BASE_URL="$2"

# Ensure required environment variables are set
if [ -z "$GITHUB_WORKSPACE" ] || [ -z "$GITHUB_RUN_ID" ] || [ -z "$GITHUB_SHA" ]; then
  echo "Error: Missing required environment variables."
  exit 1
fi

echo "Starting Terrat Runner"

eval "$(ssh-agent -s)"
ssh-add

python3 /terrat_runner/main.py \
        --work-token "$WORK_TOKEN" \
        --workspace "$GITHUB_WORKSPACE" \
        --api-base-url "$API_BASE_URL" \
        --run-id "$GITHUB_RUN_ID" \
        --sha "$GITHUB_SHA"
