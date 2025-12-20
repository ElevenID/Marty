-- Trust Services Database Migration Scripts
-- Migration 001: Initial schema creation

BEGIN;

-- Check if schema already exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'trust_svc') THEN
        RAISE NOTICE 'Creating trust_svc schema and tables...';
        -- The schema creation will be done by the main schema.sql file
    ELSE
        RAISE NOTICE 'trust_svc schema already exists, skipping creation';
    END IF;
END
$$;

COMMIT;
