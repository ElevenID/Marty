"""
Service for handling Certificate Revocation List (CRL) operations
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

import aiosqlite
from app.core.config import settings
from app.db.database import DatabaseManager
from app.models.pkd_models import (
    CrlResponse,
    CrlUploadResponse,
    RevokedCertificate,
    UploadStatus,
)
from app.utils.asn1_utils import ASN1Decoder, ASN1Encoder

from marty_plugin.native_backends import NativeOperationError, require_backend

logger = logging.getLogger(__name__)


class CRLService:
    """Service for managing Certificate Revocation Lists"""

    def __init__(
        self,
        db_connection: aiosqlite.Connection | None = None,
        issuer_certificate_resolver: Callable[[str], Awaitable[bytes | None]]
        | None = None,
    ) -> None:
        """Initialize with optional database connection"""
        self.db_connection = db_connection
        self.issuer_certificate_resolver = issuer_certificate_resolver

    async def get_crl(self, country: str | None = None) -> CrlResponse:
        """
        Retrieve CRL data, optionally filtered by country.
        """
        # Try to get CRL from database
        issuer_filter = None
        if country:
            issuer_filter = f"CN=CSCA-{country}"

        crl_dict = await DatabaseManager.get_crl(issuer_filter)

        if crl_dict:
            # Convert database dictionary to CrlResponse
            revoked_certs = []
            for revoked_dict in crl_dict.get("revoked_certificates", []):
                revoked_certs.append(
                    RevokedCertificate(
                        serial_number=revoked_dict["serial_number"],
                        revocation_date=revoked_dict["revocation_date"],
                        reason_code=revoked_dict["reason_code"],
                    )
                )

            return CrlResponse(
                id=uuid.UUID(crl_dict["id"]),
                version=1,
                created=datetime.now(),
                issuer=crl_dict["issuer"],
                this_update=crl_dict["this_update"],
                next_update=crl_dict["next_update"],
                revoked_certificates=revoked_certs,
            )
        raise NativeOperationError("No CRL is available for the requested issuer")

    async def get_crl_binary(self, country: str | None = None) -> bytes:
        """
        Get the ASN.1 encoded CRL data, optionally filtered by country.
        """
        # Get the CRL data
        crl = await self.get_crl(country)

        # Encode the CRL as ASN.1
        return ASN1Encoder.encode_crl(
            issuer=crl.issuer,
            this_update=crl.this_update,
            next_update=crl.next_update,
            revoked_certs=crl.revoked_certificates,
        )

    async def upload_crl(self, crl_data: bytes) -> CrlUploadResponse:
        """
        Process and store an uploaded CRL.
        """
        try:
            # Parse the ASN.1 CRL data
            issuer, this_update, next_update, revoked_certs = ASN1Decoder.decode_crl(
                crl_data
            )
            if self.issuer_certificate_resolver is None:
                raise NativeOperationError(
                    "CRL issuer certificate resolver is not configured"
                )
            issuer_certificate_der = await self.issuer_certificate_resolver(issuer)
            if issuer_certificate_der is None:
                raise NativeOperationError("CRL issuer certificate was not found")
            native = require_backend("marty_verification")
            der_data = ASN1Decoder._pem_to_der(crl_data)
            if not native.verify_crl_signature(der_data, issuer_certificate_der):
                raise NativeOperationError("CRL signature verification failed")

            # Save the raw CRL file to file system
            storage_path = settings.CRL_PATH
            os.makedirs(storage_path, exist_ok=True)

            crl_filename = f"crl-{datetime.now().strftime('%Y%m%d%H%M%S')}.crl"
            crl_path = os.path.join(storage_path, crl_filename)
            with open(crl_path, "wb") as f:
                f.write(crl_data)

            # Store in database
            crl_dict = {
                "issuer": issuer,
                "this_update": this_update,
                "next_update": next_update,
                "crl_data": der_data,
                "revoked_certificates": [
                    {
                        "serial_number": cert.serial_number,
                        "revocation_date": cert.revocation_date,
                        "reason_code": cert.reason_code,
                    }
                    for cert in revoked_certs
                ],
            }

            await DatabaseManager.store_crl(crl_dict)

            # Log the operation
            revoked_count = len(revoked_certs)
            logger.info(f"Processed CRL with {revoked_count} revoked certificates")

            return CrlUploadResponse(
                id=uuid.uuid4(),
                version=1,
                created=datetime.now(),
                status=UploadStatus.PROCESSED,
                revoked_count=revoked_count,
            )

        except Exception as e:
            logger.exception(f"Failed to process CRL: {e}")
            return CrlUploadResponse(
                id=uuid.uuid4(),
                version=0,
                created=datetime.now(),
                status=UploadStatus.ERROR,
                revoked_count=0,
            )
