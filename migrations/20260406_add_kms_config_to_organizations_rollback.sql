-- Rollback Migration: Remove KMS Configuration Fields from Organizations
-- Date: 2026-04-06
-- Description: Rollback script to remove KMS configuration fields

-- Drop index
DROP INDEX IF EXISTS idx_organizations_kms_provider;

-- Drop columns
ALTER TABLE organizations 
DROP COLUMN IF EXISTS kms_credentials_encrypted;

ALTER TABLE organizations 
DROP COLUMN IF EXISTS kms_config;

ALTER TABLE organizations 
DROP COLUMN IF EXISTS kms_provider;

-- Verify rollback
-- Run this query to confirm columns are removed:
-- SELECT column_name 
-- FROM information_schema.columns 
-- WHERE table_name = 'organizations' 
-- AND column_name IN ('kms_provider', 'kms_config', 'kms_credentials_encrypted');
