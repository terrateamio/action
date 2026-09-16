#include <openssl/crypto.h>
#include <openssl/err.h>
#include <openssl/evp.h>
#include <openssl/provider.h>
#include <openssl/rand.h>

#include <stdio.h>
#include <string.h>

static int failures;

static void check(int ok, const char *what)
{
    printf("%-56s %s\n", what, ok ? "ok" : "FAIL");
    if (!ok) {
        failures++;
        ERR_print_errors_fp(stdout);
        ERR_clear_error();
    }
}

static int provider_of_md(const char *alg, const char *props, const char *want)
{
    EVP_MD *md = EVP_MD_fetch(NULL, alg, props);
    int ok = 0;

    if (md != NULL) {
        const OSSL_PROVIDER *prov = EVP_MD_get0_provider(md);

        ok = prov != NULL && strcmp(OSSL_PROVIDER_get0_name(prov), want) == 0;
        EVP_MD_free(md);
    }

    return ok;
}

static int provider_of_cipher(const char *alg, const char *want)
{
    EVP_CIPHER *cipher = EVP_CIPHER_fetch(NULL, alg, NULL);
    int ok = 0;

    if (cipher != NULL) {
        const OSSL_PROVIDER *prov = EVP_CIPHER_get0_provider(cipher);

        ok = prov != NULL && strcmp(OSSL_PROVIDER_get0_name(prov), want) == 0;
        EVP_CIPHER_free(cipher);
    }

    return ok;
}

/* NIST FIPS 180-4 SHA-256 sample: the digest of "abc". */
static const unsigned char sha256_abc[] = {
    0xba, 0x78, 0x16, 0xbf, 0x8f, 0x01, 0xcf, 0xea, 0x41, 0x41, 0x40,
    0xde, 0x5d, 0xae, 0x22, 0x23, 0xb0, 0x03, 0x61, 0xa3, 0x96, 0x17,
    0x7a, 0x9c, 0xb4, 0x10, 0xff, 0x61, 0xf2, 0x00, 0x15, 0xad
};

static int sha256_known_answer(void)
{
    unsigned char out[EVP_MAX_MD_SIZE];
    unsigned int len = 0;
    int ok = 0;
    EVP_MD *md = EVP_MD_fetch(NULL, "SHA2-256", NULL);
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();

    if (md != NULL && ctx != NULL
        && EVP_DigestInit_ex(ctx, md, NULL) == 1
        && EVP_DigestUpdate(ctx, "abc", 3) == 1
        && EVP_DigestFinal_ex(ctx, out, &len) == 1) {
        ok = len == sizeof(sha256_abc) && memcmp(out, sha256_abc, len) == 0;
    }

    EVP_MD_CTX_free(ctx);
    EVP_MD_free(md);

    return ok;
}

static int aes_256_gcm_round_trip(void)
{
    static const unsigned char key[32] = { 0 };
    static const unsigned char iv[12] = { 0 };
    const unsigned char plain[] = "terrateam fips round trip";
    unsigned char cipher_text[sizeof(plain) + 16];
    unsigned char plain_out[sizeof(plain) + 16];
    unsigned char tag[16];
    int len = 0;
    int cipher_len = 0;
    int plain_len = 0;
    int ok = 0;
    EVP_CIPHER *cipher = EVP_CIPHER_fetch(NULL, "AES-256-GCM", NULL);
    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();

    if (cipher != NULL && ctx != NULL
        && EVP_EncryptInit_ex(ctx, cipher, NULL, key, iv) == 1
        && EVP_EncryptUpdate(ctx, cipher_text, &len, plain, (int)sizeof(plain)) == 1) {
        cipher_len = len;
        if (EVP_EncryptFinal_ex(ctx, cipher_text + cipher_len, &len) == 1) {
            cipher_len += len;
            ok = EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_GET_TAG, sizeof(tag), tag) == 1;
        }
    }

    if (ok) {
        ok = EVP_CIPHER_CTX_reset(ctx) == 1
            && EVP_DecryptInit_ex(ctx, cipher, NULL, key, iv) == 1
            && EVP_DecryptUpdate(ctx, plain_out, &len, cipher_text, cipher_len) == 1;
        plain_len = len;
    }

    if (ok) {
        ok = EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_SET_TAG, sizeof(tag), tag) == 1
            && EVP_DecryptFinal_ex(ctx, plain_out + plain_len, &len) == 1;
        plain_len += len;
    }

    if (ok) {
        ok = plain_len == (int)sizeof(plain) && memcmp(plain_out, plain, sizeof(plain)) == 0;
    }

    EVP_CIPHER_CTX_free(ctx);
    EVP_CIPHER_free(cipher);

    return ok;
}

static int random_bytes(void)
{
    unsigned char buf[32];

    return RAND_bytes(buf, sizeof(buf)) == 1;
}

int main(void)
{
    printf("OpenSSL: %s\n", OpenSSL_version(OPENSSL_VERSION_STRING));
    printf("Config:  %s\n", OpenSSL_version(OPENSSL_DIR));
    printf("Modules: %s\n\n", OpenSSL_version(OPENSSL_MODULES_DIR));

    check(OSSL_PROVIDER_available(NULL, "fips") == 1, "fips provider is available");
    check(EVP_default_properties_is_fips_enabled(NULL) == 1, "fips=yes is the default property");
    check(provider_of_md("SHA2-256", NULL, "fips"), "SHA2-256 resolves to the fips provider");
    check(provider_of_cipher("AES-256-GCM", "fips"), "AES-256-GCM resolves to the fips provider");
    check(sha256_known_answer(), "SHA2-256 matches the FIPS 180-4 sample");
    check(aes_256_gcm_round_trip(), "AES-256-GCM encrypts and decrypts");
    check(random_bytes(), "RAND_bytes gives random data");
    check(EVP_MD_fetch(NULL, "MD5", NULL) == NULL, "MD5 is not available by default");

    /* The runner digests plan files with MD5 for log correlation only. That path asks
       for a non-approved algorithm with "-fips", which the default provider answers. */
    check(provider_of_md("MD5", "-fips", "default"), "MD5 with -fips resolves to the default provider");

    if (failures > 0) {
        printf("\n%d check(s) failed\n", failures);
        return 1;
    }

    printf("\nall checks passed\n");

    return 0;
}
