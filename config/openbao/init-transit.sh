#!/usr/bin/env bash
# Initialize OpenBao Transit secrets engine for credential signing.
#
# Usage (dev mode):
#   export BAO_ADDR=http://127.0.0.1:8200
#   export BAO_TOKEN=dev-root-token
#   ./config/openbao/init-transit.sh
#
# This script is idempotent — safe to re-run.

set -euo pipefail

BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:8200}"
BAO_TOKEN="${BAO_TOKEN:-dev-root-token}"

export BAO_ADDR BAO_TOKEN

echo "=== OpenBao Transit Init ==="
echo "    Address: ${BAO_ADDR}"

# Wait for OpenBao to be ready
for i in $(seq 1 30); do
    if bao status -address="${BAO_ADDR}" > /dev/null 2>&1; then
        echo "    OpenBao is ready."
        break
    fi
    echo "    Waiting for OpenBao... (${i}/30)"
    sleep 1
done

# Enable transit secrets engine (idempotent)
if ! bao secrets list -address="${BAO_ADDR}" | grep -q "^transit/"; then
    echo "    Enabling transit secrets engine..."
    bao secrets enable -address="${BAO_ADDR}" transit
else
    echo "    Transit engine already enabled."
fi

# Create default signing keys for development/testing
# These keys are for development only — production keys are provisioned
# via the credential template setup flow.

echo "    Creating dev signing keys..."

# ES256 (P-256) key for JWT-VC and SD-JWT
bao write -address="${BAO_ADDR}" -f transit/keys/dev-es256 \
    type=ecdsa-p256 \
    exportable=false \
    allow_plaintext_backup=false \
    2>/dev/null || echo "    dev-es256 already exists"

# EdDSA (Ed25519) key for JWT-VC
bao write -address="${BAO_ADDR}" -f transit/keys/dev-eddsa \
    type=ed25519 \
    exportable=false \
    allow_plaintext_backup=false \
    2>/dev/null || echo "    dev-eddsa already exists"

# RSA-2048 key for SOD signing
bao write -address="${BAO_ADDR}" -f transit/keys/dev-rsa \
    type=rsa-2048 \
    exportable=false \
    allow_plaintext_backup=false \
    2>/dev/null || echo "    dev-rsa already exists"

echo "=== Transit init complete ==="

# Create a restricted policy for the issuance service
cat <<'POLICY' | bao policy write -address="${BAO_ADDR}" credential-signer -
# Allow signing with transit keys but not reading/exporting them
path "transit/sign/*" {
  capabilities = ["update"]
}
path "transit/verify/*" {
  capabilities = ["update"]
}
path "transit/keys/*" {
  capabilities = ["read"]
}
POLICY

echo "    Policy 'credential-signer' created."

# Create an AppRole for the issuance service (dev mode)
if ! bao auth list -address="${BAO_ADDR}" | grep -q "^approle/"; then
    bao auth enable -address="${BAO_ADDR}" approle
fi

bao write -address="${BAO_ADDR}" auth/approle/role/credential-signer \
    token_policies=credential-signer \
    token_ttl=1h \
    token_max_ttl=4h \
    2>/dev/null

echo "    AppRole 'credential-signer' configured."

# ============================================================================
# PKI Secrets Engine — DSC Certificate Authority (K34)
# ============================================================================
# Enable a PKI engine for issuing Document Signer Certificates (DSCs).
# The Transit engine handles signing keys, while PKI manages X.509 certs.

if ! bao secrets list -address="${BAO_ADDR}" | grep -q "^pki/"; then
    echo "    Enabling PKI secrets engine..."
    bao secrets enable -address="${BAO_ADDR}" pki
    bao secrets tune -address="${BAO_ADDR}" -max-lease-ttl=87600h pki
else
    echo "    PKI engine already enabled."
fi

# Generate internal root CA (dev only — production uses external CA)
bao write -address="${BAO_ADDR}" pki/root/generate/internal \
    common_name="Marty Dev Root CA" \
    organization="Marty Labs" \
    ttl=87600h \
    2>/dev/null || echo "    PKI root CA already exists"

# Configure CA and CRL URLs
bao write -address="${BAO_ADDR}" pki/config/urls \
    issuing_certificates="${BAO_ADDR}/v1/pki/ca" \
    crl_distribution_points="${BAO_ADDR}/v1/pki/crl"

# Create DSC issuing role — issues Document Signer Certificates
bao write -address="${BAO_ADDR}" pki/roles/document-signer \
    allow_any_name=false \
    allowed_domains="marty.dev" \
    allow_subdomains=true \
    max_ttl=26280h \
    key_type=ec \
    key_bits=256 \
    key_usage="DigitalSignature,ContentCommitment" \
    no_store=false \
    generate_lease=true

echo "    PKI role 'document-signer' configured."

# Policy for DSC issuance
cat <<'POLICY' | bao policy write -address="${BAO_ADDR}" pki-dsc-issuer -
# Allow requesting DSC certificates via the document-signer role
path "pki/issue/document-signer" {
  capabilities = ["create", "update"]
}
path "pki/sign/document-signer" {
  capabilities = ["create", "update"]
}
path "pki/ca" {
  capabilities = ["read"]
}
path "pki/crl" {
  capabilities = ["read"]
}
POLICY

echo "    Policy 'pki-dsc-issuer' created."

echo "=== OpenBao setup complete ==="
