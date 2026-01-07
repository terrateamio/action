#!/usr/bin/env bash
# FIPS status detection helper
# Detects whether FIPS mode is enabled on the host system and optionally enforces it.

set -euf -o pipefail

FIPS_ENABLED=0

# Check if FIPS is enabled via kernel parameter
if [ -f /proc/sys/crypto/fips_enabled ]; then
    FIPS_ENABLED=$(cat /proc/sys/crypto/fips_enabled 2>/dev/null || echo "0")
fi

# Display FIPS status
if [ "$FIPS_ENABLED" = "1" ]; then
    echo "FIPS mode: enabled (OpenSSL: $(openssl version 2>/dev/null || echo 'unknown'))"
else
    echo "FIPS mode: disabled (OpenSSL: $(openssl version 2>/dev/null || echo 'unknown'))"
fi

# If REQUIRE_FIPS is set to 1, fail if FIPS is not enabled
if [ "${REQUIRE_FIPS:-0}" = "1" ] && [ "$FIPS_ENABLED" != "1" ]; then
    echo "ERROR: REQUIRE_FIPS=1 but FIPS mode is not enabled on the host system"
    exit 1
fi

exit 0
