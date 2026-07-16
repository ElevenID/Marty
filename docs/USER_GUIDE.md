# Marty Educational Quick Integration Guide

**Learning ICAO standards through practical code examples**

> Review the security and support policies before operating Marty in a production environment.

## Educational Quick Start

This guide demonstrates ICAO standard implementations through code examples. This is a learning project - never use in production.

## Quick Start

```bash
# Clone and start
git clone https://github.com/ElevenID/Marty.git
cd Marty
make setup
docker-compose up --build

# Verify: Open http://localhost:8080
```

## Essential Integration Examples

### Create an Electronic Passport

```python
import grpc
from src.proto import passport_engine_pb2_grpc, passport_engine_pb2

# Connect to passport service
channel = grpc.insecure_channel('localhost:8084')
client = passport_engine_pb2_grpc.PassportEngineStub(channel)

# Create eMRTD
request = passport_engine_pb2.PersonalizationRequest(
    mrz_data="P<UTOBAKER<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<1234567890USA8001019M2501017<<<<<<<<<<<<<<02",
    photo_data=photo_bytes
)

response = client.PersonalizePassport(request)
print(f"Passport created: {response.success}")
```

### Verify a Document

```python
from src.proto import inspection_system_pb2_grpc, inspection_system_pb2

# Connect to verification service
channel = grpc.insecure_channel('localhost:8083')
client = inspection_system_pb2_grpc.InspectionSystemStub(channel)

# Verify document
request = inspection_system_pb2.VerificationRequest(
    document_data=document_bytes,
    verification_type="FULL_CHIP_VERIFICATION"
)

response = client.VerifyDocument(request)
print(f"Valid: {response.is_valid}")
```

### Create Mobile Driving License

```python
from src.proto import mdl_engine_pb2_grpc, mdl_engine_pb2

# Connect to mDL service
channel = grpc.insecure_channel('localhost:8085')
client = mdl_engine_pb2_grpc.MdlEngineStub(channel)

# Create mDL
request = mdl_engine_pb2.MdlCreationRequest(
    driver_data={
        "family_name": "Smith",
        "given_name": "Jane",
        "birth_date": "1990-01-01",
        "license_number": "DL123456789"
    },
    portrait_image=portrait_bytes
)

response = client.CreateMdl(request)
print(f"mDL created: {response.mdl_id}")
```

## Service Endpoints

| Service | Port | Purpose |
|---------|------|---------|
| Trust Anchor | 8080 | Certificate management |
| CSCA Service | 8081 | Certificate authority |
| Document Signer | 8082 | Document signing |
| Inspection System | 8083 | Document verification |
| Passport Engine | 8084 | eMRTD creation |
| MDL Engine | 8085 | Mobile license creation |
| DTC Engine | 8086 | Digital travel credentials |
| PKD Service | 8087 | Public key directory |

## REST API (Alternative)

For non-gRPC integrations, use REST endpoints:

```bash
# Create passport
curl -X POST http://localhost:8080/api/v1/passport/personalize \
  -H "Content-Type: application/json" \
  -d '{"mrz_data": "P<USA...", "photo_data": "base64..."}'

# Verify document  
curl -X POST http://localhost:8080/api/v1/verify/passport \
  -H "Content-Type: application/json" \
  -d '{"document_data": "base64..."}'
```

## Error Handling

```python
import grpc
from grpc import StatusCode

try:
    response = client.VerifyDocument(request)
    return response
except grpc.RpcError as e:
    if e.code() == StatusCode.INVALID_ARGUMENT:
        print("Invalid document format")
    elif e.code() == StatusCode.NOT_FOUND:
        print("Certificate not found")
    else:
        print(f"Error: {e.details()}")
```

## Next Steps

- 📋 **Business Overview**: See [BUSINESS_OVERVIEW.md](BUSINESS_OVERVIEW.md) for executive summary
- 🛠️ **Developer Guide**: See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) for technical deep dive
- 📄 **API Reference**: Complete OpenAPI spec at [api/openapi.yaml](api/openapi.yaml)
- 🧪 **Examples**: More integration patterns in `tests/integration/`
