# Trust Services (trust-svc)

A comprehensive microservice for managing trust relationships, certificate validation, and revocation checking in the Marty passport verification system.

## Overview

The Trust Services microservice provides centralized management of:

- **Trust Anchors**: Country Signing Certificate Authorities (CSCAs)
- **Document Signing Certificates (DSCs)**: For passport validation
- **Certificate Revocation Lists (CRLs)**: Real-time revocation status
- **Master Lists**: Official lists of trusted certificates by country
- **Trust Snapshots**: Immutable, signed snapshots of trust state

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   PKD Sources   │───▶│   Trust Service  │───▶│   PostgreSQL    │
│  (ICAO, LDAP)   │    │                  │    │   (trust_svc)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   Prometheus     │
                       │    Metrics       │
                       └──────────────────┘
```

### Key Components

- **DatabaseManager**: Async PostgreSQL operations with SQLAlchemy
- **RevocationProcessor**: CRL/OCSP validation and caching
- **TrustMetrics**: Prometheus monitoring and alerting
- **REST API**: FastAPI endpoints for trust queries and admin
- **DevJobRunner**: Development utilities and synthetic data

## Database Schema

The trust_svc schema includes:

- `trust_anchors`: Root CA certificates by country
- `dsc_certificates`: Document signing certificates
- `crl_cache`: Cached revocation lists with status
- `revoked_certificates`: Individual revocation records
- `master_lists`: Official certificate lists
- `trust_snapshots`: Signed immutable trust states
- `job_executions`: Background job tracking
- `pkd_sources`: External data source configurations

## API Endpoints

### Trust Queries

- `GET /api/v1/trust/anchor/{country}` - Get trust anchor for country
- `GET /api/v1/trust/dsc/{thumbprint}` - Check DSC trust status
- `GET /api/v1/trust/revocation/{serial}` - Get revocation status
- `GET /api/v1/trust/snapshot/latest` - Latest trust snapshot

### Administration

- `POST /api/v1/admin/refresh-crl` - Force CRL refresh
- `POST /api/v1/admin/snapshot` - Create new trust snapshot
- `GET /api/v1/admin/status` - Service health status
- `GET /api/v1/admin/stats` - Trust statistics

### Development

- `POST /api/v1/dev/load-synthetic` - Load synthetic test data
- `GET /api/v1/dev/stats` - Development statistics

## Metrics

Prometheus metrics include:

```
# Certificate counts by country and status
trust_dsc_total{country="US", status="valid"} 1205

# Master list freshness
trust_master_list_age_seconds{country="US"} 3600

# CRL freshness and revocation counts
trust_crl_age_seconds{issuer="US-CSCA"} 1800
trust_crl_revoked_count{issuer="US-CSCA"} 42

# Job execution tracking
trust_job_execution_total{job_name="refresh_crl", status="completed"} 156
trust_job_last_success_timestamp{job_name="refresh_crl"} 1703875200

# Snapshot metrics
trust_snapshot_count 25
trust_snapshot_age_seconds 7200
```

## Configuration

Environment variables:

```bash
# Database
TRUST_DB_HOST=localhost
TRUST_DB_PORT=5432
TRUST_DB_NAME=marty
TRUST_DB_USER=trust_svc
TRUST_DB_PASSWORD=secure_password

# KMS (for snapshot signing)
TRUST_KMS_KEY_ID=arn:aws:kms:us-east-1:account:key/key-id
TRUST_KMS_REGION=us-east-1

# PKD Sources
TRUST_PKD_ICAO_URL=https://pkddownloadsg.icao.int
TRUST_PKD_LDAP_URL=ldap://icao.int:389
TRUST_PKD_REFRESH_INTERVAL=3600

# Service
TRUST_SERVICE_HOST=0.0.0.0
TRUST_SERVICE_PORT=8080
TRUST_SERVICE_LOG_LEVEL=INFO
```

## Development Setup

1. **Database Setup**:

   ```bash
   psql -h localhost -U postgres -d marty -f src/trust_svc/database/schema.sql
   psql -h localhost -U postgres -d marty -f src/trust_svc/database/sample_data.sql
   ```

2. **Install Dependencies**:

   ```bash
   pip install -e ".[trust-svc]"
   ```

3. **Run Development Job**:

   ```bash
   python -m src.trust_svc.dev_job --count 1000 --format table
   ```

4. **Start Service**:

   ```bash
   uvicorn src.trust_svc.api:app --host 0.0.0.0 --port 8080 --reload
   ```

## Docker Deployment

```bash
# Build image
docker build -f docker/trust-service.Dockerfile -t marty/trust-svc .

# Run with dependencies
docker-compose up trust-svc
```

## Monitoring

Import the Grafana dashboard from `grafana_dashboard.json` for comprehensive monitoring including:

- Service health and database connections
- Certificate counts by country and status
- Master list and CRL age tracking
- Trust snapshot status
- Job execution success rates
- API request metrics

## Security Considerations

- **Immutable Snapshots**: Trust snapshots are signed with KMS and cannot be modified
- **Audit Trail**: All changes tracked in job_executions table
- **Input Validation**: All API inputs validated with Pydantic models
- **Rate Limiting**: API endpoints include rate limiting (configure as needed)
- **TLS**: All external communications use TLS 1.2+

## Integration

The trust service integrates with:

- **PKD Service**: Fetches certificate data from ICAO and other sources
- **Verification Engines**: Provides trust status for passport validation
- **Monitoring**: Exports metrics to Prometheus/Grafana
- **Audit Systems**: Maintains immutable audit trail

## Performance

- **Async Operations**: Non-blocking database and HTTP operations
- **Connection Pooling**: Efficient database connection management
- **Caching**: CRL and certificate data cached with TTL
- **Indexing**: Optimized database indexes for common queries

## Testing

```bash
# Unit tests
pytest tests/trust_svc/

# Integration tests (requires running database)
pytest tests/integration/trust_svc/

# Load test with synthetic data
python -m src.trust_svc.dev_job --count 10000 --countries 50
```

## Troubleshooting

Common issues:

1. **Database Connection**: Check TRUST_DB_* environment variables
2. **KMS Access**: Verify AWS credentials and KMS key permissions
3. **CRL Fetching**: Check network connectivity to CRL endpoints
4. **Metrics**: Verify Prometheus scraping configuration

Check logs for detailed error information:

```bash
docker logs trust-svc
```
