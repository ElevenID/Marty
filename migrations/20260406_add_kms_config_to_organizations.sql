-- Migration: Add KMS Configuration Fields to Organizations
-- Date: 2026-04-06
-- Description: Add fields for storing customer KMS/HSM configuration for remote signing

-- Add KMS provider field
ALTER TABLE organizations 
ADD COLUMN IF NOT EXISTS kms_provider VARCHAR(50);

COMMENT ON COLUMN organizations.kms_provider IS 
'KMS provider: aws_kms, azure_key_vault, gcp_kms, hashicorp_vault, pkcs11_hsm';

-- Add KMS configuration field (JSONB for PostgreSQL, fallback to JSON for other databases)
ALTER TABLE organizations 
ADD COLUMN IF NOT EXISTS kms_config JSONB DEFAULT '{}' NOT NULL;

COMMENT ON COLUMN organizations.kms_config IS 
'KMS/HSM configuration (region, key_id, endpoint, algorithm, metadata)';

-- Add encrypted credentials field
ALTER TABLE organizations 
ADD COLUMN IF NOT EXISTS kms_credentials_encrypted TEXT;

COMMENT ON COLUMN organizations.kms_credentials_encrypted IS 
'Encrypted KMS credentials/API keys (Fernet encrypted)';

-- Create index on kms_provider for faster lookups
CREATE INDEX IF NOT EXISTS idx_organizations_kms_provider 
ON organizations(kms_provider) 
WHERE kms_provider IS NOT NULL;

-- Verify migration
-- Run this query to confirm all columns exist:
-- SELECT column_name, data_type, column_default, is_nullable 
-- FROM information_schema.columns 
-- WHERE table_name = 'organizations' 
-- AND column_name IN ('kms_provider', 'kms_config', 'kms_credentials_encrypted');
