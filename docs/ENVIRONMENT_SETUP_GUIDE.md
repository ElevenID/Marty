# Environment Setup Guide

## KMS Configuration Environment Variables

This guide covers the environment variables required for KMS configuration and remote signing features.

## Required Environment Variables

### KMS_ENCRYPTION_KEY

**Purpose:** Fernet encryption key for securing KMS credentials at rest.

**Required:** Yes (for production)

**Format:** 32-byte base64-encoded key

#### Generate Encryption Key

**Using Python:**
```python
from cryptography.fernet import Fernet

# Generate a new key
key = Fernet.generate_key()
print(key.decode())
```

**Using OpenSSL:**
```bash
openssl rand -base64 32
```

**Example Output:**
```
jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G=
```

#### Set in Environment

**.env file:**
```bash
# KMS Credential Encryption Key
# CRITICAL: Keep this secret! Losing this key means losing access to KMS credentials.
KMS_ENCRYPTION_KEY=jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G=
```

**Docker Compose:**
```yaml
services:
  api:
    environment:
      - KMS_ENCRYPTION_KEY=${KMS_ENCRYPTION_KEY}
```

**Kubernetes Secret:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: marty-secrets
type: Opaque
stringData:
  kms-encryption-key: jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G=
```

```yaml
# In deployment
env:
  - name: KMS_ENCRYPTION_KEY
    valueFrom:
      secretKeyRef:
        name: marty-secrets
        key: kms-encryption-key
```

#### Security Best Practices

1. **Never commit to version control:** Add to `.gitignore`
2. **Rotate regularly:** Generate new key and re-encrypt credentials
3. **Use secret management:** AWS Secrets Manager, HashiCorp Vault, etc.
4. **Backup securely:** Store encrypted backup of encryption key
5. **Access control:** Limit who can view environment variables

---

## Optional Environment Variables

### ENFORCE_HSM_ATTESTATION

**Purpose:** Enforce hardware HSM attestation for production roles.

**Default:** `true`

**Values:** `true` | `false`

**Usage:**
```bash
# Enforce HSM attestation (production)
ENFORCE_HSM_ATTESTATION=true

# Allow software HSM (development only)
ENFORCE_HSM_ATTESTATION=false
```

**When to Disable:**
- Local development with software HSM
- Testing environments
- Initial setup and debugging

**Never disable in production!**

---

## Database Configuration

Ensure database connection is properly configured:

### DATABASE_URL

**Format:** `postgresql://user:password@host:port/database`

**Example:**
```bash
DATABASE_URL=postgresql://marty:password@localhost:5432/marty_production
```

**With SSL:**
```bash
DATABASE_URL=postgresql://marty:password@db.example.com:5432/marty?sslmode=require
```

---

## Environment-Specific Configuration

### Development Environment

**.env.development:**
```bash
# Database
DATABASE_URL=postgresql://marty:dev@localhost:5432/marty_dev

# KMS Encryption (development key - DO NOT USE IN PRODUCTION)
KMS_ENCRYPTION_KEY=dev-key-jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G=

# Allow software HSM for testing
ENFORCE_HSM_ATTESTATION=false

# Logging
LOG_LEVEL=DEBUG

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### Staging Environment

**.env.staging:**
```bash
# Database
DATABASE_URL=postgresql://marty:stagingpass@staging-db.example.com:5432/marty_staging?sslmode=require

# KMS Encryption (staging-specific key)
KMS_ENCRYPTION_KEY=${STAGING_KMS_ENCRYPTION_KEY}

# Use production-like settings
ENFORCE_HSM_ATTESTATION=true

# Logging
LOG_LEVEL=INFO

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### Production Environment

**.env.production:**
```bash
# Database
DATABASE_URL=postgresql://marty:${DB_PASSWORD}@prod-db.example.com:5432/marty_production?sslmode=require

# KMS Encryption (from secret management system)
KMS_ENCRYPTION_KEY=${PRODUCTION_KMS_ENCRYPTION_KEY}

# Production settings
ENFORCE_HSM_ATTESTATION=true

# Logging
LOG_LEVEL=WARNING

# API
API_HOST=0.0.0.0
API_PORT=8000

# Monitoring
SENTRY_DSN=${SENTRY_DSN}
```

---

## Secret Management Integration

### AWS Secrets Manager

**Python Example:**
```python
import boto3
import os
from botocore.exceptions import ClientError

def get_secret(secret_name: str, region_name: str = "us-west-2") -> str:
    """Retrieve secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager', region_name=region_name)
    
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except ClientError as e:
        raise Exception(f"Failed to retrieve secret: {e}")

# In application startup
if not os.environ.get('KMS_ENCRYPTION_KEY'):
    os.environ['KMS_ENCRYPTION_KEY'] = get_secret('marty/kms-encryption-key')
```

**Terraform Configuration:**
```hcl
resource "aws_secretsmanager_secret" "kms_encryption_key" {
  name = "marty/kms-encryption-key"
  description = "Fernet encryption key for KMS credentials"
}

resource "aws_secretsmanager_secret_version" "kms_encryption_key" {
  secret_id     = aws_secretsmanager_secret.kms_encryption_key.id
  secret_string = random_password.kms_encryption_key.result
}

resource "random_password" "kms_encryption_key" {
  length  = 32
  special = true
}
```

### HashiCorp Vault

**Configuration:**
```bash
# Store in Vault
vault kv put secret/marty/kms-encryption-key value="jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G="

# Retrieve in application
export KMS_ENCRYPTION_KEY=$(vault kv get -field=value secret/marty/kms-encryption-key)
```

### Google Cloud Secret Manager

**Python Example:**
```python
from google.cloud import secretmanager

def access_secret(project_id: str, secret_id: str, version_id: str = "latest") -> str:
    """Access a secret from Google Cloud Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Usage
os.environ['KMS_ENCRYPTION_KEY'] = access_secret('my-project', 'kms-encryption-key')
```

---

## Verification

### Check Environment Variables

**Python:**
```python
import os
from cryptography.fernet import Fernet

# Check if key is set
kms_key = os.environ.get('KMS_ENCRYPTION_KEY')
if not kms_key:
    print("❌ KMS_ENCRYPTION_KEY not set!")
else:
    print("✅ KMS_ENCRYPTION_KEY is set")
    
    # Verify it's valid
    try:
        Fernet(kms_key.encode())
        print("✅ KMS_ENCRYPTION_KEY is valid")
    except Exception as e:
        print(f"❌ KMS_ENCRYPTION_KEY is invalid: {e}")
```

**Shell Script:**
```bash
#!/bin/bash

echo "Checking required environment variables..."

# Check KMS_ENCRYPTION_KEY
if [ -z "$KMS_ENCRYPTION_KEY" ]; then
    echo "❌ KMS_ENCRYPTION_KEY is not set"
    exit 1
else
    echo "✅ KMS_ENCRYPTION_KEY is set (${#KMS_ENCRYPTION_KEY} characters)"
fi

# Check DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL is not set"
    exit 1
else
    echo "✅ DATABASE_URL is set"
fi

echo "✅ All required environment variables are set"
```

---

## Troubleshooting

### "KMS_ENCRYPTION_KEY not set"

**Error:**
```
WARNING: KMS_ENCRYPTION_KEY not set - generated temporary key.
This is ONLY for development. Set KMS_ENCRYPTION_KEY in production.
```

**Solution:**
1. Generate encryption key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. Set in environment: `export KMS_ENCRYPTION_KEY="your-generated-key"`
3. Restart application

### "Invalid encryption key"

**Error:**
```
cryptography.fernet.InvalidToken: 
```

**Causes:**
- Encryption key changed after credentials were encrypted
- Wrong encryption key used
- Corrupted encrypted data

**Solutions:**
1. If key was rotated, use old key to decrypt and re-encrypt with new key
2. Delete and reconfigure KMS (credentials will be lost)
3. Restore from backup

### Can't decrypt KMS credentials

**Symptom:** Unable to use configured KMS, credentials appear corrupted.

**Debug steps:**
```python
from cryptography.fernet import Fernet
import os

# Get key and encrypted data from database
org_encrypted = "..."  # From database
kms_key = os.environ['KMS_ENCRYPTION_KEY'].encode()

# Try to decrypt
cipher = Fernet(kms_key)
try:
    decrypted = cipher.decrypt(org_encrypted.encode())
    print("✅ Decryption successful")
    print(decrypted.decode())
except Exception as e:
    print(f"❌ Decryption failed: {e}")
```

---

## Key Rotation

### Rotate Encryption Key

**Step 1: Generate new key**
```python
from cryptography.fernet import Fernet

new_key = Fernet.generate_key()
print(f"New key: {new_key.decode()}")
```

**Step 2: Re-encrypt all credentials**
```python
from cryptography.fernet import Fernet
import os

old_key = os.environ['KMS_ENCRYPTION_KEY'].encode()
new_key = b"your-new-key"

old_cipher = Fernet(old_key)
new_cipher = Fernet(new_key)

# For each organization with KMS configured
for org in organizations_with_kms:
    # Decrypt with old key
    old_encrypted = org.kms_credentials_encrypted.encode()
    decrypted = old_cipher.decrypt(old_encrypted)
    
    # Re-encrypt with new key
    new_encrypted = new_cipher.encrypt(decrypted)
    
    # Update database
    org.kms_credentials_encrypted = new_encrypted.decode()
    db.commit()
```

**Step 3: Update environment variable**
```bash
export KMS_ENCRYPTION_KEY="your-new-key"
```

**Step 4: Restart application**

---

## Backup and Recovery

### Backup Encryption Key

**Encrypted Backup:**
```bash
# Encrypt key with GPG
echo "$KMS_ENCRYPTION_KEY" | gpg --encrypt --recipient admin@example.com > kms_key.gpg

# Store securely (e.g., AWS S3 with encryption)
aws s3 cp kms_key.gpg s3://secure-backup-bucket/keys/kms_key.gpg --sse
```

**Recovery:**
```bash
# Download and decrypt
aws s3 cp s3://secure-backup-bucket/keys/kms_key.gpg .
gpg --decrypt kms_key.gpg

# Set in environment
export KMS_ENCRYPTION_KEY="recovered-key"
```

### Disaster Recovery Plan

1. **Encryption key is lost:** All KMS credentials are unrecoverable. Organizations must reconfigure KMS.
2. **Database is lost:** Restore from backup. If encryption key is same, KMS configs are intact.
3. **Both lost:** Organizations must reconfigure KMS from scratch.

**Prevention:**
- Backup encryption key separately from database
- Use secret management system with backups
- Document recovery procedures
- Test recovery process quarterly

---

## Compliance and Auditing

### Audit Logging

Log all KMS encryption key usage:

```python
import logging

logger = logging.getLogger(__name__)

def audit_log_kms_operation(operation: str, org_id: str, success: bool):
    """Log KMS operations for compliance."""
    logger.info(
        f"KMS_OP: {operation} | ORG: {org_id} | "
        f"SUCCESS: {success} | TIMESTAMP: {datetime.now(timezone.utc)}"
    )
```

### Access Control

Restrict who can view `KMS_ENCRYPTION_KEY`:

1. **Environment:** Only platform administrators
2. **CI/CD:** Use secret injection, never log in plaintext
3. **Containers:** Use secrets, not environment variables if possible
4. **Source Control:** Never commit `.env` files

### Compliance Checklist

- [ ] Encryption key stored in secret management system
- [ ] Encryption key backed up securely
- [ ] Access to encryption key is logged
- [ ] Key rotation schedule established (e.g., quarterly)
- [ ] Disaster recovery plan documented and tested
- [ ] Audit logs retained per compliance requirements
- [ ] Environment variables reviewed in security audit

---

## Quick Start

**For Development:**
```bash
# Generate key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > .kms_key

# Set in environment
export KMS_ENCRYPTION_KEY=$(cat .kms_key)

# Run application
python -m uvicorn main:app --reload
```

**For Production:**
1. Use secret management system (AWS Secrets Manager, etc.)
2. Never use the same key as development
3. Enable audit logging
4. Set up monitoring for unauthorized access
5. Document key location and access procedures

---

## References

- [Fernet (symmetric encryption)](https://cryptography.io/en/latest/fernet/)
- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/)
- [HashiCorp Vault](https://www.vaultproject.io/)
- [Google Secret Manager](https://cloud.google.com/secret-manager)
- [KMS Configuration API Documentation](KMS_CONFIGURATION_API.md)
