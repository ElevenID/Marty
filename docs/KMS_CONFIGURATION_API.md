# KMS Configuration API Documentation

## Overview

The KMS Configuration API allows production tier organizations (STARTER, PROFESSIONAL, ENTERPRISE) to configure their own Key Management Service (KMS) or Hardware Security Module (HSM) for remote signing operations.

**Base URL:** `/v1/subscriptions/organizations/{org_id}/kms`

**Authentication:** Bearer token (organization-scoped)

## Supported KMS Providers

| Provider | Status | Description |
|----------|--------|-------------|
| `aws_kms` | ✅ Production | AWS Key Management Service |
| `hashicorp_vault` | ✅ Production | HashiCorp Vault Transit Engine |
| `pkcs11_hsm` | ✅ Production | PKCS#11 Hardware Security Modules |
| `software_hsm` | ⚠️ Development Only | Software-based HSM (testing) |
| `azure_key_vault` | 🚧 Coming Soon | Azure Key Vault |
| `gcp_kms` | 🚧 Coming Soon | Google Cloud KMS |

## Endpoints

### 1. Configure KMS

Configure KMS/HSM for remote signing.

**Endpoint:** `POST /v1/subscriptions/organizations/{org_id}/kms/configure`

**Requirements:**
- Organization must have STARTER, PROFESSIONAL, or ENTERPRISE tier
- Valid KMS credentials
- Proper IAM/access permissions in KMS provider

#### Request Body

##### AWS KMS Example

```json
{
  "provider": "aws_kms",
  "credentials": {
    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
  },
  "config": {
    "region": "us-west-2",
    "key_id": "arn:aws:kms:us-west-2:123456789012:key/12345678-1234-1234-1234-123456789012",
    "algorithm": "ECDSA_SHA_256",
    "endpoint_url": null,
    "metadata": {
      "key_alias": "marty-signing-key",
      "description": "Production signing key",
      "rotation_enabled": true
    }
  }
}
```

##### HashiCorp Vault Example

```json
{
  "provider": "hashicorp_vault",
  "credentials": {
    "token": "hvs.CAESIJX...",
    "auth_method": "token"
  },
  "config": {
    "endpoint_url": "https://vault.example.com:8200",
    "algorithm": "ES256",
    "metadata": {
      "mount_point": "transit",
      "key_name": "marty-signing-key",
      "namespace": "production"
    }
  }
}
```

##### PKCS#11 HSM Example

```json
{
  "provider": "pkcs11_hsm",
  "credentials": {
    "user_pin": "1234"
  },
  "config": {
    "algorithm": "ES256",
    "metadata": {
      "library_path": "/usr/lib/softhsm/libsofthsm2.so",
      "token_label": "marty-token",
      "slot_id": 0
    }
  }
}
```

#### Response (200 OK)

```json
{
  "provider": "aws_kms",
  "region": "us-west-2",
  "algorithm": "ECDSA_SHA_256",
  "endpoint_url": null,
  "metadata": {
    "key_alias": "marty-signing-key",
    "description": "Production signing key",
    "rotation_enabled": true
  },
  "configured_at": "2026-04-06T10:30:00Z"
}
```

**Note:** Credentials are **never** returned in responses for security.

#### Error Responses

**400 Bad Request** - Invalid configuration or tier not allowed:
```json
{
  "detail": "Tier 'free' uses service key vault with automatic rotation. KMS configuration is only available for production tiers (STARTER, PROFESSIONAL, ENTERPRISE)."
}
```

**400 Bad Request** - Missing required fields:
```json
{
  "detail": "AWS KMS requires 'region' in config"
}
```

**404 Not Found** - Organization not found:
```json
{
  "detail": "Organization f47ac10b-58cc-4372-a567-0e02b2c3d479 not found"
}
```

---

### 2. Get KMS Configuration

Retrieve current KMS configuration (credentials redacted).

**Endpoint:** `GET /v1/subscriptions/organizations/{org_id}/kms`

#### Response (200 OK)

```json
{
  "provider": "aws_kms",
  "region": "us-west-2",
  "algorithm": "ECDSA_SHA_256",
  "endpoint_url": null,
  "metadata": {
    "key_alias": "marty-signing-key",
    "rotation_enabled": true
  }
}
```

#### Error Responses

**404 Not Found** - KMS not configured:
```json
{
  "detail": "KMS not configured for this organization"
}
```

---

### 3. Delete KMS Configuration

Remove KMS configuration. **WARNING:** This will disable remote signing.

**Endpoint:** `DELETE /v1/subscriptions/organizations/{org_id}/kms`

#### Response (204 No Content)

No response body.

---

### 4. Test KMS Connectivity

Test connectivity to configured KMS provider.

**Endpoint:** `POST /v1/subscriptions/organizations/{org_id}/kms/test-connectivity`

#### Response (200 OK) - Success

```json
{
  "connected": true,
  "provider": "aws_kms",
  "error": null,
  "note": null
}
```

#### Response (200 OK) - Failure

```json
{
  "connected": false,
  "provider": "aws_kms",
  "error": "UnrecognizedClientException: The security token included in the request is invalid",
  "note": null
}
```

---

### 5. Test Remote Signing

Perform a test signing operation to verify configuration.

**Endpoint:** `POST /v1/subscriptions/organizations/{org_id}/kms/test-signing`

#### Request Body

```json
{
  "key_id": "arn:aws:kms:us-west-2:123456789012:key/12345678-1234-1234-1234-123456789012",
  "test_payload": "test signing operation",
  "algorithm": "ECDSA_SHA_256"
}
```

#### Response (200 OK) - Success

```json
{
  "success": true,
  "signature": "3045022100a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef12345678022012345678abcdef90abcdef1234567890abcdef1234567890abcdef1234567890",
  "error": null
}
```

#### Response (200 OK) - Failure

```json
{
  "success": false,
  "signature": null,
  "error": "Remote signing failed: AWS KMS error: KeyUnavailableException"
}
```

---

## Complete Workflow Example

### Step 1: Check Current Tier

Ensure your organization has a production tier subscription:

```bash
curl -X GET \
  'https://api.example.com/v1/subscriptions/organizations/{org_id}/subscription' \
  -H 'Authorization: Bearer {token}'
```

Expected response should show tier as `starter`, `professional`, or `enterprise`.

### Step 2: Configure AWS KMS

```bash
curl -X POST \
  'https://api.example.com/v1/subscriptions/organizations/{org_id}/kms/configure' \
  -H 'Authorization: Bearer {token}' \
  -H 'Content-Type: application/json' \
  -d '{
    "provider": "aws_kms",
    "credentials": {
      "access_key_id": "AKIA...",
      "secret_access_key": "..."
    },
    "config": {
      "region": "us-west-2",
      "key_id": "arn:aws:kms:us-west-2:123:key/abc123",
      "algorithm": "ECDSA_SHA_256"
    }
  }'
```

### Step 3: Test Connectivity

```bash
curl -X POST \
  'https://api.example.com/v1/subscriptions/organizations/{org_id}/kms/test-connectivity' \
  -H 'Authorization: Bearer {token}'
```

### Step 4: Test Signing Operation

```bash
curl -X POST \
  'https://api.example.com/v1/subscriptions/organizations/{org_id}/kms/test-signing' \
  -H 'Authorization: Bearer {token}' \
  -H 'Content-Type: application/json' \
  -d '{
    "key_id": "arn:aws:kms:us-west-2:123:key/abc123",
    "test_payload": "hello world",
    "algorithm": "ECDSA_SHA_256"
  }'
```

### Step 5: Use in Production

Once configured and tested, all signing operations will automatically use your KMS:

```bash
curl -X POST \
  'https://api.example.com/v1/identity/credentials/issue' \
  -H 'Authorization: Bearer {token}' \
  -H 'Content-Type: application/json' \
  -d '{
    "template_id": "template-123",
    "subject_data": {
      "given_name": "John",
      "family_name": "Doe"
    }
  }'
```

The credential will be signed using your configured KMS automatically.

---

## Security Best Practices

### Credential Management

1. **Use IAM Roles (AWS):** Prefer IAM roles over access keys when possible
2. **Rotate Credentials:** Rotate KMS credentials regularly
3. **Least Privilege:** Grant only necessary KMS permissions
4. **Audit Logging:** Enable KMS audit logging in your provider

### Required AWS KMS Permissions

Minimum IAM policy for AWS KMS:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kms:Sign",
        "kms:GetPublicKey",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:REGION:ACCOUNT:key/KEY_ID"
    }
  ]
}
```

### Network Security

1. **Enable VPC Endpoints:** Use VPC endpoints for AWS KMS to avoid public internet
2. **IP Allowlisting:** Configure IP allowlists in your KMS provider if supported
3. **TLS:** Always use TLS 1.2+ for KMS communication

---

## Troubleshooting

### Common Errors

#### "Tier 'free' uses service key vault"

**Cause:** Attempting to configure KMS on FREE or DEVS tier.

**Solution:** Upgrade to STARTER, PROFESSIONAL, or ENTERPRISE tier.

#### "AWS KMS requires 'region' in config"

**Cause:** Missing required configuration field.

**Solution:** Ensure all required fields are provided:
- AWS KMS: `region`, `access_key_id`, `secret_access_key`
- Azure Key Vault: `endpoint_url`, `tenant_id`, `client_id`, `client_secret`
- GCP KMS: `region`, `project_id`, service account JSON
- PKCS#11: `library_path`, `token_label`, `user_pin`

#### "UnrecognizedClientException: The security token included in the request is invalid"

**Cause:** Invalid or expired AWS credentials.

**Solution:** 
1. Verify access key ID and secret access key
2. Check IAM user/role exists and is active
3. Ensure credentials haven't been rotated

#### "KeyUnavailableException"

**Cause:** KMS key is disabled, pending deletion, or unavailable.

**Solution:**
1. Check key status in AWS KMS console
2. Verify key is enabled
3. Ensure key is not pending deletion

---

## Rate Limits

- **Configure KMS:** 10 requests per hour per organization
- **Get Config:** 100 requests per minute per organization
- **Test Connectivity:** 10 requests per minute per organization
- **Test Signing:** 5 requests per minute per organization

Exceeding rate limits results in `429 Too Many Requests`.

---

## Monitoring

### Recommended Metrics

Track these metrics for your KMS configuration:

1. **Signing Latency:** Time to complete signing operations
2. **Success Rate:** Percentage of successful vs failed signatures
3. **KMS Availability:** Uptime of KMS connectivity tests
4. **Error Rate:** Frequency and types of KMS errors

### Webhook Events

Subscribe to these webhook events for KMS monitoring:

- `kms.configured` - KMS configuration created/updated
- `kms.deleted` - KMS configuration removed
- `kms.connectivity.failed` - KMS connectivity test failed
- `signing.failed` - Remote signing operation failed

---

## Migration from Service Key Vault

If upgrading from FREE/DEVS tier with service key vault:

1. **Configure KMS** before upgrading tier
2. **Test thoroughly** with test signing endpoint
3. **Rotate existing credentials** issued with service vault
4. **Monitor** signing operations for 48 hours post-migration

**Note:** Credentials signed with service vault keys remain valid but cannot be verified if you delete the service vault keys.

---

## Support

For issues with KMS configuration:

1. Test connectivity endpoint first
2. Check KMS provider's service status
3. Review IAM/access permissions
4. Check audit logs in your KMS provider
5. Contact support with error details and request ID

**Support Contact:** support@example.com
