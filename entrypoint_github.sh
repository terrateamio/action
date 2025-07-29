#! /bin/sh

# Arguments: WORK_TOKEN and API_BASE_URL, passed during the action setup
WORK_TOKEN="$1"
API_BASE_URL="$2"

# Start the Terrat Runner with SSH agent
echo "Starting Terrat Runner"
ssh-agent python3 /terrat_runner/main.py \
        --work-token "$WORK_TOKEN" \
        --workspace "$GITHUB_WORKSPACE" \
        --api-base-url "$API_BASE_URL" \
        --run-id "$GITHUB_RUN_ID" \
        --sha "$GITHUB_SHA"
