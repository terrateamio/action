#!/usr/bin/env bash

# Set PATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Adding /usr/local/proxy/bin to the PATH for accessing additional tools, if needed
export PATH="$PATH":/usr/local/proxy/bin

# Append $TERRATEAM_APPEND_PATH to $PATH
if [ "$TERRATEAM_APPEND_PATH" ]; then
  export PATH="$PATH:$TERRATEAM_APPEND_PATH"
fi

# Install custom CA certificates
has_custom_certs=false

# Loop through all CUSTOM_CA_BUNDLE_* variables
# Each variable must contain a single PEM-encoded certificate
for var in "${!CUSTOM_CA_BUNDLE_@}"; do
  cert="${!var}"
  if [ -n "$cert" ]; then
    file="/usr/local/share/ca-certificates/${var}.crt"
    echo "$cert" > "$file"
    echo "Wrote custom CA cert to $file"
    has_custom_certs=true
  fi
done

if [ "$has_custom_certs" = true ]; then
  update-ca-certificates
fi

# Arguments: WORK_TOKEN and API_BASE_URL, passed during the action setup
WORK_TOKEN="$1"
API_BASE_URL="$2"

# Deprecated
# WARNING: The following script, `unsafe-add-certs`, is insecure and should not be relied upon in production environments.
# It is slated for removal in the future to avoid any potential security vulnerabilities.
# If HTTPS_PROXY and HTTPS_PROXY_DOMAINS are set, proceed with caution.
if [ -n "$HTTPS_PROXY" ] && [ -n "$HTTPS_PROXY_DOMAINS" ]; then
  /usr/local/bin/unsafe-add-certs # temporary script; not recommended for production use
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
