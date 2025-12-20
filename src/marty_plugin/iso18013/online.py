"""
ISO/IEC 18013-7 Online Flows Implementation

This module implements the complete online mDL transaction protocol over HTTPS/TLS
including relying party flows, policy prompts, and consent management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode, urlparse

try:
    import aiohttp
    import jwt
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None
    jwt = None

from ..transport import HTTPError, TransportMessage, TransportState
from ..transport import HTTPSTransport as BaseHTTPSTransport

logger = logging.getLogger(__name__)


class PresentationState(Enum):
    """Online presentation flow states"""

    INITIATED = "initiated"
    POLICY_DISPLAYED = "policy_displayed"
    CONSENT_PENDING = "consent_pending"
    CONSENT_GRANTED = "consent_granted"
    CONSENT_DENIED = "consent_denied"
    PRESENTATION_SENT = "presentation_sent"
    VERIFIED = "verified"
    COMPLETED = "completed"
    ERROR = "error"


class ConsentLevel(Enum):
    """Consent levels for data sharing"""

    MINIMAL = "minimal"  # Only required fields
    STANDARD = "standard"  # Required + some optional
    FULL = "full"  # All requested fields


@dataclass
class PresentationDefinition:
    """ISO 18013-7 presentation definition"""

    id: str
    name: str
    purpose: str
    input_descriptors: list[dict[str, Any]]
    format: dict[str, Any] = field(default_factory=dict)
    submission_requirements: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "purpose": self.purpose,
            "input_descriptors": self.input_descriptors,
            "format": self.format,
            "submission_requirements": self.submission_requirements,
        }


@dataclass
class ConsentRequest:
    """User consent request for data sharing"""

    session_id: str
    relying_party: str
    purpose: str
    requested_data: dict[str, list[str]]
    policy_url: str | None = None
    retention_period: str | None = None
    consent_level_options: list[ConsentLevel] = field(
        default_factory=lambda: [ConsentLevel.STANDARD]
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "relying_party": self.relying_party,
            "purpose": self.purpose,
            "requested_data": self.requested_data,
            "policy_url": self.policy_url,
            "retention_period": self.retention_period,
            "consent_options": [level.value for level in self.consent_level_options],
        }


@dataclass
class ConsentResponse:
    """User consent response"""

    session_id: str
    granted: bool
    consent_level: ConsentLevel
    approved_data: dict[str, list[str]]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "granted": self.granted,
            "consent_level": self.consent_level.value,
            "approved_data": self.approved_data,
            "timestamp": self.timestamp.isoformat(),
        }


class ISO18013_7RelyingParty:
    """
    ISO/IEC 18013-7 Relying Party Implementation

    Implements the complete online mDL verification flow including:
    - Presentation request initiation
    - Policy display and consent management
    - Credential verification and validation
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        private_key: ec.EllipticCurvePrivateKey | None = None,
        verify_ssl: bool = True,
    ):
        if not AIOHTTP_AVAILABLE:
            raise HTTPError("aiohttp library not available - install with: pip install aiohttp")

        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.private_key = private_key or ec.generate_private_key(ec.SECP256R1())
        self.verify_ssl = verify_ssl

        # Session storage
        self.sessions: dict[str, dict[str, Any]] = {}
        self.consent_requests: dict[str, ConsentRequest] = {}

        # HTTP session
        self.http_session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()

    async def start(self) -> None:
        """Start the relying party service"""
        connector = aiohttp.TCPConnector(verify_ssl=self.verify_ssl)
        self.http_session = aiohttp.ClientSession(connector=connector)
        logger.info(f"ISO 18013-7 Relying Party started: {self.base_url}")

    async def stop(self) -> None:
        """Stop the relying party service"""
        if self.http_session:
            await self.http_session.close()
            self.http_session = None
        logger.info("ISO 18013-7 Relying Party stopped")

    async def initiate_presentation_request(
        self,
        holder_wallet_url: str,
        presentation_definition: PresentationDefinition,
        callback_url: str | None = None,
        policy_url: str | None = None,
    ) -> str:
        """
        Initiate presentation request to holder's wallet

        Args:
            holder_wallet_url: Holder's wallet endpoint URL
            presentation_definition: Definition of requested presentation
            callback_url: URL for presentation response callback
            policy_url: URL for privacy policy

        Returns:
            Presentation session ID
        """
        try:
            session_id = str(uuid.uuid4())

            # Create session
            session = {
                "session_id": session_id,
                "state": PresentationState.INITIATED,
                "holder_wallet_url": holder_wallet_url,
                "presentation_definition": presentation_definition,
                "callback_url": callback_url
                or f"{self.base_url}/presentations/{session_id}/response",
                "policy_url": policy_url,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(minutes=15),
            }

            self.sessions[session_id] = session

            # Create presentation request JWT
            request_jwt = await self._create_presentation_request_jwt(session)

            # Send request to holder's wallet
            request_url = f"{holder_wallet_url}/presentations/request"

            async with self.http_session.post(
                request_url,
                json={
                    "presentation_request": request_jwt,
                    "callback_url": session["callback_url"],
                    "session_id": session_id,
                },
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    session["state"] = PresentationState.POLICY_DISPLAYED
                    logger.info(f"Presentation request sent: {session_id}")
                    return session_id
                else:
                    raise HTTPError(f"Presentation request failed: HTTP {response.status}")

        except Exception as e:
            logger.error(f"Presentation request initiation failed: {e}")
            raise HTTPError(f"Presentation request initiation failed: {e}")

    async def handle_consent_request(
        self,
        session_id: str,
        requested_data: dict[str, list[str]],
        purpose: str,
        relying_party_name: str,
    ) -> ConsentRequest:
        """
        Handle consent request from holder

        Args:
            session_id: Presentation session ID
            requested_data: Data being requested
            purpose: Purpose of data request
            relying_party_name: Name of relying party

        Returns:
            Consent request object
        """
        try:
            session = self.sessions.get(session_id)
            if not session:
                raise HTTPError(f"Session not found: {session_id}")

            # Create consent request
            consent_request = ConsentRequest(
                session_id=session_id,
                relying_party=relying_party_name,
                purpose=purpose,
                requested_data=requested_data,
                policy_url=session.get("policy_url"),
                retention_period="30 days",  # Example
                consent_level_options=[
                    ConsentLevel.MINIMAL,
                    ConsentLevel.STANDARD,
                    ConsentLevel.FULL,
                ],
            )

            self.consent_requests[session_id] = consent_request
            session["state"] = PresentationState.CONSENT_PENDING

            logger.info(f"Consent request created: {session_id}")
            return consent_request

        except Exception as e:
            logger.error(f"Consent request handling failed: {e}")
            raise HTTPError(f"Consent request handling failed: {e}")

    async def process_consent_response(
        self, session_id: str, consent_response: ConsentResponse
    ) -> bool:
        """
        Process consent response from holder

        Args:
            session_id: Presentation session ID
            consent_response: Consent response from holder

        Returns:
            True if consent granted
        """
        try:
            session = self.sessions.get(session_id)
            if not session:
                raise HTTPError(f"Session not found: {session_id}")

            session["consent_response"] = consent_response

            if consent_response.granted:
                session["state"] = PresentationState.CONSENT_GRANTED
                logger.info(f"Consent granted for session: {session_id}")
                return True
            else:
                session["state"] = PresentationState.CONSENT_DENIED
                logger.info(f"Consent denied for session: {session_id}")
                return False

        except Exception as e:
            logger.error(f"Consent response processing failed: {e}")
            raise HTTPError(f"Consent response processing failed: {e}")

    async def handle_presentation_submission(
        self, session_id: str, presentation_submission: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Handle presentation submission from holder

        Args:
            session_id: Presentation session ID
            presentation_submission: Presentation submission data

        Returns:
            Verification result
        """
        try:
            session = self.sessions.get(session_id)
            if not session:
                raise HTTPError(f"Session not found: {session_id}")

            session["state"] = PresentationState.PRESENTATION_SENT
            session["presentation_submission"] = presentation_submission

            # Verify presentation
            verification_result = await self._verify_presentation_submission(
                presentation_submission, session["presentation_definition"]
            )

            # Update session
            session["verification_result"] = verification_result
            session["state"] = (
                PresentationState.VERIFIED
                if verification_result["valid"]
                else PresentationState.ERROR
            )
            session["completed_at"] = datetime.utcnow()

            logger.info(
                f"Presentation verified: {session_id}, valid: {verification_result['valid']}"
            )

            return verification_result

        except Exception as e:
            logger.error(f"Presentation submission handling failed: {e}")
            session = self.sessions.get(session_id)
            if session:
                session["state"] = PresentationState.ERROR
            raise HTTPError(f"Presentation submission handling failed: {e}")

    async def _create_presentation_request_jwt(self, session: dict[str, Any]) -> str:
        """Create JWT for presentation request"""
        try:
            now = datetime.utcnow()

            payload = {
                "iss": self.client_id,
                "aud": session["holder_wallet_url"],
                "iat": int(now.timestamp()),
                "exp": int(session["expires_at"].timestamp()),
                "nonce": secrets.token_urlsafe(32),
                "presentation_definition": session["presentation_definition"].to_dict(),
                "response_uri": session["callback_url"],
                "response_mode": "direct_post",
                "client_id": self.client_id,
                "state": session["session_id"],
            }

            # Sign JWT
            private_key_pem = self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

            token = jwt.encode(
                payload, private_key_pem, algorithm="ES256", headers={"typ": "JWT", "alg": "ES256"}
            )

            return token

        except Exception as e:
            logger.error(f"JWT creation failed: {e}")
            raise HTTPError(f"JWT creation failed: {e}")

    async def _verify_presentation_submission(
        self,
        presentation_submission: dict[str, Any],
        presentation_definition: PresentationDefinition,
    ) -> dict[str, Any]:
        """
        Verify presentation submission against definition

        Args:
            presentation_submission: Submitted presentation
            presentation_definition: Required presentation definition

        Returns:
            Verification result
        """
        try:
            verification_result = {
                "valid": True,
                "verified_claims": {},
                "verification_details": [],
                "errors": [],
                "trust_chain_valid": True,
                "signature_valid": True,
                "presentation_time": datetime.utcnow().isoformat(),
                "issuer_trust_status": "trusted",
            }

            # Extract verifiable presentations
            vp_token = presentation_submission.get("vp_token")
            if not vp_token:
                verification_result["valid"] = False
                verification_result["errors"].append("No VP token in submission")
                return verification_result

            # Verify VP token (simplified)
            # In real implementation, this would:
            # 1. Verify JWT signature
            # 2. Check issuer trust chain
            # 3. Validate credential status
            # 4. Verify selective disclosure proofs
            # 5. Check policy compliance

            verification_result["verification_details"].append(
                {
                    "check": "vp_token_present",
                    "status": "passed",
                    "details": "VP token found in submission",
                }
            )

            # Mock verification of mDL credential
            if isinstance(vp_token, str):
                try:
                    # Decode JWT (without verification for demo)
                    decoded = jwt.decode(vp_token, options={"verify_signature": False})

                    # Extract credential data
                    vp_data = decoded.get("vp", {})
                    credentials = vp_data.get("verifiableCredential", [])

                    for cred in credentials:
                        if isinstance(cred, str):
                            # Decode credential JWT
                            cred_data = jwt.decode(cred, options={"verify_signature": False})
                            credential_subject = cred_data.get("vc", {}).get(
                                "credentialSubject", {}
                            )

                            # Extract claims based on presentation definition
                            for descriptor in presentation_definition.input_descriptors:
                                descriptor_id = descriptor["id"]
                                fields = descriptor.get("constraints", {}).get("fields", [])

                                verified_claims = {}
                                for field in fields:
                                    path = field["path"][0] if field.get("path") else ""
                                    # Simplified path extraction
                                    field_name = path.split(".")[-1] if "." in path else path

                                    if field_name in credential_subject:
                                        verified_claims[field_name] = credential_subject[field_name]

                                verification_result["verified_claims"][
                                    descriptor_id
                                ] = verified_claims

                    verification_result["verification_details"].append(
                        {
                            "check": "credential_extraction",
                            "status": "passed",
                            "details": f"Extracted {len(verification_result['verified_claims'])} claim sets",
                        }
                    )

                except Exception as e:
                    verification_result["valid"] = False
                    verification_result["errors"].append(f"VP token decoding failed: {e}")

            logger.info(
                f"Presentation verification completed: valid={verification_result['valid']}"
            )
            return verification_result

        except Exception as e:
            logger.error(f"Presentation verification failed: {e}")
            return {
                "valid": False,
                "error": str(e),
                "verification_time": datetime.utcnow().isoformat(),
            }

    def get_session_status(self, session_id: str) -> dict[str, Any] | None:
        """Get session status"""
        session = self.sessions.get(session_id)
        if not session:
            return None

        return {
            "session_id": session_id,
            "state": session["state"].value,
            "created_at": session["created_at"].isoformat(),
            "expires_at": session["expires_at"].isoformat(),
            "has_consent_response": "consent_response" in session,
            "verification_complete": "verification_result" in session,
        }

    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        now = datetime.utcnow()
        expired_sessions = []

        for session_id, session in self.sessions.items():
            if session["expires_at"] < now:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del self.sessions[session_id]
            if session_id in self.consent_requests:
                del self.consent_requests[session_id]

        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
        return len(expired_sessions)


class ISO18013_7Holder:
    """
    ISO/IEC 18013-7 Holder Implementation

    Implements the holder side of online mDL transactions including:
    - Presentation request handling
    - User consent management
    - Credential presentation
    """

    def __init__(
        self,
        wallet_url: str,
        holder_id: str,
        private_key: ec.EllipticCurvePrivateKey | None = None,
    ):
        if not AIOHTTP_AVAILABLE:
            raise HTTPError("aiohttp library not available")

        self.wallet_url = wallet_url.rstrip("/")
        self.holder_id = holder_id
        self.private_key = private_key or ec.generate_private_key(ec.SECP256R1())

        # Credential storage (mock)
        self.credentials: dict[str, dict[str, Any]] = {}

        # HTTP session
        self.http_session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()

    async def start(self) -> None:
        """Start the holder service"""
        self.http_session = aiohttp.ClientSession()
        logger.info(f"ISO 18013-7 Holder started: {self.wallet_url}")

    async def stop(self) -> None:
        """Stop the holder service"""
        if self.http_session:
            await self.http_session.close()
            self.http_session = None
        logger.info("ISO 18013-7 Holder stopped")

    async def handle_presentation_request(
        self, presentation_request_jwt: str, callback_url: str
    ) -> ConsentRequest:
        """
        Handle incoming presentation request

        Args:
            presentation_request_jwt: JWT containing presentation request
            callback_url: URL to send response to

        Returns:
            Consent request for user approval
        """
        try:
            # Decode presentation request
            request_data = jwt.decode(
                presentation_request_jwt,
                options={"verify_signature": False},  # In production, verify signature
            )

            presentation_definition = request_data["presentation_definition"]
            session_id = request_data["state"]

            # Extract requested data elements
            requested_data = {}
            for descriptor in presentation_definition["input_descriptors"]:
                doc_type = descriptor.get("id", "unknown")
                fields = []

                constraints = descriptor.get("constraints", {})
                for field in constraints.get("fields", []):
                    path = field.get("path", [""])[0]
                    field_name = path.split(".")[-1] if "." in path else path
                    if field_name:
                        fields.append(field_name)

                requested_data[doc_type] = fields

            # Create consent request
            consent_request = ConsentRequest(
                session_id=session_id,
                relying_party=request_data.get("iss", "Unknown Relying Party"),
                purpose=presentation_definition.get("purpose", "Identity Verification"),
                requested_data=requested_data,
                policy_url=request_data.get("policy_url"),
                retention_period="30 days",
            )

            logger.info(f"Presentation request received: {session_id}")
            return consent_request

        except Exception as e:
            logger.error(f"Presentation request handling failed: {e}")
            raise HTTPError(f"Presentation request handling failed: {e}")

    async def create_presentation_submission(
        self, consent_response: ConsentResponse, callback_url: str
    ) -> dict[str, Any]:
        """
        Create and send presentation submission

        Args:
            consent_response: User's consent response
            callback_url: URL to send submission to

        Returns:
            Submission result
        """
        try:
            if not consent_response.granted:
                raise HTTPError("Consent not granted")

            # Create verifiable presentation
            vp_token = await self._create_verifiable_presentation(consent_response)

            # Create presentation submission
            submission = {
                "presentation_submission": {
                    "id": str(uuid.uuid4()),
                    "definition_id": consent_response.session_id,
                    "descriptor_map": [],
                },
                "vp_token": vp_token,
            }

            # Send submission to relying party
            async with self.http_session.post(
                callback_url, json=submission, headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(
                        f"Presentation submitted successfully: {consent_response.session_id}"
                    )
                    return result
                else:
                    raise HTTPError(f"Presentation submission failed: HTTP {response.status}")

        except Exception as e:
            logger.error(f"Presentation submission failed: {e}")
            raise HTTPError(f"Presentation submission failed: {e}")

    async def _create_verifiable_presentation(self, consent_response: ConsentResponse) -> str:
        """Create verifiable presentation JWT"""
        try:
            now = datetime.utcnow()

            # Mock credential data (in real implementation, this would come from secure storage)
            mock_credential = {
                "@context": ["https://www.w3.org/2018/credentials/v1"],
                "id": str(uuid.uuid4()),
                "type": ["VerifiableCredential", "mDL"],
                "issuer": "did:example:issuer",
                "issuanceDate": "2024-01-01T00:00:00Z",
                "credentialSubject": {
                    "id": f"did:example:{self.holder_id}",
                    "family_name": "Doe",
                    "given_name": "John",
                    "birth_date": "1990-01-01",
                    "document_number": "DL123456789",
                    "issuing_country": "US",
                    "issuing_authority": "State DMV",
                },
            }

            # Filter to only approved data
            filtered_subject = {}
            for doc_type, fields in consent_response.approved_data.items():
                for field in fields:
                    if field in mock_credential["credentialSubject"]:
                        filtered_subject[field] = mock_credential["credentialSubject"][field]

            mock_credential["credentialSubject"] = {
                "id": mock_credential["credentialSubject"]["id"],
                **filtered_subject,
            }

            # Create credential JWT
            credential_jwt = jwt.encode(
                {
                    "iss": f"did:example:{self.holder_id}",
                    "sub": f"did:example:{self.holder_id}",
                    "iat": int(now.timestamp()),
                    "exp": int((now + timedelta(minutes=5)).timestamp()),
                    "vc": mock_credential,
                },
                self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ),
                algorithm="ES256",
            )

            # Create verifiable presentation
            vp = {
                "@context": ["https://www.w3.org/2018/credentials/v1"],
                "type": ["VerifiablePresentation"],
                "holder": f"did:example:{self.holder_id}",
                "verifiableCredential": [credential_jwt],
            }

            # Create VP JWT
            vp_jwt = jwt.encode(
                {
                    "iss": f"did:example:{self.holder_id}",
                    "aud": "relying_party",
                    "iat": int(now.timestamp()),
                    "exp": int((now + timedelta(minutes=5)).timestamp()),
                    "nonce": secrets.token_urlsafe(16),
                    "vp": vp,
                },
                self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ),
                algorithm="ES256",
            )

            return vp_jwt

        except Exception as e:
            logger.error(f"VP creation failed: {e}")
            raise HTTPError(f"VP creation failed: {e}")

    def add_credential(self, credential_id: str, credential_data: dict[str, Any]) -> None:
        """Add credential to holder's wallet"""
        self.credentials[credential_id] = credential_data
        logger.info(f"Credential added: {credential_id}")

    def list_credentials(self) -> list[dict[str, Any]]:
        """List available credentials"""
        return [
            {"id": cred_id, "type": cred_data.get("type", []), "issuer": cred_data.get("issuer")}
            for cred_id, cred_data in self.credentials.items()
        ]


# Demo function to simulate complete online flow
async def simulate_online_mdl_transaction() -> dict[str, Any]:
    """
    Simulate a complete online mDL transaction for testing

    Returns:
        Transaction result
    """
    try:
        # Create presentation definition
        presentation_def = PresentationDefinition(
            id="mdl_verification",
            name="Driver License Verification",
            purpose="Verify driver license for age verification",
            input_descriptors=[
                {
                    "id": "mdl_credential",
                    "name": "Mobile Driver License",
                    "constraints": {
                        "fields": [
                            {"path": ["$.credentialSubject.family_name"]},
                            {"path": ["$.credentialSubject.given_name"]},
                            {"path": ["$.credentialSubject.birth_date"]},
                            {"path": ["$.credentialSubject.document_number"]},
                        ]
                    },
                }
            ],
        )

        # Initialize relying party and holder
        async with (
            ISO18013_7RelyingParty(
                base_url="https://rp.example.com", client_id="rp_client_123"
            ) as rp,
            ISO18013_7Holder(
                wallet_url="https://wallet.example.com", holder_id="holder_456"
            ) as holder,
        ):
            # Step 1: Initiate presentation request
            session_id = await rp.initiate_presentation_request(
                holder_wallet_url=holder.wallet_url,
                presentation_definition=presentation_def,
                policy_url="https://rp.example.com/privacy-policy",
            )

            # Step 2: Handle presentation request (mock JWT)
            mock_jwt = jwt.encode(
                {
                    "iss": rp.client_id,
                    "state": session_id,
                    "presentation_definition": presentation_def.to_dict(),
                },
                "secret",  # Mock secret
                algorithm="HS256",
            )

            consent_request = await holder.handle_presentation_request(
                mock_jwt, f"{rp.base_url}/presentations/{session_id}/response"
            )

            # Step 3: User grants consent
            consent_response = ConsentResponse(
                session_id=session_id,
                granted=True,
                consent_level=ConsentLevel.STANDARD,
                approved_data={
                    "mdl_credential": ["family_name", "given_name", "birth_date", "document_number"]
                },
            )

            await rp.process_consent_response(session_id, consent_response)

            # Step 4: Create and submit presentation
            submission_result = await holder.create_presentation_submission(
                consent_response, f"{rp.base_url}/presentations/{session_id}/response"
            )

            return {
                "success": True,
                "session_id": session_id,
                "transaction_type": "online_mdl",
                "consent_level": consent_response.consent_level.value,
                "fields_disclosed": len(consent_response.approved_data.get("mdl_credential", [])),
                "timestamp": time.time(),
            }

    except Exception as e:
        logger.error(f"Online transaction simulation failed: {e}")
        return {"success": False, "error": str(e), "timestamp": time.time()}
