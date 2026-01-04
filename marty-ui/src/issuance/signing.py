"""Credential signing service.

Handles cryptographic signing of verifiable credentials using
organization-specific keys from IssuerKeyConfig.
"""

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CredentialSigner:
    """Signs verifiable credentials using organization keys.
    
    Supports multiple credential formats:
    - vc+sd-jwt: SD-JWT Verifiable Credentials (default)
    - jwt_vc_json: JWT-encoded Verifiable Credentials
    - mso_mdoc: Mobile Security Object (ISO 18013-5)
    """

    def __init__(self, issuer_url: str = "http://localhost:8000"):
        self.issuer_url = issuer_url

    async def sign_credential(
        self,
        *,
        organization_id: str,
        credential_config_id: str,
        subject_id: str,
        claims: dict[str, Any],
        credential_format: str = "vc+sd-jwt",
        validity_days: int = 365,
    ) -> str:
        """Sign a verifiable credential.
        
        Args:
            organization_id: ID of the issuing organization
            credential_config_id: Credential type configuration ID
            subject_id: Subject (holder) identifier
            claims: Credential claims to include
            credential_format: Output format (vc+sd-jwt, jwt_vc_json, mso_mdoc)
            validity_days: Credential validity period
            
        Returns:
            Signed credential in the specified format
        """
        # Get the organization's signing key
        signing_key = await self._get_signing_key(organization_id)
        
        if credential_format == "vc+sd-jwt":
            return await self._sign_sd_jwt(
                signing_key=signing_key,
                subject_id=subject_id,
                claims=claims,
                credential_config_id=credential_config_id,
                validity_days=validity_days,
            )
        elif credential_format == "jwt_vc_json":
            return await self._sign_jwt_vc(
                signing_key=signing_key,
                subject_id=subject_id,
                claims=claims,
                credential_config_id=credential_config_id,
                validity_days=validity_days,
            )
        elif credential_format == "mso_mdoc":
            return await self._sign_mdoc(
                signing_key=signing_key,
                subject_id=subject_id,
                claims=claims,
                credential_config_id=credential_config_id,
                validity_days=validity_days,
            )
        else:
            raise ValueError(f"Unsupported credential format: {credential_format}")

    async def _get_signing_key(self, organization_id: str) -> dict:
        """Get the organization's active signing key.
        
        Args:
            organization_id: Organization ID
            
        Returns:
            Signing key configuration with JWK
        """
        # TODO: Look up from IssuerKeyConfig database
        # For now, return a demo key
        from trust.router import _org_trust_configs
        
        config = _org_trust_configs.get(organization_id)
        if config and config.signing_keys:
            # Get the first active key
            active_keys = [k for k in config.signing_keys if k.get("is_active", True)]
            if active_keys:
                return active_keys[0]
        
        # Fallback: generate ephemeral demo key
        logger.warning(
            f"No signing key found for organization {organization_id}, using demo key"
        )
        return await self._generate_demo_key()

    async def _generate_demo_key(self) -> dict:
        """Generate a demo signing key for testing."""
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.backends import default_backend
            
            # Generate P-256 key
            private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
            public_key = private_key.public_key()
            
            # Get raw key bytes
            public_numbers = public_key.public_numbers()
            private_numbers = private_key.private_numbers()
            
            # Convert to JWK
            def _b64url(data: bytes) -> str:
                return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
            
            x_bytes = public_numbers.x.to_bytes(32, byteorder="big")
            y_bytes = public_numbers.y.to_bytes(32, byteorder="big")
            d_bytes = private_numbers.private_value.to_bytes(32, byteorder="big")
            
            return {
                "key_id": "demo-key",
                "algorithm": "ES256",
                "private_key_jwk": {
                    "kty": "EC",
                    "crv": "P-256",
                    "x": _b64url(x_bytes),
                    "y": _b64url(y_bytes),
                    "d": _b64url(d_bytes),
                },
            }
        except ImportError:
            # Fallback if cryptography not available
            return {
                "key_id": "demo-key",
                "algorithm": "ES256",
                "private_key_jwk": None,
            }

    async def _sign_sd_jwt(
        self,
        signing_key: dict,
        subject_id: str,
        claims: dict[str, Any],
        credential_config_id: str,
        validity_days: int,
    ) -> str:
        """Sign a credential as SD-JWT.
        
        SD-JWT format: <issuer-jwt>~<disclosure1>~<disclosure2>~...
        """
        now = datetime.utcnow()
        exp = now + timedelta(days=validity_days)
        
        # Build JWT header
        header = {
            "alg": signing_key.get("algorithm", "ES256"),
            "typ": "vc+sd-jwt",
            "kid": signing_key.get("key_id", "default"),
        }
        
        # Generate selective disclosures
        disclosures = []
        sd_hashes = []
        
        for claim_name, claim_value in claims.items():
            if claim_value is not None:
                # Create disclosure: [salt, claim_name, claim_value]
                salt = secrets.token_urlsafe(16)
                disclosure = [salt, claim_name, claim_value]
                disclosure_json = json.dumps(disclosure, separators=(",", ":"))
                disclosure_b64 = base64.urlsafe_b64encode(
                    disclosure_json.encode()
                ).rstrip(b"=").decode()
                disclosures.append(disclosure_b64)
                
                # Hash for _sd array
                disclosure_hash = hashlib.sha256(disclosure_b64.encode()).digest()
                sd_hashes.append(
                    base64.urlsafe_b64encode(disclosure_hash).rstrip(b"=").decode()
                )
        
        # Build JWT payload
        payload = {
            "iss": self.issuer_url,
            "sub": subject_id,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "vct": credential_config_id,
            "_sd": sd_hashes,
            "_sd_alg": "sha-256",
            "cnf": {
                "jwk": {
                    # Placeholder for holder binding - would come from wallet
                    "kty": "EC",
                    "crv": "P-256",
                }
            },
        }
        
        # Encode and sign
        header_b64 = base64.urlsafe_b64encode(
            json.dumps(header, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        
        # Sign the JWT
        signature = await self._sign_jwt_payload(
            signing_key, f"{header_b64}.{payload_b64}"
        )
        
        # Combine: jwt~disclosure1~disclosure2~...
        jwt = f"{header_b64}.{payload_b64}.{signature}"
        sd_jwt = jwt + "~" + "~".join(disclosures) + "~"
        
        return sd_jwt

    async def _sign_jwt_vc(
        self,
        signing_key: dict,
        subject_id: str,
        claims: dict[str, Any],
        credential_config_id: str,
        validity_days: int,
    ) -> str:
        """Sign a credential as JWT VC (W3C format)."""
        now = datetime.utcnow()
        exp = now + timedelta(days=validity_days)
        
        header = {
            "alg": signing_key.get("algorithm", "ES256"),
            "typ": "JWT",
            "kid": signing_key.get("key_id", "default"),
        }
        
        payload = {
            "iss": self.issuer_url,
            "sub": subject_id,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "vc": {
                "@context": [
                    "https://www.w3.org/2018/credentials/v1",
                ],
                "type": ["VerifiableCredential", credential_config_id],
                "credentialSubject": {
                    "id": subject_id,
                    **claims,
                },
                "issuanceDate": now.isoformat() + "Z",
                "expirationDate": exp.isoformat() + "Z",
            },
        }
        
        header_b64 = base64.urlsafe_b64encode(
            json.dumps(header, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        
        signature = await self._sign_jwt_payload(
            signing_key, f"{header_b64}.{payload_b64}"
        )
        
        return f"{header_b64}.{payload_b64}.{signature}"

    async def _sign_mdoc(
        self,
        signing_key: dict,
        subject_id: str,
        claims: dict[str, Any],
        credential_config_id: str,
        validity_days: int,
    ) -> str:
        """Sign a credential as mDL/mDoc (ISO 18013-5).
        
        Note: Full mDoc implementation requires CBOR encoding.
        This is a simplified placeholder that returns base64-encoded structure.
        """
        now = datetime.utcnow()
        exp = now + timedelta(days=validity_days)
        
        # Simplified mDoc structure (real implementation needs CBOR)
        mdoc_data = {
            "version": "1.0",
            "docType": credential_config_id,
            "issuerSigned": {
                "issuerAuth": {
                    "alg": signing_key.get("algorithm", "ES256"),
                    "kid": signing_key.get("key_id", "default"),
                },
                "nameSpaces": {
                    credential_config_id: [
                        {"elementIdentifier": k, "elementValue": v}
                        for k, v in claims.items()
                        if v is not None
                    ],
                },
            },
            "deviceSigned": None,  # Would contain holder binding
        }
        
        # Placeholder: return JSON-encoded (real mDoc is CBOR)
        logger.warning("mDoc format is placeholder - real implementation needs CBOR")
        return base64.urlsafe_b64encode(
            json.dumps(mdoc_data).encode()
        ).rstrip(b"=").decode()

    async def _sign_jwt_payload(self, signing_key: dict, message: str) -> str:
        """Sign a JWT message with the given key.
        
        Args:
            signing_key: Key configuration with private_key_jwk
            message: The header.payload string to sign
            
        Returns:
            Base64url-encoded signature
        """
        private_jwk = signing_key.get("private_key_jwk")
        
        if not private_jwk or "d" not in private_jwk:
            # No private key available - return placeholder signature
            logger.warning("No private key available, using placeholder signature")
            return "placeholder_signature"
        
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.backends import default_backend
            
            # Decode JWK to private key
            def _b64url_decode(s: str) -> bytes:
                # Add padding
                padding = 4 - len(s) % 4
                if padding != 4:
                    s += "=" * padding
                return base64.urlsafe_b64decode(s)
            
            crv = private_jwk.get("crv", "P-256")
            if crv == "P-256":
                curve = ec.SECP256R1()
            elif crv == "P-384":
                curve = ec.SECP384R1()
            elif crv == "P-521":
                curve = ec.SECP521R1()
            else:
                raise ValueError(f"Unsupported curve: {crv}")
            
            d = int.from_bytes(_b64url_decode(private_jwk["d"]), byteorder="big")
            x = int.from_bytes(_b64url_decode(private_jwk["x"]), byteorder="big")
            y = int.from_bytes(_b64url_decode(private_jwk["y"]), byteorder="big")
            
            public_numbers = ec.EllipticCurvePublicNumbers(x, y, curve)
            private_numbers = ec.EllipticCurvePrivateNumbers(d, public_numbers)
            private_key = private_numbers.private_key(default_backend())
            
            # Sign using ECDSA
            signature_der = private_key.sign(
                message.encode(),
                ec.ECDSA(hashes.SHA256()),
            )
            
            # Convert DER to raw R||S format for JWS
            from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
            r, s = decode_dss_signature(signature_der)
            
            # Determine byte length based on curve
            byte_length = (curve.key_size + 7) // 8
            
            r_bytes = r.to_bytes(byte_length, byteorder="big")
            s_bytes = s.to_bytes(byte_length, byteorder="big")
            
            raw_signature = r_bytes + s_bytes
            return base64.urlsafe_b64encode(raw_signature).rstrip(b"=").decode()
            
        except ImportError:
            logger.warning("cryptography library not available for signing")
            return "placeholder_signature"
        except Exception as e:
            logger.error(f"Signing failed: {e}")
            return "placeholder_signature"


# Singleton instance
_credential_signer: Optional[CredentialSigner] = None


def get_credential_signer() -> CredentialSigner:
    """Get the credential signer singleton."""
    global _credential_signer
    if _credential_signer is None:
        _credential_signer = CredentialSigner()
    return _credential_signer
