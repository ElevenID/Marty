-- Sample data for trust services development and testing

SET search_path = trust_svc;

-- Insert sample trust anchors (CSCA certificates)
INSERT INTO trust_anchors (
    country_code, certificate_hash, certificate_data, subject_dn, issuer_dn,
    serial_number, valid_from, valid_to, key_usage, signature_algorithm,
    public_key_algorithm, trust_level, status
) VALUES
(
    'DEV',
    sha256('DEV_CSCA_001'::bytea)::text,
    'DEV_CSCA_CERT_DATA_001'::bytea,
    'CN=CSCA-DEV,C=DEV,O=Development Authority',
    'CN=CSCA-DEV,C=DEV,O=Development Authority',
    '1001',
    NOW() - INTERVAL '1 year',
    NOW() + INTERVAL '4 years',
    ARRAY['keyCertSign', 'cRLSign'],
    'sha256WithRSAEncryption',
    'RSA',
    'standard',
    'active'
),
(
    'TST',
    sha256('TST_CSCA_001'::bytea)::text,
    'TST_CSCA_CERT_DATA_001'::bytea,
    'CN=CSCA-TST,C=TST,O=Test Authority',
    'CN=CSCA-TST,C=TST,O=Test Authority',
    '2001',
    NOW() - INTERVAL '6 months',
    NOW() + INTERVAL '3 years',
    ARRAY['keyCertSign', 'cRLSign'],
    'sha256WithRSAEncryption',
    'RSA',
    'high',
    'active'
),
(
    'USA',
    sha256('USA_CSCA_001'::bytea)::text,
    'USA_CSCA_CERT_DATA_001'::bytea,
    'CN=CSCA-USA,C=US,O=U.S. Department of State',
    'CN=CSCA-USA,C=US,O=U.S. Department of State',
    '3001',
    NOW() - INTERVAL '2 years',
    NOW() + INTERVAL '8 years',
    ARRAY['keyCertSign', 'cRLSign'],
    'sha256WithRSAEncryption',
    'RSA',
    'standard',
    'active'
);

-- Insert sample DSC certificates
WITH trust_anchor_ids AS (
    SELECT id, country_code FROM trust_anchors WHERE country_code IN ('DEV', 'TST', 'USA')
)
INSERT INTO dsc_certificates (
    country_code, certificate_hash, certificate_data, issuer_trust_anchor_id,
    subject_dn, issuer_dn, serial_number, valid_from, valid_to,
    key_usage, signature_algorithm, public_key_algorithm, revocation_status,
    revocation_checked_at, chain_valid, chain_validated_at, status
)
SELECT
    ta.country_code,
    sha256(('DSC_' || ta.country_code || '_' || series.num)::bytea)::text,
    ('DSC_CERT_DATA_' || ta.country_code || '_' || series.num)::bytea,
    ta.id,
    'CN=DSC-' || ta.country_code || '-' || series.num || ',C=' || ta.country_code || ',O=Document Signer',
    'CN=CSCA-' || ta.country_code || ',C=' || ta.country_code,
    (4000 + series.num)::text,
    NOW() - INTERVAL '1 year',
    NOW() + INTERVAL '2 years',
    ARRAY['digitalSignature'],
    'sha256WithRSAEncryption',
    'RSA',
    CASE
        WHEN series.num % 10 = 0 THEN 'bad'  -- 10% revoked
        WHEN series.num % 5 = 0 THEN 'unknown'  -- 10% unknown
        ELSE 'good'  -- 80% good
    END,
    NOW() - INTERVAL '1 hour',
    true,
    NOW() - INTERVAL '1 hour',
    'active'
FROM trust_anchor_ids ta
CROSS JOIN generate_series(1, 25) as series(num);

-- Insert sample CRL cache entries
WITH trust_anchor_data AS (
    SELECT id, country_code,
           'CN=CSCA-' || country_code || ',C=' || country_code || ',O=' || country_code || ' Authority' as issuer_dn
    FROM trust_anchors WHERE country_code IN ('DEV', 'TST', 'USA')
)
INSERT INTO crl_cache (
    issuer_dn, issuer_certificate_hash, crl_url, crl_number,
    this_update, next_update, crl_data, crl_hash, signature_valid,
    revoked_count, status
)
SELECT
    ta.issuer_dn,
    sha256(('CSCA_' || ta.country_code)::bytea)::text,
    'https://crl.example.com/' || ta.country_code || '/current.crl',
    1001 + (ta.id::text::int % 1000),
    NOW() - INTERVAL '6 hours',
    NOW() + INTERVAL '7 days',
    ('CRL_DATA_' || ta.country_code)::bytea,
    sha256(('CRL_' || ta.country_code)::bytea)::text,
    true,
    CASE ta.country_code
        WHEN 'DEV' THEN 3
        WHEN 'TST' THEN 2
        WHEN 'USA' THEN 1
        ELSE 0
    END,
    'active'
FROM trust_anchor_data ta;

-- Insert revoked certificates (matching the DSCs marked as 'bad')
WITH revoked_dscs AS (
    SELECT dsc.serial_number, dsc.certificate_hash, dsc.country_code
    FROM dsc_certificates dsc
    WHERE dsc.revocation_status = 'bad'
),
crl_data AS (
    SELECT cc.id as crl_id, cc.issuer_dn
    FROM crl_cache cc
    WHERE cc.status = 'active'
)
INSERT INTO revoked_certificates (
    crl_id, serial_number, revocation_date, reason_code, certificate_hash
)
SELECT
    cd.crl_id,
    rd.serial_number,
    NOW() - INTERVAL '30 days',
    1, -- Key compromise
    rd.certificate_hash
FROM revoked_dscs rd
JOIN crl_data cd ON cd.issuer_dn LIKE '%' || rd.country_code || '%';

-- Insert sample master lists
INSERT INTO master_lists (
    country_code, sequence_number, version, issue_date, next_update,
    certificate_count, data_hash, raw_data, signature_valid,
    signer_certificate_hash, source_type, source_url
) VALUES
(
    'DEV',
    1,
    '1.0.0',
    NOW() - INTERVAL '1 day',
    NOW() + INTERVAL '30 days',
    26, -- 1 CSCA + 25 DSCs
    sha256('DEV_MASTER_LIST_001'::bytea)::text,
    'DEV_MASTER_LIST_RAW_DATA'::bytea,
    true,
    sha256('DEV_CSCA_001'::bytea)::text,
    'synthetic',
    'file:///data/synthetic/dev_master_list.ml'
),
(
    'TST',
    1,
    '1.0.0',
    NOW() - INTERVAL '2 hours',
    NOW() + INTERVAL '7 days',
    26,
    sha256('TST_MASTER_LIST_001'::bytea)::text,
    'TST_MASTER_LIST_RAW_DATA'::bytea,
    true,
    sha256('TST_CSCA_001'::bytea)::text,
    'synthetic',
    'file:///data/synthetic/tst_master_list.ml'
);

-- Insert sample PKD sources
INSERT INTO pkd_sources (
    name, country_code, source_type, base_url, master_list_url,
    sync_enabled, sync_interval_hours, last_sync_status
) VALUES
(
    'ICAO PKD Test Environment',
    NULL,
    'icao_pkd',
    'https://test.pkd.icao.int',
    'https://test.pkd.icao.int/masterlist',
    true,
    24,
    'completed'
),
(
    'DEV Synthetic Source',
    'DEV',
    'manual',
    'file:///data/synthetic/',
    'file:///data/synthetic/dev_master_list.ml',
    true,
    1,
    'completed'
),
(
    'USA National PKI',
    'USA',
    'national_pki',
    'https://pki.state.gov',
    'https://pki.state.gov/masterlist',
    false,
    168, -- Weekly
    null
);

-- Insert sample job executions
INSERT INTO job_executions (
    job_name, job_type, status, started_at, completed_at,
    duration_seconds, records_processed, errors_count, metadata
) VALUES
(
    'daily_masterlist_sync',
    'masterlist_sync',
    'completed',
    NOW() - INTERVAL '2 hours',
    NOW() - INTERVAL '1 hour 30 minutes',
    1800, -- 30 minutes
    2, -- 2 master lists processed
    0,
    '{"countries_processed": ["DEV", "TST"], "certificates_updated": 52}'::jsonb
),
(
    'crl_refresh_all',
    'crl_refresh',
    'completed',
    NOW() - INTERVAL '6 hours',
    NOW() - INTERVAL '5 hours 50 minutes',
    600, -- 10 minutes
    3, -- 3 CRLs processed
    0,
    '{"crls_fetched": 3, "revoked_certificates_found": 6}'::jsonb
),
(
    'trust_snapshot_create',
    'snapshot_create',
    'completed',
    NOW() - INTERVAL '1 hour',
    NOW() - INTERVAL '58 minutes',
    120, -- 2 minutes
    1, -- 1 snapshot created
    0,
    '{"snapshot_id": "' || gen_random_uuid() || '", "signature_created": true}'::jsonb
);

-- Create initial trust snapshot
INSERT INTO trust_snapshots (
    snapshot_hash, signature, trust_anchor_count, dsc_count,
    revoked_count, crl_count, metadata, expires_at
)
SELECT
    sha256(('SNAPSHOT_' || NOW()::text)::bytea)::text,
    'MOCK_KMS_SIGNATURE_' || extract(epoch from NOW())::text,
    (SELECT COUNT(*) FROM trust_anchors WHERE status = 'active'),
    (SELECT COUNT(*) FROM dsc_certificates WHERE status = 'active'),
    (SELECT COUNT(*) FROM revoked_certificates),
    (SELECT COUNT(*) FROM crl_cache WHERE status = 'active'),
    jsonb_build_object(
        'created_by', 'initial_data_load',
        'trust_anchors_by_country', (
            SELECT jsonb_object_agg(country_code, count)
            FROM (
                SELECT country_code, COUNT(*) as count
                FROM trust_anchors
                WHERE status = 'active'
                GROUP BY country_code
            ) t
        ),
        'dsc_status_distribution', (
            SELECT jsonb_object_agg(revocation_status, count)
            FROM (
                SELECT revocation_status, COUNT(*) as count
                FROM dsc_certificates
                WHERE status = 'active'
                GROUP BY revocation_status
            ) t
        )
    ),
    NOW() + INTERVAL '7 days';

-- Update last sync times for PKD sources
UPDATE pkd_sources
SET last_sync_at = NOW() - INTERVAL '1 hour'
WHERE name IN ('ICAO PKD Test Environment', 'DEV Synthetic Source');

COMMIT;
