#!/usr/bin/env python

from __future__ import annotations

"""
DTC Engine Service Implementation

This module implements the Digital Travel Credential (DTC) Engine service
which provides functionality for creating, managing, and verifying DTCs
according to ICAO standards.
"""

import datetime
import base64
import hashlib
import json
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import qrcode

# Import common utilities
from marty_plugin.common.config import Config
from marty_plugin.common import crypto_bridge
from marty_plugin.common.crypto import generate_hash
from marty_plugin.common.grpc_client import GRPCClient as GrpcClient
from marty_plugin.common.logging_config import get_logger
from marty_plugin.proto import document_signer_pb2
from marty_plugin.proto.document_signer_pb2_grpc import DocumentSignerStub

try:  # Prefer Rust bindings when available
    import marty_verification  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    marty_verification = None

# Import proto-generated modules
from marty_plugin.proto.dtc_engine_pb2 import (
    CreateDTCResponse,
    DTCResponse,
    GenerateDTCQRCodeResponse,
    LinkDTCToPassportResponse,
    RevokeDTCResponse,
    SignDTCResponse,
    TransferDTCToDeviceResponse,
    VerificationResult,
    VerifyDTCResponse,
    DTCType,
)
from marty_plugin.proto.dtc_engine_pb2_grpc import DTCEngineServicer
from marty_plugin.proto.passport_engine_pb2_grpc import PassportEngineStub

# Configure logger
logger = get_logger(__name__)


class DTCEngineService(DTCEngineServicer):
    """
    Implementation of Digital Travel Credential (DTC) Engine service.

    This service provides functionality for creating, managing, and verifying
    Digital Travel Credentials according to ICAO standards.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize the DTC Engine Service.

        Args:
            config: Configuration object with service settings
        """
        self.config = config
        self.data_dir = os.environ.get("DATA_DIR", "./data")
        self.dtc_storage_dir = Path(self.data_dir) / "dtc_store"

        # Create storage directory if it doesn't exist
        Path(self.dtc_storage_dir).mkdir(parents=True, exist_ok=True)

        # Initialize gRPC clients for dependent services
        self.document_signer_client = GrpcClient(
            service_name="document-signer",
            stub_class=DocumentSignerStub,
            config=config,
        )

        self.passport_engine_client = GrpcClient(
            service_name="passport-engine",
            stub_class=PassportEngineStub,
            config=config,
        )

        logger.info(f"DTC Engine Service initialized with data directory: {self.data_dir}")
        service_config = {}
        try:
            service_config = config.get_service("dtc_engine")
        except Exception:  # pragma: no cover - defensive
            service_config = {}

        self.signer_id = service_config.get("signer_id", "rust-dtc")
        self.signing_key_pem = os.environ.get("DTC_SIGNING_KEY_PEM")
        self.signer_public_key_pem = os.environ.get("DTC_SIGNER_PUBLIC_KEY_PEM")

        signing_key_path = service_config.get("signing_key_path") or os.environ.get(
            "DTC_SIGNING_KEY_PATH"
        )
        if signing_key_path and Path(signing_key_path).exists():
            self.signing_key_pem = Path(signing_key_path).read_text(encoding="utf-8")

        public_key_path = service_config.get("signer_public_key_path") or os.environ.get(
            "DTC_SIGNER_PUBLIC_KEY_PATH"
        )
        if public_key_path and Path(public_key_path).exists():
            self.signer_public_key_pem = Path(public_key_path).read_text(encoding="utf-8")

        if self.signing_key_pem and not self.signer_public_key_pem:
            try:
                private_der = crypto_bridge.load_private_key_pem(self.signing_key_pem)
                public_der = crypto_bridge.extract_public_key(private_der)
                self.signer_public_key_pem = crypto_bridge.save_public_key_pem(public_der)
            except Exception:  # pragma: no cover - defensive
                logger.warning("Failed to derive DTC public key from signing key")
        self.trust_anchors_pem = []
        self.certificate_chain_pem = []
        ta_path = service_config.get("trust_anchors_path") or os.environ.get("DTC_TRUST_ANCHORS_PATH")
        if ta_path and Path(ta_path).exists():
            try:
                self.trust_anchors_pem = Path(ta_path).read_text(encoding="utf-8").split("\n\n")
            except Exception:  # pragma: no cover - defensive
                logger.warning("Failed to load trust anchors from %s", ta_path)
        chain_path = service_config.get("certificate_chain_path") or os.environ.get("DTC_CERT_CHAIN_PATH")
        if chain_path and Path(chain_path).exists():
            try:
                self.certificate_chain_pem = Path(chain_path).read_text(encoding="utf-8").split(
                    "\n\n"
                )
            except Exception:  # pragma: no cover - defensive
                logger.warning("Failed to load certificate chain from %s", chain_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _encode_data_group(self, data: bytes) -> str:
        """Base64-encode data group content for JSON storage."""
        return base64.b64encode(data).decode("ascii")

    def _decode_data_group(self, data_b64: str) -> bytes:
        """Decode base64-encoded data group content."""
        return base64.b64decode(data_b64.encode("ascii"))

    def _build_type1_profile(self, request) -> dict[str, Any]:
        """Construct Type 1 profile payload, deriving MRZ lines and SOD hash."""
        mrz_line1 = request.type1_profile.mrz_line1 if request.type1_profile else ""
        mrz_line2 = request.type1_profile.mrz_line2 if request.type1_profile else ""
        sod_hash = request.type1_profile.sod_hash if request.type1_profile else ""
        passive_auth_ok = request.type1_profile.passive_auth_ok if request.type1_profile else False

        # Derive MRZ lines from passport_mrz if not provided
        if (not mrz_line1 or not mrz_line2) and request.passport_mrz:
            try:
                mrz_text = request.passport_mrz.decode("utf-8").strip().splitlines()
                if len(mrz_text) >= 2:
                    mrz_line1 = mrz_line1 or mrz_text[0][:44]
                    mrz_line2 = mrz_line2 or mrz_text[1][:44]
            except Exception:
                logger.warning("Failed to decode passport MRZ for Type 1 profile")

        if not mrz_line1 or not mrz_line2:
            msg = "Type 1 requires MRZ line1 and line2"
            raise ValueError(msg)

        # Compute SOD hash if missing using concatenated data group bytes
        if not sod_hash:
            dg_bytes = b"".join(dg.data for dg in request.data_groups if dg.data)
            if not dg_bytes and request.passport_mrz:
                dg_bytes = request.passport_mrz
            if not dg_bytes:
                msg = "Type 1 requires data groups or MRZ to derive SOD hash"
                raise ValueError(msg)
            sod_hash = hashlib.sha256(dg_bytes).hexdigest()

        return {
            "mrz_line1": mrz_line1,
            "mrz_line2": mrz_line2,
            "sod_hash": sod_hash,
            "issuing_state": request.issuing_authority,
            "passive_auth_ok": passive_auth_ok,
        }

    def _build_type2_profile(self, request) -> dict[str, Any]:
        """Construct Type 2 profile payload (chip/device bound)."""
        if not request.type2_profile.chip_auth_public_key:
            msg = "Type 2 requires chip_auth_public_key"
            raise ValueError(msg)

        return {
            "chip_auth_public_key": request.type2_profile.chip_auth_public_key,
            "device_public_key": request.type2_profile.device_public_key,
            "attestation_cert_hash": request.type2_profile.attestation_cert_hash,
            "passive_auth_ok": request.type2_profile.passive_auth_ok,
        }

    def _build_type3_profile(self, request) -> dict[str, Any]:
        """Construct Type 3 profile payload (wallet/device attestation)."""
        if not request.type3_profile.remote_attestation_report:
            msg = "Type 3 requires remote_attestation_report"
            raise ValueError(msg)

        return {
            "remote_attestation_report": request.type3_profile.remote_attestation_report,
            "device_binding_id": request.type3_profile.device_binding_id,
            "ephemeral_public_key": request.type3_profile.ephemeral_public_key,
            "session_id": request.type3_profile.session_id,
            "attestation_cert_hash": request.type3_profile.attestation_cert_hash,
        }

    def _canonical_type1_payload(self, dtc_data: dict[str, Any]) -> bytes:
        """Deterministic Type 1 payload used for signing."""
        type1 = dtc_data.get("type1_profile") or {}
        payload = {
            "dtc_id": dtc_data.get("dtc_id"),
            "issuing_authority": dtc_data.get("issuing_authority"),
            "issue_date": dtc_data.get("issue_date"),
            "expiry_date": dtc_data.get("expiry_date"),
            "mrz_line1": type1.get("mrz_line1"),
            "mrz_line2": type1.get("mrz_line2"),
            "sod_hash": type1.get("sod_hash"),
            "passive_auth_ok": type1.get("passive_auth_ok", False),
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    def _canonical_type2_payload(self, dtc_data: dict[str, Any]) -> bytes:
        type2 = dtc_data.get("type2_profile") or {}
        payload = {
            "dtc_id": dtc_data.get("dtc_id"),
            "issuing_authority": dtc_data.get("issuing_authority"),
            "issue_date": dtc_data.get("issue_date"),
            "expiry_date": dtc_data.get("expiry_date"),
            "chip_auth_public_key": type2.get("chip_auth_public_key"),
            "device_public_key": type2.get("device_public_key"),
            "attestation_cert_hash": type2.get("attestation_cert_hash"),
            "passive_auth_ok": type2.get("passive_auth_ok", False),
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    def _canonical_type3_payload(self, dtc_data: dict[str, Any]) -> bytes:
        type3 = dtc_data.get("type3_profile") or {}
        payload = {
            "dtc_id": dtc_data.get("dtc_id"),
            "issuing_authority": dtc_data.get("issuing_authority"),
            "issue_date": dtc_data.get("issue_date"),
            "expiry_date": dtc_data.get("expiry_date"),
            "remote_attestation_report": type3.get("remote_attestation_report"),
            "device_binding_id": type3.get("device_binding_id"),
            "ephemeral_public_key": type3.get("ephemeral_public_key"),
            "session_id": type3.get("session_id"),
            "attestation_cert_hash": type3.get("attestation_cert_hash"),
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    def _use_rust_dtc(self) -> bool:
        """Check if Rust DTC bindings are available."""
        return marty_verification is not None

    def _rust_create(self, request_json: str) -> dict[str, Any]:
        created = marty_verification.dtc_create(request_json)  # type: ignore[attr-defined]
        return json.loads(created)

    def _rust_sign(self, dtc_json: str) -> dict[str, Any]:
        signed = marty_verification.dtc_sign(dtc_json)  # type: ignore[attr-defined]
        return json.loads(signed)

    def _rust_verify(self, dtc_json: str) -> dict[str, Any]:
        verified = marty_verification.dtc_verify(dtc_json)  # type: ignore[attr-defined]
        return json.loads(verified)

    def _get_dtc_file_path(self, dtc_id: str) -> str:
        """
        Get the file path for a DTC storage file.

        Args:
            dtc_id: ID of the DTC

        Returns:
            File path for the DTC storage
        """
        return Path(self.dtc_storage_dir) / f"{dtc_id}.json"

    def _store_dtc(self, dtc_id: str, dtc_data: dict[str, Any]) -> bool:
        """
        Store DTC data to file.

        Args:
            dtc_id: ID of the DTC
            dtc_data: DTC data to store

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = self._get_dtc_file_path(dtc_id)
            with Path(file_path).open("w", encoding="utf-8") as f:
                json.dump(dtc_data, f, indent=2)
        except Exception:
            logger.exception(f"Error storing DTC {dtc_id}")
            return False
        else:
            return True

    def _load_dtc(self, dtc_id: str) -> dict[str, Any] | None:
        """
        Load DTC data from file.

        Args:
            dtc_id: ID of the DTC

        Returns:
            DTC data dictionary or None if not found
        """
        try:
            file_path = self._get_dtc_file_path(dtc_id)
            if not Path(file_path).exists():
                logger.error(f"DTC {dtc_id} not found")
                return None

            with Path(file_path).open(encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception(f"Error loading DTC {dtc_id}")
            return None

    def _check_access(self, dtc_data: dict[str, Any], access_key: str) -> bool:
        """
        Check if access to the DTC is allowed with the given access key.

        Args:
            dtc_data: DTC data
            access_key: Access key provided

        Returns:
            True if access is allowed, False otherwise
        """
        access_control = dtc_data.get("access_control", "NONE")

        # If no access control, always allow
        if access_control == "NONE":
            return True

        # If access control is enabled, check key
        if access_control in ["PASSWORD", "BIOMETRIC", "CERTIFICATE"]:
            stored_key = dtc_data.get("access_key", "")
            if not stored_key:
                return True  # If no key stored, allow access

            # For simplicity, just check direct match
            # In a real implementation, we'd handle different auth methods differently
            return access_key == stored_key

        return False  # Default deny

    def CreateDTC(self, request, context) -> CreateDTCResponse:
        """
        Create a new Digital Travel Credential from passport data.

        Args:
            request: CreateDTCRequest with passport data
            context: gRPC context

        Returns:
            CreateDTCResponse with DTC ID and status
        """
        try:
            if self._use_rust_dtc():
                payload = {
                    "passport_number": request.passport_number,
                    "issuing_authority": request.issuing_authority,
                    "issue_date": request.issue_date,
                    "expiry_date": request.expiry_date,
                    "personal_details": {
                        "first_name": request.personal_details.first_name,
                        "last_name": request.personal_details.last_name,
                        "date_of_birth": request.personal_details.date_of_birth,
                        "gender": request.personal_details.gender,
                        "nationality": request.personal_details.nationality,
                        "place_of_birth": request.personal_details.place_of_birth,
                        "portrait": self._encode_data_group(request.personal_details.portrait)
                        if request.personal_details.portrait
                        else "",
                        "signature": self._encode_data_group(request.personal_details.signature)
                        if request.personal_details.signature
                        else "",
                        "other_names": list(request.personal_details.other_names),
                    },
                    "data_groups": [
                        {
                            "dg_number": dg.dg_number,
                            "data": self._encode_data_group(dg.data),
                            "data_type": dg.data_type,
                        }
                        for dg in request.data_groups
                    ],
                    "dtc_type": request.dtc_type,
                    "access_control": request.access_control,
                    "access_key": request.access_key if request.access_key else None,
                    "dtc_valid_from": request.dtc_valid_from,
                    "dtc_valid_until": request.dtc_valid_until or request.expiry_date,
                    "type1_profile": request.type1_profile
                    if request.dtc_type == DTCType.TYPE1
                    else None,
                    "type2_profile": request.type2_profile
                    if request.dtc_type == DTCType.TYPE2
                    else None,
                    "type3_profile": request.type3_profile
                    if request.dtc_type == DTCType.TYPE3
                    else None,
                }
                created = self._rust_create(json.dumps(payload))
                dtc_id = created.get("dtc_id", "")
                if not dtc_id:
                    return CreateDTCResponse(
                        dtc_id="", status="ERROR", error_message="Rust DTC create failed"
                    )
                if self._store_dtc(dtc_id, created):
                    logger.info(f"[rust] Created DTC {dtc_id}")
                    return CreateDTCResponse(dtc_id=dtc_id, status="SUCCESS", error_message="")
                return CreateDTCResponse(
                    dtc_id="", status="FAILURE", error_message="Failed to store DTC data"
                )

            # Fallback: python path
            # Generate unique DTC ID
            dtc_id = str(uuid.uuid4())

            # Set current date if not provided
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            dtc_valid_from = request.dtc_valid_from if request.dtc_valid_from else current_date
            dtc_valid_until = (
                request.dtc_valid_until if request.dtc_valid_until else request.expiry_date
            )

            # Create DTC data structure
            dtc_data = {
                "dtc_id": dtc_id,
                "passport_number": request.passport_number,
                "issuing_authority": request.issuing_authority,
                "issue_date": request.issue_date,
                "expiry_date": request.expiry_date,
                "personal_details": {
                    "first_name": request.personal_details.first_name,
                    "last_name": request.personal_details.last_name,
                    "date_of_birth": request.personal_details.date_of_birth,
                    "gender": request.personal_details.gender,
                    "nationality": request.personal_details.nationality,
                    "place_of_birth": request.personal_details.place_of_birth,
                    "portrait": self._encode_data_group(request.personal_details.portrait)
                    if request.personal_details.portrait
                    else "",
                    "signature": self._encode_data_group(request.personal_details.signature)
                    if request.personal_details.signature
                    else "",
                    "other_names": list(request.personal_details.other_names),
                },
                "data_groups": [
                    {
                        "dg_number": dg.dg_number,
                        "data": self._encode_data_group(dg.data),
                        "data_type": dg.data_type,
                    }
                    for dg in request.data_groups
                ],
                "dtc_type": request.dtc_type,
                "access_control": request.access_control,
                "access_key": request.access_key if request.access_key else None,
                "dtc_valid_from": dtc_valid_from,
                "dtc_valid_until": dtc_valid_until,
                "type1_profile": None,
                "type2_profile": None,
                "type3_profile": None,
                "is_signed": False,
                "is_revoked": False,
                "linked_passport": None,
                "creation_date": current_date,
            }

            if request.dtc_type == DTCType.TYPE1:
                dtc_data["type1_profile"] = self._build_type1_profile(request)
            elif request.dtc_type == DTCType.TYPE2:
                dtc_data["type2_profile"] = self._build_type2_profile(request)
            elif request.dtc_type == DTCType.TYPE3:
                dtc_data["type3_profile"] = self._build_type3_profile(request)

            # Store DTC data
            if self._store_dtc(dtc_id, dtc_data):
                logger.info(f"Created DTC {dtc_id} for passport {request.passport_number}")
                return CreateDTCResponse(dtc_id=dtc_id, status="SUCCESS", error_message="")
            return CreateDTCResponse(
                dtc_id="", status="FAILURE", error_message="Failed to store DTC data"
            )

        except Exception:
            logger.exception("Error creating DTC")
            return CreateDTCResponse(dtc_id="", status="ERROR", error_message="Error creating DTC")

    def GetDTC(self, request, context) -> DTCResponse:
        """
        Get an existing DTC by ID.

        Args:
            request: GetDTCRequest with DTC ID
            context: gRPC context

        Returns:
            DTCResponse with DTC data
        """
        try:
            dtc_id = request.dtc_id
            access_key = request.access_key

            # Load DTC data
            dtc_data = self._load_dtc(dtc_id)
            if not dtc_data:
                return DTCResponse(status="NOT_FOUND", error_message=f"DTC {dtc_id} not found")

            # Check access permission
            if not self._check_access(dtc_data, access_key):
                return DTCResponse(
                    status="ACCESS_DENIED",
                    error_message="Access denied - invalid or missing access key",
                )

            # Convert DTC data to response object
            response = DTCResponse(
                dtc_id=dtc_id,
                passport_number=dtc_data.get("passport_number", ""),
                issuing_authority=dtc_data.get("issuing_authority", ""),
                issue_date=dtc_data.get("issue_date", ""),
                expiry_date=dtc_data.get("expiry_date", ""),
                dtc_type=dtc_data.get("dtc_type", 0),
                dtc_valid_from=dtc_data.get("dtc_valid_from", ""),
                dtc_valid_until=dtc_data.get("dtc_valid_until", ""),
                is_revoked=dtc_data.get("is_revoked", False),
                revocation_reason=dtc_data.get("revocation_reason", ""),
                revocation_date=dtc_data.get("revocation_date", ""),
                status="SUCCESS",
                error_message="",
            )

            # Add personal details
            pd = dtc_data.get("personal_details", {})
            response.personal_details.first_name = pd.get("first_name", "")
            response.personal_details.last_name = pd.get("last_name", "")
            response.personal_details.date_of_birth = pd.get("date_of_birth", "")
            response.personal_details.gender = pd.get("gender", "")
            response.personal_details.nationality = pd.get("nationality", "")
            response.personal_details.place_of_birth = pd.get("place_of_birth", "")
            portrait_stored = pd.get("portrait", b"")
            signature_stored = pd.get("signature", b"")
            try:
                response.personal_details.portrait = (
                    self._decode_data_group(portrait_stored)
                    if isinstance(portrait_stored, str)
                    else portrait_stored
                )
            except Exception:
                response.personal_details.portrait = b""
            try:
                response.personal_details.signature = (
                    self._decode_data_group(signature_stored)
                    if isinstance(signature_stored, str)
                    else signature_stored
                )
            except Exception:
                response.personal_details.signature = b""
            response.personal_details.other_names.extend(pd.get("other_names", []))

            # Add data groups
            for dg in dtc_data.get("data_groups", []):
                data_group = response.data_groups.add()
                data_group.dg_number = dg.get("dg_number", 0)
                stored_data = dg.get("data", b"")
                try:
                    data_group.data = (
                        self._decode_data_group(stored_data) if isinstance(stored_data, str) else stored_data
                    )
                except Exception:
                    data_group.data = b""
                data_group.data_type = dg.get("data_type", "")

            # Add signature info if available
            sig_info = dtc_data.get("signature_info", {})
            if sig_info:
                response.signature_info.signature_date = sig_info.get("signature_date", "")
                response.signature_info.signer_id = sig_info.get("signer_id", "")
                response.signature_info.signature = sig_info.get("signature", b"")
                response.signature_info.is_valid = sig_info.get("is_valid", False)

            # Add Type 1 profile if present
            type1 = dtc_data.get("type1_profile")
            if type1:
                response.type1_profile.mrz_line1 = type1.get("mrz_line1", "")
                response.type1_profile.mrz_line2 = type1.get("mrz_line2", "")
                response.type1_profile.sod_hash = type1.get("sod_hash", "")
                response.type1_profile.issuing_state = type1.get("issuing_state", "")
                response.type1_profile.passive_auth_ok = type1.get("passive_auth_ok", False)

            type2 = dtc_data.get("type2_profile")
            if type2:
                response.type2_profile.chip_auth_public_key = type2.get("chip_auth_public_key", "")
                response.type2_profile.device_public_key = type2.get("device_public_key", "")
                response.type2_profile.attestation_cert_hash = type2.get("attestation_cert_hash", "")
                response.type2_profile.passive_auth_ok = type2.get("passive_auth_ok", False)

            type3 = dtc_data.get("type3_profile")
            if type3:
                response.type3_profile.remote_attestation_report = type3.get(
                    "remote_attestation_report", ""
                )
                response.type3_profile.device_binding_id = type3.get("device_binding_id", "")
                response.type3_profile.ephemeral_public_key = type3.get("ephemeral_public_key", "")
                response.type3_profile.session_id = type3.get("session_id", "")
                response.type3_profile.attestation_cert_hash = type3.get("attestation_cert_hash", "")

        except Exception:
            logger.exception(f"Error getting DTC {request.dtc_id}")
            return DTCResponse(status="ERROR", error_message="Error getting DTC")
        else:
            return response

    def SignDTC(self, request, context) -> SignDTCResponse:
        """
        Sign a DTC using the Document Signer service.

        Args:
            request: SignDTCRequest with DTC ID
            context: gRPC context

        Returns:
            SignDTCResponse with signature info
        """
        try:
            dtc_id = request.dtc_id
            access_key = request.access_key

            # Load DTC data
            dtc_data = self._load_dtc(dtc_id)
            if not dtc_data:
                return SignDTCResponse(success=False, error_message=f"DTC {dtc_id} not found")

            # Check access permission
            if not self._check_access(dtc_data, access_key):
                return SignDTCResponse(
                    success=False, error_message="Access denied - invalid or missing access key"
                )

            # Check if already signed
            if dtc_data.get("is_signed", False):
                return SignDTCResponse(success=False, error_message="DTC is already signed")

            # Create the data to sign (in a real system, this would be more structured)
            if dtc_data.get("dtc_type") == DTCType.TYPE1 and not dtc_data.get("type1_profile"):
                return SignDTCResponse(
                    success=False, error_message="Type 1 DTC missing type1_profile"
                )

            # Prefer Rust signing path if available
            if self._use_rust_dtc() and self.signing_key_pem:
                try:
                    dtc_payload = dtc_data.copy()
                    dtc_payload["signing_key_pem"] = self.signing_key_pem
                    dtc_payload["signer_id"] = self.signer_id
                    signed = self._rust_sign(json.dumps(dtc_payload))
                    dtc_data.update(signed)
                    if self.signer_public_key_pem:
                        dtc_data.setdefault("signature_info", {})[
                            "signer_public_key_pem"
                        ] = self.signer_public_key_pem
                    if self._store_dtc(dtc_id, dtc_data):
                        response = SignDTCResponse(success=True, error_message="")
                        response.signature_info.signature_date = (
                            dtc_data.get("signature_info", {}).get("signature_date", "")
                        )
                        response.signature_info.signer_id = (
                            dtc_data.get("signature_info", {}).get("signer_id", "")
                        )
                        signature_value = dtc_data.get("signature_info", {}).get("signature", "")
                        if isinstance(signature_value, str):
                            try:
                                signature_bytes = base64.b64decode(signature_value)
                            except Exception:  # pragma: no cover - defensive
                                signature_bytes = signature_value.encode("utf-8")
                        elif isinstance(signature_value, (bytes, bytearray)):
                            signature_bytes = bytes(signature_value)
                        else:
                            signature_bytes = b""
                        response.signature_info.signature = signature_bytes
                        response.signature_info.is_valid = dtc_data.get("signature_info", {}).get(
                            "is_valid", False
                        )
                        return response
                    return SignDTCResponse(
                        success=False, error_message="Failed to update DTC after signing"
                    )
                except Exception:
                    logger.exception("Rust DTC signing failed, falling back to Python")

            # Canonical payload for signing (Python fallback)
            if dtc_data.get("dtc_type") == DTCType.TYPE1:
                data_to_sign = self._canonical_type1_payload(dtc_data)
            elif dtc_data.get("dtc_type") == DTCType.TYPE2:
                data_to_sign = self._canonical_type2_payload(dtc_data)
            elif dtc_data.get("dtc_type") == DTCType.TYPE3:
                data_to_sign = self._canonical_type3_payload(dtc_data)
            else:
                data_to_sign = json.dumps(
                    {
                        "dtc_id": dtc_id,
                        "passport_number": dtc_data.get("passport_number", ""),
                        "issuing_authority": dtc_data.get("issuing_authority", ""),
                        "issue_date": dtc_data.get("issue_date", ""),
                        "expiry_date": dtc_data.get("expiry_date", ""),
                        "dtc_valid_from": dtc_data.get("dtc_valid_from", ""),
                        "dtc_valid_until": dtc_data.get("dtc_valid_until", ""),
                    },
                    sort_keys=True,
                ).encode("utf-8")

            # Call Document Signer service to sign the data; fallback to local hash if unavailable
            try:
                signature_bytes: bytes
                signer_id = "DS_001"
                signature_date = datetime.datetime.now().isoformat()

                if self.document_signer_client:
                    # pylint: disable=no-member
                    signer_stub = self.document_signer_client.stub
                    sign_request = document_signer_pb2.SignRequest(
                        document_id=dtc_id, document_content=data_to_sign
                    )
                    sign_response = signer_stub.SignDocument(sign_request, timeout=5)
                    if not sign_response.success:
                        return SignDTCResponse(
                            success=False, error_message=sign_response.error_message
                        )
                    signature_bytes = sign_response.signature_info.signature
                    signer_id = sign_response.signature_info.signer_id or signer_id
                    signature_date = sign_response.signature_info.signature_date or signature_date
                else:
                    signature_bytes = generate_hash(data_to_sign)

                # Update DTC data with signature
                signature_info = {
                    "signature_date": signature_date,
                    "signer_id": signer_id,
                    "signature": signature_bytes,
                    "is_valid": True,
                }
                dtc_data["signature_info"] = signature_info
                dtc_data["is_signed"] = True

                # Store updated DTC
                if self._store_dtc(dtc_id, dtc_data):
                    logger.info(f"Signed DTC {dtc_id} successfully")

                    response = SignDTCResponse(success=True, error_message="")
                    response.signature_info.signature_date = signature_info["signature_date"]
                    response.signature_info.signer_id = signature_info["signer_id"]
                    response.signature_info.signature = signature_info["signature"]
                    response.signature_info.is_valid = signature_info["is_valid"]
                    return response
                return SignDTCResponse(
                    success=False, error_message="Failed to update DTC after signing"
                )

            except Exception:
                logger.exception(f"Error during signing DTC {dtc_id}")
                return SignDTCResponse(success=False, error_message="Error during signing")

        except Exception:
            logger.exception(f"Error signing DTC {request.dtc_id}")
            return SignDTCResponse(success=False, error_message="Error signing DTC")

    def RevokeDTC(self, request, context) -> RevokeDTCResponse:
        """
        Revoke a DTC.

        Args:
            request: RevokeDTCRequest with DTC ID and reason
            context: gRPC context

        Returns:
            RevokeDTCResponse with status
        """
        try:
            dtc_id = request.dtc_id
            reason = request.reason
            access_key = request.access_key

            # Load DTC data
            dtc_data = self._load_dtc(dtc_id)
            if not dtc_data:
                return RevokeDTCResponse(success=False, error_message=f"DTC {dtc_id} not found")

            # Check access permission
            if not self._check_access(dtc_data, access_key):
                return RevokeDTCResponse(
                    success=False, error_message="Access denied - invalid or missing access key"
                )

            # Check if already revoked
            if dtc_data.get("is_revoked", False):
                return RevokeDTCResponse(success=False, error_message="DTC is already revoked")

            # Update DTC with revocation info
            current_time = datetime.datetime.now().isoformat()
            dtc_data["is_revoked"] = True
            dtc_data["revocation_reason"] = reason
            dtc_data["revocation_date"] = current_time

            # Store updated DTC
            if self._store_dtc(dtc_id, dtc_data):
                logger.info(f"Revoked DTC {dtc_id} for reason: {reason}")
                return RevokeDTCResponse(
                    success=True, revocation_date=current_time, error_message=""
                )
            return RevokeDTCResponse(
                success=False, error_message="Failed to update DTC after revocation"
            )

        except Exception:
            logger.exception(f"Error revoking DTC {request.dtc_id}")
            return RevokeDTCResponse(success=False, error_message="Error revoking DTC")

    def GenerateDTCQRCode(self, request, context) -> GenerateDTCQRCodeResponse:
        """
        Generate QR code for offline verification of a DTC.

        Args:
            request: GenerateDTCQRCodeRequest with DTC ID
            context: gRPC context

        Returns:
            GenerateDTCQRCodeResponse with QR code image data
        """
        try:
            dtc_id = request.dtc_id
            include_portrait = request.include_portrait
            include_biometrics = request.include_biometrics
            dg_numbers = list(request.dg_numbers_to_include)
            access_key = request.access_key

            # Load DTC data
            dtc_data = self._load_dtc(dtc_id)
            if not dtc_data:
                return GenerateDTCQRCodeResponse(error_message=f"DTC {dtc_id} not found")

            # Check access permission
            if not self._check_access(dtc_data, access_key):
                return GenerateDTCQRCodeResponse(
                    error_message="Access denied - invalid or missing access key"
                )

            # Check if revoked
            if dtc_data.get("is_revoked", False):
                return GenerateDTCQRCodeResponse(
                    error_message="Cannot generate QR code for revoked DTC"
                )

            # Generate DTC data for QR code
            # In a real system, this would be more selective based on the request parameters
            qr_data = {
                "dtc_id": dtc_id,
                "passport_number": dtc_data.get("passport_number", ""),
                "issuing_authority": dtc_data.get("issuing_authority", ""),
                "issue_date": dtc_data.get("issue_date", ""),
                "expiry_date": dtc_data.get("expiry_date", ""),
                "dtc_valid_from": dtc_data.get("dtc_valid_from", ""),
                "dtc_valid_until": dtc_data.get("dtc_valid_until", ""),
                "personal_details": {
                    "first_name": dtc_data.get("personal_details", {}).get("first_name", ""),
                    "last_name": dtc_data.get("personal_details", {}).get("last_name", ""),
                    "date_of_birth": dtc_data.get("personal_details", {}).get("date_of_birth", ""),
                    "gender": dtc_data.get("personal_details", {}).get("gender", ""),
                    "nationality": dtc_data.get("personal_details", {}).get("nationality", ""),
                },
            }

            # Selectively include data groups based on request
            if dg_numbers:
                filtered_dgs = [
                    dg
                    for dg in dtc_data.get("data_groups", [])
                    if dg.get("dg_number", 0) in dg_numbers
                ]
                qr_data["data_groups"] = filtered_dgs

            # Include portrait if requested
            if include_portrait and dtc_data.get("personal_details", {}).get("portrait"):
                # In a real system, you'd use a more efficient encoding for binary data
                # This is just a placeholder approach
                qr_data["portrait"] = True

            # Include biometrics if requested
            if include_biometrics:
                # In a real system, you'd selectively include biometric data groups
                # This is just a placeholder
                qr_data["biometrics"] = True

            if dtc_data.get("type1_profile"):
                qr_data["type1_profile"] = dtc_data.get("type1_profile")

            # Generate QR code from the data
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )

            # Convert data to JSON string for QR code
            qr.add_data(json.dumps(qr_data))
            qr.make(fit=True)

            # Create QR code image
            img = qr.make_image(fill_color="black", back_color="white")

            # Convert image to bytes
            buffer = BytesIO()
            img.save(buffer)
            qr_bytes = buffer.getvalue()

            return GenerateDTCQRCodeResponse(qr_code=qr_bytes, error_message="")

        except Exception:
            logger.exception(f"Error generating QR code for DTC {request.dtc_id}")
            return GenerateDTCQRCodeResponse(error_message="Error generating QR code")

    def TransferDTCToDevice(self, request, context) -> TransferDTCToDeviceResponse:
        """
        Transfer a DTC to a mobile device.

        Args:
            request: TransferDTCToDeviceRequest with DTC ID and device info
            context: gRPC context

        Returns:
            TransferDTCToDeviceResponse with status
        """
        try:
            dtc_id = request.dtc_id
            device_id = request.device_id
            transfer_method = request.transfer_method
            access_key = request.access_key

            # Load DTC data
            dtc_data = self._load_dtc(dtc_id)
            if not dtc_data:
                return TransferDTCToDeviceResponse(
                    success=False, error_message=f"DTC {dtc_id} not found"
                )

            # Check access permission
            if not self._check_access(dtc_data, access_key):
                return TransferDTCToDeviceResponse(
                    success=False, error_message="Access denied - invalid or missing access key"
                )

            # Check if revoked
            if dtc_data.get("is_revoked", False):
                return TransferDTCToDeviceResponse(
                    success=False, error_message="Cannot transfer revoked DTC"
                )

            # In a real implementation, this would handle different transfer methods
            # For now, we just simulate a successful transfer
            logger.info(f"Transferring DTC {dtc_id} to device {device_id} via {transfer_method}")

            # Generate a transfer ID
            transfer_id = str(uuid.uuid4())

            # In a real system, we would:
            # 1. Establish connection with the device
            # 2. Authenticate the device
            # 3. Encrypt and transfer the DTC data
            # 4. Verify the transfer was successful
            # 5. Log the transfer

            # Here we just simulate a successful transfer
            return TransferDTCToDeviceResponse(
                success=True, transfer_id=transfer_id, error_message=""
            )

        except Exception:
            logger.exception(f"Error transferring DTC {request.dtc_id}")
            return TransferDTCToDeviceResponse(
                success=False, error_message="Error transferring DTC"
            )

    def VerifyDTC(self, request, context) -> VerifyDTCResponse:
        """
        Verify a DTC.

        Args:
            request: VerifyDTCRequest with DTC data
            context: gRPC context

        Returns:
            VerifyDTCResponse with verification results
        """
        try:
            # Initialize verification variables
            verification_results = []
            dtc_data = None
            dtc_id = None

            # Get DTC data based on request type
            if request.HasField("dtc_id"):
                dtc_id = request.dtc_id
                dtc_data = self._load_dtc(dtc_id)

                if not dtc_data:
                    return VerifyDTCResponse(
                        is_valid=False, error_message=f"DTC {dtc_id} not found"
                    )

                # Check access permission
                if not self._check_access(dtc_data, request.access_key):
                    return VerifyDTCResponse(
                        is_valid=False,
                        error_message="Access denied - invalid or missing access key",
                    )

            elif request.HasField("qr_code_data"):
                # Parse QR code data
                try:
                    # Decode QR code to get data
                    # In a real implementation, you would use a QR code decoder library
                    qr_data = json.loads(request.qr_code_data.decode("utf-8"))
                    dtc_id = qr_data.get("dtc_id")

                    # Load full DTC data from storage
                    dtc_data = self._load_dtc(dtc_id)
                    if not dtc_data:
                        return VerifyDTCResponse(
                            is_valid=False,
                            error_message=f"DTC {dtc_id} referenced in QR code not found",
                        )

                except Exception as e:
                    return VerifyDTCResponse(
                        is_valid=False, error_message=f"Invalid QR code data: {e!s}"
                    )

            elif request.HasField("device_data"):
                # Parse device data
                try:
                    # Decode device data
                    # In a real implementation, this would be a more complex protocol
                    device_data = json.loads(request.device_data.decode("utf-8"))
                    dtc_id = device_data.get("dtc_id")

                    # Load full DTC data from storage
                    dtc_data = self._load_dtc(dtc_id)
                    if not dtc_data:
                        return VerifyDTCResponse(
                            is_valid=False,
                            error_message=f"DTC {dtc_id} referenced in device data not found",
                        )

                except Exception as e:
                    return VerifyDTCResponse(
                        is_valid=False, error_message=f"Invalid device data: {e!s}"
                    )

            else:
                return VerifyDTCResponse(
                    is_valid=False, error_message="No DTC identification provided"
                )

            # Perform verification checks

            # 1. Check expiration
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            expiry_date = dtc_data.get("dtc_valid_until", "")
            is_expired = expiry_date < current_date if expiry_date else True

            verification_results.append(
                VerificationResult(
                    check_name="Expiration",
                    passed=not is_expired,
                    details="DTC is current" if not is_expired else "DTC has expired",
                )
            )

            # 2. Check if revoked
            is_revoked = dtc_data.get("is_revoked", False)
            verification_results.append(
                VerificationResult(
                    check_name="Revocation",
                    passed=not is_revoked,
                    details=(
                        "DTC is not revoked"
                        if not is_revoked
                        else f"DTC was revoked on {dtc_data.get('revocation_date', '')}"
                    ),
                )
            )

            # 3. Check signature if DTC is signed
            is_signed = dtc_data.get("is_signed", False)
            has_valid_signature = False

            if is_signed:
                sig_info = dtc_data.get("signature_info", {})
                has_signature = bool(sig_info.get("signature"))

                signer_public_key_pem = (
                    sig_info.get("signer_public_key_pem") or self.signer_public_key_pem
                )
                if self._use_rust_dtc() and signer_public_key_pem:
                    try:
                        payload = dtc_data.copy()
                        payload["signer_public_key_pem"] = signer_public_key_pem
                        if self.trust_anchors_pem:
                            payload["trust_anchors_pem"] = self.trust_anchors_pem
                        if self.certificate_chain_pem:
                            payload["certificate_chain_pem"] = self.certificate_chain_pem
                        verify_result = self._rust_verify(json.dumps(payload))
                        has_valid_signature = bool(
                            verify_result.get("is_valid", False)
                        )
                        verification_results.append(
                            VerificationResult(
                                check_name="Signature",
                                passed=has_valid_signature,
                                details="Rust binding verification"
                                if has_valid_signature
                                else "Rust binding signature check failed",
                            )
                        )
                    except Exception:
                        logger.exception("Rust DTC verification failed, falling back")

                if not has_valid_signature:
                    verification_results.append(
                        VerificationResult(
                            check_name="Signature",
                            passed=has_signature,
                            details=(
                                "DTC has signature"
                                if has_signature
                                else "DTC signature is missing"
                            ),
                        )
                    )
                    has_valid_signature = has_signature
            else:
                verification_results.append(
                    VerificationResult(
                        check_name="Signature", passed=False, details="DTC is not signed"
                    )
                )

            # 4. If Type 1, ensure MRZ hash presence
            if dtc_data.get("dtc_type") == DTCType.TYPE1:
                type1 = dtc_data.get("type1_profile") or {}
                has_type1 = bool(type1.get("mrz_line1") and type1.get("mrz_line2"))

                # Recompute SOD hash from stored data groups for consistency
                recomputed_hash = None
                try:
                    dg_bytes = b"".join(
                        self._decode_data_group(dg["data"])
                        for dg in dtc_data.get("data_groups", [])
                        if dg.get("data")
                    )
                    if dg_bytes:
                        recomputed_hash = hashlib.sha256(dg_bytes).hexdigest()
                except Exception:
                    recomputed_hash = None

                hash_matches = (
                    recomputed_hash == type1.get("sod_hash") if recomputed_hash else bool(type1.get("sod_hash"))
                )

                verification_results.append(
                    VerificationResult(
                        check_name="Type1Profile",
                        passed=has_type1 and hash_matches,
                        details=(
                            "Type 1 profile present and hashes consistent"
                            if has_type1 and hash_matches
                            else "Missing or inconsistent Type 1 profile"
                        ),
                    )

            # 5. If Type 2, ensure chip/device binding fields are present
            if dtc_data.get("dtc_type") == DTCType.TYPE2:
                type2 = dtc_data.get("type2_profile") or {}
                has_type2 = bool(type2.get("chip_auth_public_key") and type2.get("device_public_key"))
                verification_results.append(
                    VerificationResult(
                        check_name="Type2Profile",
                        passed=has_type2,
                        details=(
                            "Type 2 profile present"
                            if has_type2
                            else "Missing chip/device binding for Type 2"
                        ),
                    )
                )

            # 6. If Type 3, ensure attestation fields are present
            if dtc_data.get("dtc_type") == DTCType.TYPE3:
                type3 = dtc_data.get("type3_profile") or {}
                has_type3 = bool(
                    type3.get("remote_attestation_report") and type3.get("device_binding_id")
                )
                verification_results.append(
                    VerificationResult(
                        check_name="Type3Profile",
                        passed=has_type3,
                        details=(
                            "Type 3 profile present"
                            if has_type3
                            else "Missing attestation/binding for Type 3"
                        ),
                    )
                )
                )

            # 4. Check passport link if requested
            if request.check_passport_link and request.passport_number:
                linked_passport = dtc_data.get("linked_passport")
                has_valid_link = linked_passport == request.passport_number

                verification_results.append(
                    VerificationResult(
                        check_name="Passport Link",
                        passed=has_valid_link,
                        details=(
                            "DTC is linked to the provided passport"
                            if has_valid_link
                            else "DTC is not linked to the provided passport"
                        ),
                    )
                )

            # Determine overall validity
            # DTC is valid if:
            # - Not expired
            # - Not revoked
            # - Has valid signature
            # - Links to passport (if requested)
            is_valid = not is_expired and not is_revoked and has_valid_signature

            # Create DTC response object
            dtc_response = DTCResponse(
                dtc_id=dtc_id,
                passport_number=dtc_data.get("passport_number", ""),
                issuing_authority=dtc_data.get("issuing_authority", ""),
                issue_date=dtc_data.get("issue_date", ""),
                expiry_date=dtc_data.get("expiry_date", ""),
                dtc_type=dtc_data.get("dtc_type", 0),
                dtc_valid_from=dtc_data.get("dtc_valid_from", ""),
                dtc_valid_until=dtc_data.get("dtc_valid_until", ""),
                is_revoked=dtc_data.get("is_revoked", False),
                revocation_reason=dtc_data.get("revocation_reason", ""),
                revocation_date=dtc_data.get("revocation_date", ""),
                status="VALID" if is_valid else "INVALID",
                error_message="",
            )

            # Add personal details
            pd = dtc_data.get("personal_details", {})
            dtc_response.personal_details.first_name = pd.get("first_name", "")
            dtc_response.personal_details.last_name = pd.get("last_name", "")
            dtc_response.personal_details.date_of_birth = pd.get("date_of_birth", "")
            dtc_response.personal_details.gender = pd.get("gender", "")
            dtc_response.personal_details.nationality = pd.get("nationality", "")

            # Return verification response
            response = VerifyDTCResponse(is_valid=is_valid, dtc_data=dtc_response, error_message="")

            # Add verification results
            response.verification_results.extend(verification_results)

        except Exception:
            logger.exception("Error verifying DTC")
            return VerifyDTCResponse(is_valid=False, error_message="Error verifying DTC")
        else:
            return response

    def LinkDTCToPassport(self, request, context) -> LinkDTCToPassportResponse:
        """
        Link a DTC to a physical passport.

        Args:
            request: LinkDTCToPassportRequest with DTC ID and passport info
            context: gRPC context

        Returns:
            LinkDTCToPassportResponse with status
        """
        try:
            dtc_id = request.dtc_id
            passport_number = request.passport_number
            access_key = request.access_key
            passport_mrz_data = request.passport_mrz_data

            # Load DTC data
            dtc_data = self._load_dtc(dtc_id)
            if not dtc_data:
                return LinkDTCToPassportResponse(
                    success=False, error_message=f"DTC {dtc_id} not found"
                )

            # Check access permission
            if not self._check_access(dtc_data, access_key):
                return LinkDTCToPassportResponse(
                    success=False, error_message="Access denied - invalid or missing access key"
                )

            # Verify passport number against DTC
            dtc_passport_number = dtc_data.get("passport_number", "")
            if dtc_passport_number != passport_number:
                return LinkDTCToPassportResponse(
                    success=False,
                    error_message=f"Passport number mismatch: DTC was created for passport {dtc_passport_number}",
                )

            # In a real system, we would verify the passport MRZ data
            # For this implementation, we'll just check that it exists
            if passport_mrz_data and len(passport_mrz_data) > 0:
                # Verify MRZ data
                # This would involve checking against the Passport Engine service
                # For now, we'll just simulate successful verification
                pass

            # Update DTC with passport link
            dtc_data["linked_passport"] = passport_number
            dtc_data["link_date"] = datetime.datetime.now().isoformat()

            # Store updated DTC
            if self._store_dtc(dtc_id, dtc_data):
                logger.info(f"Linked DTC {dtc_id} to passport {passport_number}")
                return LinkDTCToPassportResponse(
                    success=True, link_date=dtc_data["link_date"], error_message=""
                )
            return LinkDTCToPassportResponse(
                success=False, error_message="Failed to update DTC after linking"
            )

        except Exception:
            logger.exception(f"Error linking DTC {request.dtc_id} to passport")
            return LinkDTCToPassportResponse(
                success=False, error_message="Error linking DTC to passport"
            )
