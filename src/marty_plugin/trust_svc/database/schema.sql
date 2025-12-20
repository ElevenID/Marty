-- Trust Services Database Schema
-- PostgreSQL schema for centralized trust management in Marty

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create trust_svc schema
CREATE SCHEMA IF NOT EXISTS trust_svc;
SET search_path = trust_svc;

-- Trust anchors (CSCA certificates)
CREATE TABLE trust_anchors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country_code CHAR(3) NOT NULL,
    certificate_hash VARCHAR(64) UNIQUE NOT NULL,
    certificate_data BYTEA NOT NULL,
    subject_dn TEXT NOT NULL,
    issuer_dn TEXT NOT NULL,
    serial_number TEXT NOT NULL,
    valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
    valid_to TIMESTAMP WITH TIME ZONE NOT NULL,
    key_usage TEXT[],
    signature_algorithm TEXT,
    public_key_algorithm TEXT,
    immutable_flag BOOLEAN DEFAULT false,
    trust_level VARCHAR(20) DEFAULT 'standard', -- standard, high, emergency
    status VARCHAR(20) DEFAULT 'active', -- active, inactive, revoked
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT valid_trust_level CHECK (trust_level IN ('standard', 'high', 'emergency')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'inactive', 'revoked'))
);

-- DSC metadata and revocation status
CREATE TABLE dsc_certificates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country_code CHAR(3) NOT NULL,
    certificate_hash VARCHAR(64) UNIQUE NOT NULL,
    certificate_data BYTEA NOT NULL,
    issuer_trust_anchor_id UUID REFERENCES trust_anchors(id),
    subject_dn TEXT NOT NULL,
    issuer_dn TEXT NOT NULL,
    serial_number TEXT NOT NULL,
    valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
    valid_to TIMESTAMP WITH TIME ZONE NOT NULL,
    key_usage TEXT[],
    signature_algorithm TEXT,
    public_key_algorithm TEXT,

    -- Revocation status tracking
    revocation_status VARCHAR(20) DEFAULT 'unknown', -- good, bad, unknown
    revocation_checked_at TIMESTAMP WITH TIME ZONE,
    revocation_reason INTEGER, -- RFC 5280 reason codes
    revocation_date TIMESTAMP WITH TIME ZONE,
    crl_source TEXT,
    ocsp_source TEXT,
    ocsp_checked_at TIMESTAMP WITH TIME ZONE,

    -- Trust chain information
    chain_valid BOOLEAN,
    chain_validated_at TIMESTAMP WITH TIME ZONE,
    trust_path TEXT[], -- Array of certificate hashes in chain

    immutable_flag BOOLEAN DEFAULT false,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT valid_revocation_status CHECK (revocation_status IN ('good', 'bad', 'unknown')),
    CONSTRAINT valid_dsc_status CHECK (status IN ('active', 'inactive', 'revoked'))
);

-- CRL metadata and caching
CREATE TABLE crl_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer_dn TEXT NOT NULL,
    issuer_certificate_hash VARCHAR(64),
    crl_url TEXT,
    crl_number BIGINT,
    this_update TIMESTAMP WITH TIME ZONE NOT NULL,
    next_update TIMESTAMP WITH TIME ZONE NOT NULL,
    crl_data BYTEA NOT NULL,
    crl_hash VARCHAR(64) NOT NULL,
    signature_valid BOOLEAN DEFAULT false,
    revoked_count INTEGER DEFAULT 0,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT valid_crl_status CHECK (status IN ('active', 'expired', 'invalid'))
);

-- Revoked certificates from CRLs
CREATE TABLE revoked_certificates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crl_id UUID REFERENCES crl_cache(id) ON DELETE CASCADE,
    serial_number TEXT NOT NULL,
    revocation_date TIMESTAMP WITH TIME ZONE NOT NULL,
    reason_code INTEGER, -- RFC 5280 reason codes
    certificate_hash VARCHAR(64), -- if we can match to DSC
    dsc_id UUID REFERENCES dsc_certificates(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(crl_id, serial_number)
);

-- Master list metadata and tracking
CREATE TABLE master_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country_code CHAR(3),
    sequence_number INTEGER,
    version TEXT,
    issue_date TIMESTAMP WITH TIME ZONE NOT NULL,
    next_update TIMESTAMP WITH TIME ZONE,
    certificate_count INTEGER NOT NULL,
    data_hash VARCHAR(64) NOT NULL,
    raw_data BYTEA NOT NULL,
    signature_valid BOOLEAN DEFAULT false,
    signer_certificate_hash VARCHAR(64),
    immutable_flag BOOLEAN DEFAULT false,
    status VARCHAR(20) DEFAULT 'active',
    source_type VARCHAR(20) DEFAULT 'manual', -- manual, synthetic, pkd_sync
    source_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT valid_ml_status CHECK (status IN ('active', 'superseded', 'invalid')),
    CONSTRAINT valid_source_type CHECK (source_type IN ('manual', 'synthetic', 'pkd_sync'))
);

-- Trust snapshots (immutable views with KMS signatures)
CREATE TABLE trust_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    snapshot_hash VARCHAR(64) NOT NULL,
    signature TEXT, -- KMS signed attestation
    signature_algorithm TEXT DEFAULT 'RSA-SHA256',
    trust_anchor_count INTEGER NOT NULL,
    dsc_count INTEGER NOT NULL,
    revoked_count INTEGER NOT NULL,
    crl_count INTEGER NOT NULL,
    metadata JSONB,
    immutable_flag BOOLEAN DEFAULT true,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(snapshot_hash)
);

-- Job execution tracking
CREATE TABLE job_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name VARCHAR(100) NOT NULL,
    job_type VARCHAR(50) NOT NULL, -- masterlist_sync, crl_refresh, ocsp_check, snapshot_create
    status VARCHAR(20) NOT NULL, -- running, completed, failed
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    records_processed INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    metadata JSONB,

    CONSTRAINT valid_job_status CHECK (status IN ('running', 'completed', 'failed'))
);

-- PKD ingestion configuration
CREATE TABLE pkd_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    country_code CHAR(3),
    source_type VARCHAR(20) NOT NULL, -- icao_pkd, national_pki, manual
    base_url TEXT,
    master_list_url TEXT,
    crl_url TEXT,
    sync_enabled BOOLEAN DEFAULT true,
    sync_interval_hours INTEGER DEFAULT 24,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    last_sync_status VARCHAR(20),
    authentication_config JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT valid_source_type CHECK (source_type IN ('icao_pkd', 'national_pki', 'manual'))
);

-- Indexes for performance
CREATE INDEX idx_trust_anchors_country ON trust_anchors(country_code);
CREATE INDEX idx_trust_anchors_hash ON trust_anchors(certificate_hash);
CREATE INDEX idx_trust_anchors_valid_period ON trust_anchors(valid_from, valid_to);
CREATE INDEX idx_trust_anchors_status ON trust_anchors(status);

CREATE INDEX idx_dsc_country ON dsc_certificates(country_code);
CREATE INDEX idx_dsc_hash ON dsc_certificates(certificate_hash);
CREATE INDEX idx_dsc_serial ON dsc_certificates(serial_number);
CREATE INDEX idx_dsc_revocation_status ON dsc_certificates(revocation_status);
CREATE INDEX idx_dsc_issuer ON dsc_certificates(issuer_trust_anchor_id);
CREATE INDEX idx_dsc_valid_period ON dsc_certificates(valid_from, valid_to);

CREATE INDEX idx_revoked_serial ON revoked_certificates(serial_number);
CREATE INDEX idx_revoked_hash ON revoked_certificates(certificate_hash);
CREATE INDEX idx_revoked_crl ON revoked_certificates(crl_id);

CREATE INDEX idx_crl_issuer ON crl_cache(issuer_dn);
CREATE INDEX idx_crl_hash ON crl_cache(issuer_certificate_hash);
CREATE INDEX idx_crl_validity ON crl_cache(this_update, next_update);
CREATE INDEX idx_crl_status ON crl_cache(status);

CREATE INDEX idx_snapshots_time ON trust_snapshots(snapshot_time);
CREATE INDEX idx_snapshots_hash ON trust_snapshots(snapshot_hash);

CREATE INDEX idx_jobs_name_time ON job_executions(job_name, started_at);
CREATE INDEX idx_jobs_status ON job_executions(status);

CREATE INDEX idx_pkd_sources_country ON pkd_sources(country_code);
CREATE INDEX idx_pkd_sources_type ON pkd_sources(source_type);

-- Functions for trust validation
CREATE OR REPLACE FUNCTION check_certificate_chain(dsc_hash VARCHAR(64))
RETURNS TABLE(
    valid BOOLEAN,
    trust_anchor_id UUID,
    chain_length INTEGER,
    validation_errors TEXT[]
) AS $$
DECLARE
    dsc_record dsc_certificates%ROWTYPE;
    ta_record trust_anchors%ROWTYPE;
BEGIN
    -- Get DSC record
    SELECT * INTO dsc_record FROM dsc_certificates WHERE certificate_hash = dsc_hash;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, NULL::UUID, 0, ARRAY['DSC not found'];
        RETURN;
    END IF;

    -- Get trust anchor
    SELECT * INTO ta_record FROM trust_anchors WHERE id = dsc_record.issuer_trust_anchor_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, NULL::UUID, 1, ARRAY['Trust anchor not found'];
        RETURN;
    END IF;

    -- Basic chain validation (extend with cryptographic verification)
    RETURN QUERY SELECT
        true,
        ta_record.id,
        2,
        ARRAY[]::TEXT[];
END;
$$ LANGUAGE plpgsql;

-- Function to check if certificate is revoked
CREATE OR REPLACE FUNCTION is_certificate_revoked(cert_serial TEXT, issuer_dn TEXT)
RETURNS TABLE(
    is_revoked BOOLEAN,
    revocation_date TIMESTAMP WITH TIME ZONE,
    reason_code INTEGER,
    source TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        true as is_revoked,
        rc.revocation_date,
        rc.reason_code,
        'CRL' as source
    FROM revoked_certificates rc
    JOIN crl_cache cc ON rc.crl_id = cc.id
    WHERE rc.serial_number = cert_serial
    AND cc.issuer_dn = issuer_dn
    AND cc.status = 'active'
    AND NOW() BETWEEN cc.this_update AND cc.next_update
    LIMIT 1;

    -- If not found in CRL, return not revoked
    IF NOT FOUND THEN
        RETURN QUERY SELECT false, NULL::TIMESTAMP WITH TIME ZONE, NULL::INTEGER, NULL::TEXT;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updating timestamps
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_trust_anchors_modtime
    BEFORE UPDATE ON trust_anchors
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

CREATE TRIGGER update_dsc_certificates_modtime
    BEFORE UPDATE ON dsc_certificates
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

CREATE TRIGGER update_pkd_sources_modtime
    BEFORE UPDATE ON pkd_sources
    FOR EACH ROW EXECUTE FUNCTION update_modified_column();

-- Views for common queries
CREATE VIEW current_trust_anchors AS
SELECT
    ta.*,
    COUNT(dsc.id) as dsc_count
FROM trust_anchors ta
LEFT JOIN dsc_certificates dsc ON ta.id = dsc.issuer_trust_anchor_id
WHERE ta.status = 'active'
AND NOW() BETWEEN ta.valid_from AND ta.valid_to
GROUP BY ta.id;

CREATE VIEW certificate_status_summary AS
SELECT
    country_code,
    COUNT(*) as total_certificates,
    COUNT(CASE WHEN revocation_status = 'good' THEN 1 END) as good_certificates,
    COUNT(CASE WHEN revocation_status = 'bad' THEN 1 END) as revoked_certificates,
    COUNT(CASE WHEN revocation_status = 'unknown' THEN 1 END) as unknown_certificates,
    COUNT(CASE WHEN valid_to < NOW() THEN 1 END) as expired_certificates
FROM dsc_certificates
WHERE status = 'active'
GROUP BY country_code;

-- Grant permissions for trust service user
-- CREATE USER trust_service WITH PASSWORD 'change_me_in_production';
-- GRANT USAGE ON SCHEMA trust_svc TO trust_service;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA trust_svc TO trust_service;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA trust_svc TO trust_service;

-- Comment the table structure
COMMENT ON TABLE trust_anchors IS 'CSCA certificates serving as trust anchors';
COMMENT ON TABLE dsc_certificates IS 'Document Signer Certificates with revocation status';
COMMENT ON TABLE crl_cache IS 'Certificate Revocation Lists cache';
COMMENT ON TABLE revoked_certificates IS 'Individual revoked certificates from CRLs';
COMMENT ON TABLE master_lists IS 'Master list metadata and raw data';
COMMENT ON TABLE trust_snapshots IS 'Immutable trust snapshots with signatures';
COMMENT ON TABLE job_executions IS 'Trust service job execution tracking';
COMMENT ON TABLE pkd_sources IS 'PKD synchronization source configuration';

COMMENT ON COLUMN trust_anchors.immutable_flag IS 'Prevents modification of critical trust anchors';
COMMENT ON COLUMN dsc_certificates.revocation_status IS 'Current revocation status: good, bad, unknown';
COMMENT ON COLUMN trust_snapshots.signature IS 'KMS signed attestation of snapshot integrity';
COMMENT ON COLUMN master_lists.source_type IS 'Source of master list: manual, synthetic, pkd_sync';
