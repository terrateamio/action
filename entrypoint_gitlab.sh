#! /bin/sh

# Set PATH
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Adding /usr/local/proxy/bin to the PATH for accessing additional tools, if needed
export PATH="$PATH":/usr/local/proxy/bin

# Prepend $TERRATEAM_PREPEND_PATH to $PATH
if [ "$TERRATEAM_PREPEND_PATH" ]; then
  export PATH="$TERRATEAM_PREPEND_PATH:$PATH"
fi

# Append $TERRATEAM_APPEND_PATH to $PATH
if [ "$TERRATEAM_APPEND_PATH" ]; then
  export PATH="$PATH:$TERRATEAM_APPEND_PATH"
fi

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
        --workspace "$(pwd)" \
        --api-base-url "$API_BASE_URL" \
        --run-id "$CI_JOB_ID" \
        --sha "$CI_COMMIT_SHA" \
        --runtime gitlab
