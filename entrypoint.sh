#! /bin/sh

export PATH="$PATH":/usr/local/proxy/bin

WORK_TOKEN="$1"
API_BASE_URL="$2"

if [ -n "$HTTPS_PROXY" ] && [ -n "$HTTPS_PROXY_DOMAINS" ]; then
  /usr/local/bin/http-proxy-add-self-signed-certs
fi

echo "Starting Terrat Runner"
ssh-agent python3 /terrat_runner/main.py \
        --work-token "$WORK_TOKEN" \
        --workspace "$GITHUB_WORKSPACE" \
        --api-base-url "$API_BASE_URL" \
        --run-id "$GITHUB_RUN_ID" \
        --sha "$GITHUB_SHA"
