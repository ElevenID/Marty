# IACA Certificate Store

This directory contains bundled IACA (Issuing Authority Certificate Authority) certificates for mDL trust chain verification per ISO 18013-5.

## Directory Structure

```
iaca/
├── manifest.json          # Certificate index and metadata
├── README.md              # This file
└── <jurisdiction>/        # Per-jurisdiction certificate directories
    └── iaca.pem           # IACA root certificate
```

## Trust Chain

For ISO 18013-5 mDL verification:

```
IACA (Root) → Document Signer (Intermediate) → mDoc (Document)
```

## Obtaining Official Certificates

### AAMVA Digital Trust Service (Production)

1. **Apply for AAMVA membership**: https://aamva.org/membership
   - Processing time: 2-4 weeks
   - Requires organizational membership

2. **Request DTS API access** through the AAMVA member portal

3. **Configure OAuth2 credentials** in your backend:
   ```env
   AAMVA_DTS_CLIENT_ID=your_client_id
   AAMVA_DTS_CLIENT_SECRET=your_client_secret
   AAMVA_DTS_TOKEN_URL=https://dts.aamva.org/oauth/token
   AAMVA_DTS_VICAL_URL=https://dts.aamva.org/vical
   ```

4. Use the `aamva-client` feature to sync certificates:
   ```rust
   use marty_verification::pkd::AamvaDtsClient;
   
   let client = AamvaDtsClient::from_env()?;
   let vical = client.fetch_vical().await?;
   ```

### Testing Certificates

For development, some states publish their IACA certificates publicly:

- **California**: DMV mDL testing program
- **Colorado**: DMV public key repository  
- **Utah**: DPS mDL documentation

Check each state's DMV/DPS website for publicly available test certificates.

## Certificate Format

Certificates should be in PEM format:

```pem
-----BEGIN CERTIFICATE-----
MIICyTCCA...
-----END CERTIFICATE-----
```

## Usage

### Rust

```rust
use marty_verification::trust_anchor::IacaRegistry;

let registry = IacaRegistry::from_directory("./data/certs/iaca/")?;
```

### Python

```python
import _marty_rs as marty

registry = marty.IacaRegistry.from_directory("./data/certs/iaca/")
result = marty.verify_mdl_x5chain(x5chain_pems, registry)
```

## Security Considerations

- Only trust certificates from verified sources
- Validate certificate signatures before adding to trust store
- Implement certificate revocation checking
- Keep certificates synchronized with AAMVA DTS
