# ICAO Public Key Directory (PKD) Service

This service implements a RESTful API that mimics the functionality of the ICAO PKD (Public Key Directory),
allowing for the management and distribution of certificates and other components needed for ePassport verification.

## Features

- **CSCA Master List Management**: Store, retrieve, and distribute CSCA certificates
- **Document Signer Certificate List**: Manage and distribute document signer certificates
- **CRL Management**: Certificate Revocation List handling
- **Deviation List**: Track and report deviations in the certificate ecosystem
- **External PKD Synchronization**: Synchronize with external ICAO PKD services

## API Structure

The API follows RESTful principles and provides both JSON responses and ASN.1 binary formats for compatibility
with existing ICAO PKD implementations. The main API endpoints are:

- `/v1/pkd/masterlist`: CSCA Master List operations
- `/v1/pkd/dsclist`: Document Signer Certificate list operations
- `/v1/pkd/crl`: Certificate Revocation List operations
- `/v1/pkd/deviationlist`: Deviation list operations
- `/v1/pkd/sync`: External PKD synchronization operations

## Authentication

The API uses API key authentication. Set the `PKD_API_KEY` environment variable to a secure value, and include this key in
requests via the `X-API-Key` header.

## Integration with Marty

This service integrates with the other Marty microservices:

- **CSCA Service**: Sources CSCA certificates
- **Document Signer Service**: Sources Document Signer certificates
- **Trust Anchor Service**: Integrates with trust management

## Deployment

The PKD service is containerized and can be deployed with the main Marty stack via Docker Compose.
Environment variables control the service configuration:

```bash
# Build and start the service
docker-compose up -d pkd-service

# View logs
docker-compose logs -f pkd-service
```

## Development

### Requirements

- Python 3.10+
- FastAPI
- ASN.1 libraries (asn1crypto, cryptography)

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
cd src/pkd-service
uvicorn app.main:app --reload
```

### API Documentation

When running, Swagger documentation is available at:

- <http://localhost:8000/docs> (development)
- <https://api.example.com/docs> (production)

## License

This service is part of the Marty project and follows the same licensing terms.
