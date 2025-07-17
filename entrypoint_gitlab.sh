#! /bin/sh

# Start the Terrat Runner with SSH agent
echo "Starting Terrat Runner"
ssh-agent python3 /terrat_runner/main.py \
        --work-token "$WORK_TOKEN" \
        --workspace "$(pwd)" \
        --api-base-url "$API_BASE_URL" \
        --run-id "$CI_JOB_ID" \
        --sha "$CI_COMMIT_SHA" \
        --runtime gitlab
