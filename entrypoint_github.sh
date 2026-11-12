#! /bin/sh

# Arguments: WORK_TOKEN and API_BASE_URL, passed during the action setup
WORK_TOKEN="$1"
API_BASE_URL="$2"

# tenv takes a version directory as installed, so a version directory without
# an executable makes every run of that version fail.  Remove it so that tenv
# installs the version again.
for version_dir in "${TENV_ROOT:-$HOME/.tenv}"/*/*/; do
    if [ -d "$version_dir" ] && [ -z "$(find "$version_dir" -maxdepth 1 -type f -perm -u+x)" ]; then
        echo "Removing incomplete tenv install: $version_dir"
        rm -rf "$version_dir"
    fi
done

# Start the Terrat Runner with SSH agent
echo "Starting Terrat Runner"
ssh-agent python3 /terrat_runner/main.py \
        --work-token "$WORK_TOKEN" \
        --workspace "$GITHUB_WORKSPACE" \
        --api-base-url "$API_BASE_URL" \
        --run-id "$GITHUB_RUN_ID" \
        --sha "$GITHUB_SHA"
