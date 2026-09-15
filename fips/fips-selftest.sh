#! /bin/sh
# Asserts that the assembled image resolves cryptography to the FIPS provider.

set -eu

SSL_PREFIX=${SSL_PREFIX:-/usr/local/ssl}
failures=0

check() {
    name=$1
    shift
    if "$@" > /tmp/fips-selftest.out 2>&1; then
        echo "ok   ${name}"
    else
        echo "FAIL ${name}"
        sed 's/^/     /' /tmp/fips-selftest.out
        failures=$((failures + 1))
    fi
}

only_one_libcrypto() {
    ! test -e /usr/lib/libcrypto.so.3 && ! test -e /usr/lib/libssl.so.3
}

fips_provider_active() {
    openssl list -providers | grep -A3 -E '^ *fips$' | grep -q 'status: active'
}

openssl_is_the_fips_build() {
    openssl version -d | grep -q "${SSL_PREFIX}"
}

python_digests() {
    python3 - <<'PY'
import hashlib
import ssl

print('ssl:', ssl.OPENSSL_VERSION)
assert hashlib.sha256(b'abc').hexdigest() == (
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')

try:
    hashlib.md5(b'abc')
except ValueError:
    pass
else:
    raise AssertionError('md5 is available by default')

# The runner digests plan files with MD5 for log correlation only.
assert hashlib.md5(b'abc', usedforsecurity=False).hexdigest() == (
    '900150983cd24fb0d6963f7d28e17f72')
PY
}

apk_over_tls() {
    out=$(apk update 2>&1) || return 1
    ! echo "${out}" | grep -q 'error:'
}

tls_works() {
    curl -fsS -o /dev/null https://github.com/ && \
        python3 -c "import urllib.request; urllib.request.urlopen('https://github.com/').read(1)"
}

git_works() {
    d=$(mktemp -d) && \
        git -C "${d}" init -q && \
        : > "${d}/f" && \
        git -C "${d}" -c user.email=a@b -c user.name=c add f && \
        git -C "${d}" -c user.email=a@b -c user.name=c commit -qm f && \
        rm -rf "${d}"
}

check "openssl fips self test" openssl-fips-test
check "one libcrypto in the image" only_one_libcrypto
check "openssl cli is the fips build" openssl_is_the_fips_build
check "fips provider is active" fips_provider_active
check "python digests" python_digests
check "tls client" tls_works
check "apk over tls" apk_over_tls
check "git object hashing" git_works
check "tofu runs" tofu version
check "conftest runs" conftest --version
check "infracost runs" infracost --version
check "checkov runs" checkov --version
check "aws cli runs" aws --version
check "ssh agent runs" ssh-agent -c

rm -f /tmp/fips-selftest.out

if [ "${failures}" -gt 0 ]; then
    echo "${failures} check(s) failed"
    exit 1
fi

echo "all checks passed"
