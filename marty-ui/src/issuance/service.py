"""Credential issuance service.

Business logic for creating credential offers and managing the
issuance lifecycle. Integrates with the applicant service for
approval-triggered issuance.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from subscription.models import (
    CredentialOffer,
    IssuanceSession,
    IssuanceStatus,
)

logger = logging.getLogger(__name__)


# Configuration
OFFER_EXPIRY_SECONDS = 300  # 5 minutes for real-time
DEFERRED_EXPIRY_SECONDS = 86400  # 24 hours for deferred
TRANSACTION_ID_LENGTH = 32


# In-memory storage (shared with router for now)
# TODO: Move to database
_issuance_sessions: dict[str, IssuanceSession] = {}
_credential_offers: dict[str, CredentialOffer] = {}


def _generate_transaction_id() -> str:
    """Generate a unique transaction ID."""
    return secrets.token_urlsafe(TRANSACTION_ID_LENGTH)


def _generate_pre_authorized_code() -> str:
    """Generate a pre-authorized code."""
    return secrets.token_urlsafe(32)


class IssuanceService:
    """Service for managing credential issuance."""

    def __init__(self, issuer_url: str = "http://localhost:8000"):
        self.issuer_url = issuer_url

    async def create_offer_for_application(
        self,
        *,
        organization_id: str,
        application_id: str,
        credential_config_id: str,
        applicant_id: str,
        credential_data: dict,
        device_id: Optional[str] = None,
        credential_format: str = "vc+sd-jwt",
        auto_accept: bool = True,  # Auto-accept since holder already applied
    ) -> IssuanceSession:
        """Create a credential offer for an approved application.

        This is the main integration point called after an application
        is approved and ready for credential issuance.
        
        Since the holder already consented by submitting the application,
        the credential is automatically accepted and pushed to their
        authenticator - no additional user action required.

        Args:
            organization_id: The issuing organization ID
            application_id: The source application ID
            credential_config_id: The credential type configuration ID
            applicant_id: The recipient user ID
            credential_data: The claim values for the credential
            device_id: Optional target device for push notification
            credential_format: Credential format (vc+sd-jwt, jwt_vc_json, mso_mdoc)
            auto_accept: Auto-accept the offer (default True for application flow)

        Returns:
            The created IssuanceSession with transaction_id and offer_uri
        """
        session_id = str(uuid.uuid4())
        transaction_id = _generate_transaction_id()
        pre_authorized_code = _generate_pre_authorized_code()

        # For auto-accept (application flow), credential is generated immediately
        # and pushed to the authenticator - no user action needed
        expiry = datetime.utcnow() + timedelta(seconds=DEFERRED_EXPIRY_SECONDS)

        # Create issuance session
        session = IssuanceSession()
        session.id = session_id
        session.transaction_id = transaction_id
        session.organization_id = organization_id
        session.application_id = application_id
        session.credential_config_id = credential_config_id
        session.applicant_id = applicant_id
        session.device_id = device_id
        session.status = IssuanceStatus.PENDING
        session.pre_authorized_code = pre_authorized_code
        session.credential_format = credential_format
        session.credential_data = credential_data
        session.expires_at = expiry
        session.created_at = datetime.utcnow()

        _issuance_sessions[transaction_id] = session

        # Build credential offer
        offer_payload = self._build_credential_offer(session)
        offer_uri = self._build_credential_offer_uri(session_id)

        # Create offer record
        offer = CredentialOffer()
        offer.id = str(uuid.uuid4())
        offer.issuance_session_id = session_id
        offer.offer_uri = offer_uri
        offer.offer_payload = offer_payload
        offer.is_active = True
        offer.expires_at = expiry
        offer.created_at = datetime.utcnow()

        _credential_offers[offer.id] = offer

        logger.info(
            f"Created issuance session {session_id} for application {application_id}, "
            f"transaction_id={transaction_id}, auto_accept={auto_accept}"
        )

        # Generate the credential immediately
        await self._queue_credential_generation(session)

        if auto_accept:
            # Auto-accept: mark as accepted and issued, push credential to authenticator
            session.status = IssuanceStatus.ISSUED
            session.accepted_at = datetime.utcnow()
            session.issued_at = datetime.utcnow()
            
            # Push the actual credential to the authenticator (not just an offer)
            if device_id:
                await self._push_credential_to_authenticator(session)
        else:
            # Manual accept: send offer notification, user must accept
            if device_id:
                await self._send_credential_ready_notification(session, offer_uri)

        return session

    async def get_session(self, transaction_id: str) -> Optional[IssuanceSession]:
        """Get issuance session by transaction ID."""
        return _issuance_sessions.get(transaction_id)

    async def get_session_by_application(self, application_id: str) -> Optional[IssuanceSession]:
        """Get issuance session by application ID."""
        for session in _issuance_sessions.values():
            if session.application_id == application_id:
                return session
        return None

    async def update_session_status(
        self,
        transaction_id: str,
        status: IssuanceStatus,
        credential: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[IssuanceSession]:
        """Update issuance session status.

        Called by the credential generation worker when async processing completes.
        """
        session = _issuance_sessions.get(transaction_id)
        if not session:
            return None

        session.status = status
        session.updated_at = datetime.utcnow()

        if credential:
            session.issued_credential = credential
            session.issued_at = datetime.utcnow()

        if error_message:
            session.error_message = error_message

        logger.info(f"Updated issuance session {transaction_id} to status {status}")

        return session

    def _build_credential_offer(self, session: IssuanceSession) -> dict:
        """Build OID4VCI credential offer payload."""
        return {
            "credential_issuer": self.issuer_url,
            "credential_configuration_ids": [session.credential_config_id],
            "grants": {
                "urn:ietf:params:oauth:grant-type:pre-authorized_code": {
                    "pre-authorized_code": session.pre_authorized_code,
                    "tx_code": None,
                }
            },
        }

    def _build_credential_offer_uri(self, session_id: str) -> str:
        """Build credential offer URI for wallet."""
        from urllib.parse import urlencode

        offer_endpoint = f"{self.issuer_url}/api/issuance/offers/{session_id}"
        params = urlencode({"credential_offer_uri": offer_endpoint})
        return f"openid-credential-offer://?{params}"

    async def _queue_credential_generation(self, session: IssuanceSession) -> None:
        """Queue async credential generation.

        In production, this would:
        1. Send a message to a job queue (Celery, RQ, etc.)
        2. The worker would fetch the session, generate the credential,
           and call update_session_status

        For now, we perform immediate signing.
        """
        logger.info(f"Generating credential for session {session.id}")

        try:
            # Sign the credential
            from issuance.signing import get_credential_signer
            
            signer = get_credential_signer()
            credential = await signer.sign_credential(
                organization_id=session.organization_id,
                credential_config_id=session.credential_config_id,
                subject_id=session.applicant_id,
                claims=session.credential_data or {},
                credential_format=session.credential_format or "vc+sd-jwt",
            )
            
            session.status = IssuanceStatus.READY
            session.issued_credential = credential
            session.issued_at = datetime.utcnow()
            
            logger.info(f"Credential generated for session {session.id}")
            
        except Exception as e:
            logger.error(f"Failed to generate credential for session {session.id}: {e}")
            session.status = IssuanceStatus.FAILED
            session.error_message = str(e)

    async def _push_credential_to_authenticator(
        self,
        session: IssuanceSession,
    ) -> bool:
        """Push the credential directly to the authenticator.

        For auto-accept flow: the holder already consented when they applied,
        so we push the credential directly to their wallet without requiring
        them to manually accept an offer.

        Args:
            session: The issuance session with the generated credential

        Returns:
            True if credential was pushed successfully
        """
        if not session.device_id:
            logger.info(
                f"No device_id for session {session.id}, skipping push"
            )
            return False

        if not session.issued_credential:
            logger.error(
                f"No credential to push for session {session.id}"
            )
            return False

        # Build push payload with the actual credential
        payload = {
            "type": "credential_issued",
            "title": "New Credential",
            "body": "A new credential has been added to your wallet",
            "data": {
                "action": "store_credential",
                "transaction_id": session.transaction_id,
                "credential_config_id": session.credential_config_id,
                "credential_format": session.credential_format,
                "credential": session.issued_credential,
                "credential_data": session.credential_data,
                "issued_at": session.issued_at.isoformat() if session.issued_at else None,
            },
            "priority": "high",
        }

        try:
            # Push via FCM or SSE
            logger.info(
                f"[PUSH] Sending credential to device {session.device_id}: "
                f"transaction_id={session.transaction_id}"
            )
            
            # TODO: Integrate with actual push service (FCM/SSE)
            # For now, store in a pickup queue that the authenticator can poll
            from issuance.notifications import get_credential_offer_notifier
            
            notifier = get_credential_offer_notifier()
            # The notifier will handle the push delivery
            await notifier.notify_credential_ready(
                session, 
                f"credential://{session.transaction_id}"  # Direct credential URI
            )
            
            logger.info(
                f"Credential pushed to authenticator for session {session.id}"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"Failed to push credential for session {session.id}: {e}"
            )
            return False

    async def _send_credential_ready_notification(
        self,
        session: IssuanceSession,
        credential_offer_uri: str,
    ) -> bool:
        """Send push notification that credential offer is ready.

        For manual accept flow: notify user they have a pending offer.

        Args:
            session: The issuance session
            credential_offer_uri: The credential offer URI for wallet

        Returns:
            True if notification was sent
        """
        from issuance.notifications import send_credential_offer_notification

        try:
            return await send_credential_offer_notification(session, credential_offer_uri)
        except Exception as e:
            logger.error(
                f"Failed to send credential ready notification for session {session.id}: {e}"
            )
            return False

    def _generate_placeholder_credential(self, session: IssuanceSession) -> str:
        """Generate a placeholder credential for testing.

        In production, this would:
        1. Fetch the organization's signing key
        2. Build the credential claims from session.credential_data
        3. Sign using the appropriate format (SD-JWT, jwt_vc_json, mso_mdoc)
        """
        # Placeholder SD-JWT structure
        import json
        import base64

        header = {"alg": "ES256", "typ": "vc+sd-jwt"}
        payload = {
            "iss": self.issuer_url,
            "sub": session.applicant_id,
            "iat": int(datetime.utcnow().timestamp()),
            "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp()),
            "vc": {
                "type": ["VerifiableCredential"],
                "credentialSubject": session.credential_data or {},
            },
        }

        # Encode (not a real JWT - placeholder only)
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

        return f"{header_b64}.{payload_b64}.placeholder_signature"


# Singleton instance
_issuance_service: Optional[IssuanceService] = None


def get_issuance_service() -> IssuanceService:
    """Get the issuance service singleton."""
    global _issuance_service
    if _issuance_service is None:
        _issuance_service = IssuanceService()
    return _issuance_service
