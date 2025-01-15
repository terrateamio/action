#! /bin/sh

set -x

# Adding /usr/local/proxy/bin to the PATH for accessing additional tools, if needed
export PATH="$PATH":/usr/local/proxy/bin

# Arguments: WORK_TOKEN and API_BASE_URL, passed during the action setup
WORK_TOKEN="$1"
API_BASE_URL="$2"

# Deprecated
# WARNING: The following script, `unsafe-add-certs`, is insecure and should not be relied upon in production environments.
# It is slated for removal in the future to avoid any potential security vulnerabilities.
# If HTTPS_PROXY and HTTPS_PROXY_DOMAINS are set, proceed with caution.
if [ -n "$HTTPS_PROXY" ] && [ -n "$HTTPS_PROXY_DOMAINS" ]; then
  bash -x /usr/local/bin/unsafe-add-certs # temporary script; not recommended for production use
fi

export TENV_AUTO_INSTALL=true

# Start the Terrat Runner with SSH agent
echo "Starting Terrat Runner"
ssh-agent python3 /terrat_runner/main.py \
        --work-token "$WORK_TOKEN" \
        --workspace "$GITHUB_WORKSPACE" \
        --api-base-url "$API_BASE_URL" \
        --run-id "$GITHUB_RUN_ID" \
        --sha "$GITHUB_SHA"
