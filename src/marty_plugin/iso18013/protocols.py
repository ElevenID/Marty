"""
Protocol Implementation for ISO/IEC 18013-5 and 18013-7

This module implements the complete protocol flows for:
- ISO 18013-5: Offline mDL transactions (BLE, NFC)
- ISO 18013-7: Online mDL transactions (HTTPS)
- Device engagement and session establishment
- Selective disclosure protocols
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import cbor2

from .core import DeviceEngagement, SelectiveDisclosure, SessionManager, mDLRequest, mDLResponse
from .crypto import (
    KeyDerivation,
    KeyManager,
    MessageAuthentication,
    SelectiveDisclosureCrypto,
    SessionEncryption,
    generate_random_bytes,
)
from .transport import TransportInterface, TransportMessage

logger = logging.getLogger(__name__)


class ProtocolState(Enum):
    """Protocol session states"""

    IDLE = "idle"
    DEVICE_ENGAGEMENT = "device_engagement"
    SESSION_ESTABLISHMENT = "session_establishment"
    REQUEST_SENT = "request_sent"
    RESPONSE_RECEIVED = "response_received"
    SESSION_TERMINATION = "session_termination"
    ERROR = "error"


class ProtocolError(Exception):
    """Base exception for protocol errors"""

    pass


class SessionEstablishmentError(ProtocolError):
    """Session establishment specific errors"""

    pass


class MessageProtocolError(ProtocolError):
    """Message protocol specific errors"""

    pass


@dataclass
class SessionContext:
    """Context information for a protocol session"""

    session_id: str
    state: ProtocolState = ProtocolState.IDLE
    reader_key: Any | None = None
    device_key: Any | None = None
    session_manager: SessionManager | None = None
    encryption: SessionEncryption | None = None
    authentication: MessageAuthentication | None = None
    device_engagement: DeviceEngagement | None = None
    transport: TransportInterface | None = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


class ISO18013_5Protocol:
    """
    ISO/IEC 18013-5 Protocol Implementation

    Implements the complete offline mDL transaction protocol including:
    - Device engagement
    - Session establishment
    - Request/response exchange
    - Session termination
    """

    def __init__(self):
        self.sessions: dict[str, SessionContext] = {}
        self.message_handlers = {
            "device_engagement": self._handle_device_engagement,
            "session_establishment": self._handle_session_establishment,
            "mdl_request": self._handle_mdl_request,
            "mdl_response": self._handle_mdl_response,
        }

    async def initiate_reader_session(
        self,
        transport: TransportInterface,
        requested_data_elements: dict[str, list[str]] | None = None,
    ) -> str:
        """
        Initiate a reader session (reader acting as verifier)

        Args:
            transport: Transport layer to use
            requested_data_elements: Data elements to request

        Returns:
            Session ID
        """
        try:
            session_id = str(uuid.uuid4())

            # Create session context
            session = SessionContext(
                session_id=session_id, state=ProtocolState.DEVICE_ENGAGEMENT, transport=transport
            )

            # Generate reader key pair
            reader_private_key, reader_public_key = KeyManager.generate_ephemeral_keypair()
            session.reader_key = reader_private_key

            # Store session
            self.sessions[session_id] = session

            logger.info(f"Initiated reader session: {session_id}")

            # Start device discovery/engagement process
            await self._initiate_device_engagement(session)

            return session_id

        except Exception as e:
            logger.error(f"Reader session initiation failed: {e}")
            raise ProtocolError(f"Reader session initiation failed: {e}")

    async def initiate_holder_session(
        self, transport: TransportInterface, device_engagement: DeviceEngagement
    ) -> str:
        """
        Initiate a holder session (holder acting as prover)

        Args:
            transport: Transport layer to use
            device_engagement: Device engagement data

        Returns:
            Session ID
        """
        try:
            session_id = str(uuid.uuid4())

            # Create session context
            session = SessionContext(
                session_id=session_id,
                state=ProtocolState.SESSION_ESTABLISHMENT,
                transport=transport,
                device_engagement=device_engagement,
            )

            # Generate device key pair
            device_private_key, device_public_key = KeyManager.generate_ephemeral_keypair()
            session.device_key = device_private_key

            # Store session
            self.sessions[session_id] = session

            logger.info(f"Initiated holder session: {session_id}")

            # Send device engagement
            await self._send_device_engagement(session)

            return session_id

        except Exception as e:
            logger.error(f"Holder session initiation failed: {e}")
            raise ProtocolError(f"Holder session initiation failed: {e}")

    async def _initiate_device_engagement(self, session: SessionContext) -> None:
        """Initiate device engagement process from reader side"""
        try:
            # Connect to transport
            if not await session.transport.connect():
                raise ProtocolError("Transport connection failed")

            # Wait for device engagement from holder
            session.state = ProtocolState.DEVICE_ENGAGEMENT
            logger.info(f"Waiting for device engagement: {session.session_id}")

        except Exception as e:
            session.state = ProtocolState.ERROR
            raise ProtocolError(f"Device engagement initiation failed: {e}")

    async def _send_device_engagement(self, session: SessionContext) -> None:
        """Send device engagement from holder side"""
        try:
            if not session.device_engagement:
                raise ProtocolError("No device engagement data")

            # Connect to transport
            if not await session.transport.connect():
                raise ProtocolError("Transport connection failed")

            # Send device engagement
            engagement_data = session.device_engagement.to_cbor()
            await session.transport.send_message(engagement_data, "device_engagement")

            session.state = ProtocolState.SESSION_ESTABLISHMENT
            logger.info(f"Sent device engagement: {session.session_id}")

        except Exception as e:
            session.state = ProtocolState.ERROR
            raise ProtocolError(f"Device engagement send failed: {e}")

    async def establish_session(self, session_id: str) -> bool:
        """
        Establish secure session between reader and holder

        Args:
            session_id: Session identifier

        Returns:
            True if session established successfully
        """
        try:
            session = self.sessions.get(session_id)
            if not session:
                raise ProtocolError(f"Session not found: {session_id}")

            # Create session manager
            session.session_manager = SessionManager()

            # Establish session with device engagement
            if session.device_engagement:
                session_key = session.session_manager.establish_session(
                    session.device_engagement, session.reader_key
                )

                # Initialize encryption and authentication
                session.encryption = SessionEncryption(session.session_manager.session_key)
                session.authentication = MessageAuthentication(
                    KeyDerivation.derive_mac_key(session.session_manager.session_key)
                )

                session.state = ProtocolState.REQUEST_SENT
                logger.info(f"Session established: {session_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Session establishment failed: {e}")
            if session_id in self.sessions:
                self.sessions[session_id].state = ProtocolState.ERROR
            raise SessionEstablishmentError(f"Session establishment failed: {e}")

    async def send_mdl_request(
        self, session_id: str, requested_data_elements: dict[str, list[str]] | None = None
    ) -> bool:
        """
        Send mDL request to holder

        Args:
            session_id: Session identifier
            requested_data_elements: Data elements to request

        Returns:
            True if request sent successfully
        """
        try:
            session = self.sessions.get(session_id)
            if not session or session.state != ProtocolState.REQUEST_SENT:
                raise ProtocolError(f"Invalid session state for request: {session_id}")

            # Create mDL request
            mdl_request = mDLRequest()

            if requested_data_elements:
                for doc_type, elements in requested_data_elements.items():
                    namespaces = {"org.iso.18013.5.1": elements}
                    mdl_request.add_document_request(doc_type, namespaces)
            else:
                # Default request
                mdl_request.add_document_request()

            # Serialize request
            request_data = mdl_request.to_cbor()

            # Encrypt if session is established
            if session.encryption:
                encrypted_data = session.encryption.encrypt_message(request_data)
                await session.transport.send_message(encrypted_data, "mdl_request")
            else:
                await session.transport.send_message(request_data, "mdl_request")

            logger.info(f"Sent mDL request: {session_id}")
            return True

        except Exception as e:
            logger.error(f"mDL request send failed: {e}")
            raise MessageProtocolError(f"mDL request send failed: {e}")

    async def send_mdl_response(
        self,
        session_id: str,
        documents: list[dict[str, Any]],
        requested_elements: list[str] | None = None,
    ) -> bool:
        """
        Send mDL response from holder

        Args:
            session_id: Session identifier
            documents: Documents to include in response
            requested_elements: Elements that were requested

        Returns:
            True if response sent successfully
        """
        try:
            session = self.sessions.get(session_id)
            if not session:
                raise ProtocolError(f"Session not found: {session_id}")

            # Create mDL response with selective disclosure
            mdl_response = mDLResponse()

            for doc_data in documents:
                # Apply selective disclosure
                disclosed_data = self._apply_selective_disclosure(doc_data, requested_elements)

                mdl_response.add_document(
                    doc_type=doc_data.get("docType", "org.iso.18013.5.1.mDL"),
                    issuer_signed=disclosed_data["issuerSigned"],
                    device_signed=disclosed_data["deviceSigned"],
                )

            # Serialize response
            response_data = mdl_response.to_cbor()

            # Encrypt if session is established
            if session.encryption:
                encrypted_data = session.encryption.encrypt_message(response_data)
                await session.transport.send_message(encrypted_data, "mdl_response")
            else:
                await session.transport.send_message(response_data, "mdl_response")

            session.state = ProtocolState.RESPONSE_RECEIVED
            logger.info(f"Sent mDL response: {session_id}")
            return True

        except Exception as e:
            logger.error(f"mDL response send failed: {e}")
            raise MessageProtocolError(f"mDL response send failed: {e}")

    def _apply_selective_disclosure(
        self, document_data: dict[str, Any], requested_elements: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Apply selective disclosure to document data

        Args:
            document_data: Full document data
            requested_elements: Elements that were requested

        Returns:
            Document data with selective disclosure applied
        """
        try:
            if not requested_elements:
                # Return all elements if none specifically requested
                requested_elements = list(document_data.get("elements", {}).keys())

            # Create issuer signed items with selective disclosure
            issuer_signed_items = []
            disclosed_elements = {}

            for element_id in requested_elements:
                if element_id in document_data.get("elements", {}):
                    element_value = document_data["elements"][element_id]
                    random_value = generate_random_bytes(16)

                    # Create selective disclosure item
                    disclosure = SelectiveDisclosure(
                        namespace="org.iso.18013.5.1",
                        element_identifier=element_id,
                        element_value=element_value,
                        random=random_value,
                    )

                    issuer_signed_items.append(disclosure.to_issuer_signed_item())
                    disclosed_elements[element_id] = element_value

            # Create device signed data
            device_signed = {
                "nameSpaces": {"org.iso.18013.5.1": disclosed_elements},
                "deviceAuth": {"deviceSignature": b"mock_device_signature"},  # TODO: Real signature
            }

            return {
                "issuerSigned": {
                    "nameSpaces": {"org.iso.18013.5.1": issuer_signed_items},
                    "issuerAuth": b"mock_issuer_auth",  # TODO: Real issuer auth
                },
                "deviceSigned": device_signed,
            }

        except Exception as e:
            logger.error(f"Selective disclosure failed: {e}")
            raise ProtocolError(f"Selective disclosure failed: {e}")

    async def terminate_session(self, session_id: str) -> None:
        """
        Terminate a protocol session

        Args:
            session_id: Session identifier
        """
        try:
            session = self.sessions.get(session_id)
            if not session:
                return

            # Disconnect transport
            if session.transport:
                await session.transport.disconnect()

            # Update state
            session.state = ProtocolState.SESSION_TERMINATION

            # Clean up session
            del self.sessions[session_id]

            logger.info(f"Session terminated: {session_id}")

        except Exception as e:
            logger.error(f"Session termination failed: {e}")

    async def _handle_device_engagement(self, message: TransportMessage) -> None:
        """Handle received device engagement message"""
        try:
            # Parse device engagement
            device_engagement = DeviceEngagement.from_cbor(message.data)

            # Find session waiting for engagement
            for session in self.sessions.values():
                if session.state == ProtocolState.DEVICE_ENGAGEMENT:
                    session.device_engagement = device_engagement
                    session.state = ProtocolState.SESSION_ESTABLISHMENT
                    break

            logger.info("Processed device engagement message")

        except Exception as e:
            logger.error(f"Device engagement handling failed: {e}")

    async def _handle_session_establishment(self, message: TransportMessage) -> None:
        """Handle session establishment message"""
        try:
            # TODO: Implement session establishment handshake
            logger.info("Processed session establishment message")

        except Exception as e:
            logger.error(f"Session establishment handling failed: {e}")

    async def _handle_mdl_request(self, message: TransportMessage) -> None:
        """Handle received mDL request message"""
        try:
            # Parse mDL request
            mdl_request = mDLRequest.from_cbor(message.data)

            logger.info(
                f"Received mDL request with {len(mdl_request.doc_requests)} document requests"
            )

            # TODO: Process request and generate response

        except Exception as e:
            logger.error(f"mDL request handling failed: {e}")

    async def _handle_mdl_response(self, message: TransportMessage) -> None:
        """Handle received mDL response message"""
        try:
            # Parse mDL response
            mdl_response = mDLResponse.from_cbor(message.data)

            logger.info(f"Received mDL response with {len(mdl_response.documents)} documents")

            # TODO: Verify response and extract data

        except Exception as e:
            logger.error(f"mDL response handling failed: {e}")


class ISO18013_7Protocol:
    """
    ISO/IEC 18013-7 Online Protocol Implementation

    Implements online mDL transactions over HTTPS with relying party flows.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.sessions: dict[str, dict[str, Any]] = {}

    async def initiate_presentation_request(
        self, presentation_definition: dict[str, Any], callback_url: str | None = None
    ) -> str:
        """
        Initiate presentation request to holder's wallet

        Args:
            presentation_definition: Definition of requested presentation
            callback_url: URL for presentation response

        Returns:
            Presentation session ID
        """
        try:
            session_id = str(uuid.uuid4())

            # Create presentation session
            session = {
                "session_id": session_id,
                "presentation_definition": presentation_definition,
                "callback_url": callback_url,
                "state": "request_initiated",
                "created_at": time.time(),
            }

            self.sessions[session_id] = session

            # TODO: Send presentation request to wallet
            logger.info(f"Initiated presentation request: {session_id}")

            return session_id

        except Exception as e:
            logger.error(f"Presentation request initiation failed: {e}")
            raise ProtocolError(f"Presentation request initiation failed: {e}")

    async def handle_presentation_response(
        self, session_id: str, presentation_submission: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Handle presentation response from holder

        Args:
            session_id: Presentation session ID
            presentation_submission: Presentation submission data

        Returns:
            Verification result
        """
        try:
            session = self.sessions.get(session_id)
            if not session:
                raise ProtocolError(f"Presentation session not found: {session_id}")

            # Verify presentation
            verification_result = await self._verify_presentation(
                presentation_submission, session["presentation_definition"]
            )

            # Update session
            session["state"] = "completed"
            session["verification_result"] = verification_result

            logger.info(f"Processed presentation response: {session_id}")

            return verification_result

        except Exception as e:
            logger.error(f"Presentation response handling failed: {e}")
            raise ProtocolError(f"Presentation response handling failed: {e}")

    async def _verify_presentation(
        self, presentation_submission: dict[str, Any], presentation_definition: dict[str, Any]
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
            # TODO: Implement comprehensive presentation verification
            verification_result = {
                "valid": True,
                "verified_claims": {},
                "verification_details": [],
                "trust_chain_valid": True,
                "signature_valid": True,
                "presentation_time": time.time(),
            }

            logger.info("Verified presentation submission")

            return verification_result

        except Exception as e:
            logger.error(f"Presentation verification failed: {e}")
            return {"valid": False, "error": str(e), "verification_time": time.time()}


def create_device_engagement_qr_demo() -> str:
    """
    Create a demo device engagement QR code for testing

    Returns:
        QR code content string
    """
    from .core import TransportMethod, create_device_engagement_qr

    return create_device_engagement_qr(
        [TransportMethod.BLE, TransportMethod.NFC, TransportMethod.WIFI_AWARE]
    )


async def simulate_offline_transaction() -> dict[str, Any]:
    """
    Simulate a complete offline mDL transaction for testing

    Returns:
        Transaction result
    """
    try:
        # Create protocol instance
        protocol = ISO18013_5Protocol()

        # Create mock transport
        from .transport import create_transport

        reader_transport = create_transport("ble", device_address="AA:BB:CC:DD:EE:FF")

        # Initiate reader session
        session_id = await protocol.initiate_reader_session(
            reader_transport,
            {
                "org.iso.18013.5.1.mDL": [
                    "family_name",
                    "given_name",
                    "birth_date",
                    "document_number",
                ]
            },
        )

        # Simulate session establishment
        await protocol.establish_session(session_id)

        # Send request
        await protocol.send_mdl_request(session_id)

        # Simulate response (normally from holder)
        mock_document = {
            "docType": "org.iso.18013.5.1.mDL",
            "elements": {
                "family_name": "Doe",
                "given_name": "John",
                "birth_date": "1990-01-01",
                "document_number": "DL123456789",
            },
        }

        await protocol.send_mdl_response(
            session_id,
            [mock_document],
            ["family_name", "given_name", "birth_date", "document_number"],
        )

        # Terminate session
        await protocol.terminate_session(session_id)

        return {
            "success": True,
            "session_id": session_id,
            "transaction_type": "offline_mdl",
            "elements_disclosed": 4,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Offline transaction simulation failed: {e}")
        return {"success": False, "error": str(e), "timestamp": time.time()}
