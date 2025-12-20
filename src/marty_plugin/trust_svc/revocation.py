"""
Revocation Processing Service

Handles CRL parsing, OCSP checking, and DSC revocation status management.

This module uses Rust implementations from marty-verification for core cryptographic
operations (CRL parsing, OCSP request building/response parsing) while maintaining
Python async HTTP handling for network operations.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from sqlalchemy import text  # Added for raw SQL queries
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtensionOID

from .database import DatabaseManager
from .models import RevocationStatus

# Import Rust bindings for OCSP/CRL operations (required)
from marty_plugin.common.crypto_bridge import (
    parse_crl as rust_parse_crl,
    build_ocsp_request as rust_build_ocsp_request,
    parse_ocsp_response as rust_parse_ocsp_response,
    get_ocsp_responder_url as rust_get_ocsp_responder_url,
    check_certificate_revocation as rust_check_revocation,
)

logger = logging.getLogger(__name__)


class RevocationProcessor:
    """Processes certificate revocation lists and OCSP responses."""

    def __init__(self, db_manager: DatabaseManager, ocsp_timeout: int = 10):
        self.db_manager = db_manager
        self.ocsp_timeout = ocsp_timeout
        self.session: aiohttp.ClientSession | None = None
        logger.info("Using Rust bindings for OCSP/CRL operations")

    async def initialize(self) -> None:
        """Initialize HTTP session for OCSP requests."""
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.ocsp_timeout))

    async def close(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()

    async def process_crl(self, crl_data: bytes, issuer_dn: str) -> dict[str, Any]:
        """
        Process a Certificate Revocation List.

        Args:
            crl_data: Raw CRL data (DER or PEM)
            issuer_dn: Issuer distinguished name

        Returns:
            Dictionary with processing results
        """
        try:
            # Parse CRL
            if crl_data.startswith(b"-----BEGIN"):
                crl = x509.load_pem_x509_crl(crl_data)
            else:
                crl = x509.load_der_x509_crl(crl_data)

            # Extract CRL metadata
            this_update = crl.last_update
            next_update = crl.next_update
            crl_number = None

            # Extract CRL number if present
            try:
                crl_number_ext = crl.extensions.get_extension_for_oid(ExtensionOID.CRL_NUMBER).value
                crl_number = crl_number_ext.crl_number
            except x509.ExtensionNotFound:
                pass

            # Generate CRL hash
            crl_hash = hashlib.sha256(crl_data).hexdigest()

            # Store CRL in cache
            crl_cache_data = {
                "issuer_dn": issuer_dn,
                "issuer_certificate_hash": None,  # TODO: Link to issuer certificate
                "crl_url": None,
                "crl_number": crl_number,
                "this_update": this_update,
                "next_update": next_update,
                "crl_data": crl_data,
                "crl_hash": crl_hash,
                "signature_valid": True,  # TODO: Verify signature
                "revoked_count": len(crl),
                "status": "active",
            }

            crl_id = await self.db_manager.add_crl(crl_cache_data)

            # Process revoked certificates
            revoked_certificates = []
            updated_dscs = 0

            for revoked_cert in crl:
                serial_number = format(revoked_cert.serial_number, "X")
                revocation_date = revoked_cert.revocation_date

                # Extract reason code if present
                reason_code = None
                try:
                    reason_ext = revoked_cert.extensions.get_extension_for_oid(
                        ExtensionOID.CRL_REASON
                    ).value
                    reason_code = reason_ext.reason.value
                except x509.ExtensionNotFound:
                    pass

                revoked_certificates.append(
                    {
                        "serial_number": serial_number,
                        "revocation_date": revocation_date,
                        "reason_code": reason_code,
                    }
                )

                # Update corresponding DSC status
                await self._update_dsc_from_revocation(
                    serial_number, revocation_date, reason_code, "CRL"
                )
                updated_dscs += 1

            # Add revoked certificates to database
            await self._add_revoked_certificates(crl_id, revoked_certificates)

            logger.info(
                f"Processed CRL for {issuer_dn}: {len(revoked_certificates)} revoked certificates, "
                f"{updated_dscs} DSCs updated"
            )

            return {
                "success": True,
                "crl_id": crl_id,
                "issuer_dn": issuer_dn,
                "this_update": this_update,
                "next_update": next_update,
                "revoked_count": len(revoked_certificates),
                "updated_dscs": updated_dscs,
            }

        except Exception as e:
            logger.error(f"Failed to process CRL for {issuer_dn}: {e}")
            return {"success": False, "error": str(e), "issuer_dn": issuer_dn}

    async def check_ocsp_status(
        self, certificate: x509.Certificate, issuer_certificate: x509.Certificate, ocsp_url: str
    ) -> dict[str, Any]:
        """
        Check certificate status via OCSP.

        Args:
            certificate: Certificate to check
            issuer_certificate: Issuer certificate
            ocsp_url: OCSP responder URL

        Returns:
            Dictionary with OCSP response data
        """
        if not self.session:
            await self.initialize()

        try:
            # Get DER bytes for both certificates
            cert_der = certificate.public_bytes(serialization.Encoding.DER)
            issuer_der = issuer_certificate.public_bytes(serialization.Encoding.DER)
            
            # Build OCSP request using Rust
            request_der = rust_build_ocsp_request(cert_der, issuer_der)

            # Send OCSP request
            async with self.session.post(
                ocsp_url,
                data=request_der,
                headers={"Content-Type": "application/ocsp-request"},
            ) as response:
                if response.status != 200:
                    raise ValueError(f"OCSP request failed with status {response.status}")

                response_data = await response.read()

            # Parse OCSP response using Rust
            parsed = rust_parse_ocsp_response(response_data)
            status_str = parsed.get("status", "unknown")
            if status_str == "good":
                status = RevocationStatus.GOOD
                revocation_date = None
                reason_code = None
            elif status_str == "revoked":
                status = RevocationStatus.BAD
                revocation_date_str = parsed.get("revocation_time")
                revocation_date = (
                    datetime.fromisoformat(revocation_date_str.replace("Z", "+00:00"))
                    if revocation_date_str
                    else None
                )
                reason_code = parsed.get("revocation_reason")
            else:
                status = RevocationStatus.UNKNOWN
                revocation_date = None
                reason_code = None

            # Update DSC status
            cert_hash = hashlib.sha256(cert_der).hexdigest()
            await self.db_manager.update_dsc_revocation_status(
                cert_hash, status, revocation_date, reason_code, "OCSP"
            )

            logger.info(f"OCSP check for certificate {cert_hash}: {status.value}")

            return {
                "success": True,
                "certificate_hash": cert_hash,
                "status": status.value,
                "revocation_date": revocation_date,
                "reason_code": reason_code,
                "ocsp_url": ocsp_url,
                "checked_at": datetime.now(timezone.utc),
            }

        except Exception as e:
            logger.error(f"OCSP check failed for {ocsp_url}: {e}")
            return {"success": False, "error": str(e), "ocsp_url": ocsp_url}

    def check_revocation_against_crl(
        self, certificate: x509.Certificate, issuer_dn: str, crl_der: bytes
    ) -> tuple[bool, str | None]:
        """
        Check if a certificate is revoked according to a CRL using Rust.
        
        This is a synchronous method that uses Rust for fast revocation checking
        without parsing the entire CRL in Python.

        Args:
            certificate: Certificate to check
            issuer_dn: Issuer distinguished name
            crl_der: DER-encoded CRL data

        Returns:
            Tuple of (is_revoked: bool, reason: Optional[str])
        """
        
        serial_number = format(certificate.serial_number, "X")
        return rust_check_revocation(serial_number, issuer_dn, crl_der)

    def get_ocsp_url_from_certificate(self, certificate: x509.Certificate) -> str | None:
        """
        Extract OCSP responder URL from certificate's AIA extension.
        
        Uses Rust for fast extraction.

        Args:
            certificate: Certificate to extract URL from

        Returns:
            OCSP responder URL or None if not present
        """
        cert_der = certificate.public_bytes(serialization.Encoding.DER)
        return rust_get_ocsp_responder_url(cert_der)

    async def refresh_all_crls(self, force: bool = False) -> dict[str, Any]:
        """
        Refresh all CRLs from known sources.

        Args:
            force: Force refresh even if CRL is still valid

        Returns:
            Summary of refresh operations
        """
        results = {
            "success": True,
            "crls_processed": 0,
            "crls_failed": 0,
            "total_revoked": 0,
            "updated_dscs": 0,
            "errors": [],
        }

        try:
            # Get active CRLs to determine which need refresh
            active_crls = await self.db_manager.get_active_crls()
            now = datetime.now(timezone.utc)

            for crl_data in active_crls:
                # Check if refresh is needed
                if not force and crl_data["next_update"] > now:
                    continue

                # TODO: Fetch CRL from URL if available
                if crl_data["crl_url"]:
                    crl_result = await self._fetch_crl_from_url(crl_data["crl_url"])
                    if crl_result["success"]:
                        process_result = await self.process_crl(
                            crl_result["data"], crl_data["issuer_dn"]
                        )

                        if process_result["success"]:
                            results["crls_processed"] += 1
                            results["total_revoked"] += process_result["revoked_count"]
                            results["updated_dscs"] += process_result["updated_dscs"]
                        else:
                            results["crls_failed"] += 1
                            results["errors"].append(process_result.get("error", "Unknown error"))
                    else:
                        results["crls_failed"] += 1
                        results["errors"].append(crl_result.get("error", "Failed to fetch CRL"))

            if results["crls_failed"] > 0:
                results["success"] = False

            logger.info(
                f"CRL refresh completed: {results['crls_processed']} processed, "
                f"{results['crls_failed']} failed"
            )

        except Exception as e:
            logger.error(f"CRL refresh failed: {e}")
            results["success"] = False
            results["errors"].append(str(e))

        return results

    async def _fetch_crl_from_url(self, crl_url: str) -> dict[str, Any]:
        """Fetch CRL from HTTP(S) URL."""
        if not self.session:
            await self.initialize()

        try:
            async with self.session.get(crl_url) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")

                crl_data = await response.read()

                return {"success": True, "data": crl_data, "url": crl_url}

        except Exception as e:
            return {"success": False, "error": str(e), "url": crl_url}

    async def _update_dsc_from_revocation(
        self, serial_number: str, revocation_date: datetime, reason_code: int | None, source: str
    ) -> None:
        """Update DSC revocation status from CRL entry."""
        # Find DSC by serial number
        dscs = await self.db_manager.get_dsc_certificates()

        for dsc_data in dscs:
            if dsc_data["serial_number"] == serial_number:
                await self.db_manager.update_dsc_revocation_status(
                    dsc_data["certificate_hash"],
                    RevocationStatus.BAD,
                    revocation_date,
                    reason_code,
                    source,
                )
                break

    async def _add_revoked_certificates(
        self, crl_id: str, revoked_certificates: list[dict[str, Any]]
    ) -> None:
        """Add revoked certificates to database."""
        async with self.db_manager.get_session() as session:
            for revoked_cert in revoked_certificates:
                query = text(
                    """
                    INSERT INTO trust_svc.revoked_certificates
                    (crl_id, serial_number, revocation_date, reason_code)
                    VALUES (:crl_id, :serial_number, :revocation_date, :reason_code)
                    ON CONFLICT (crl_id, serial_number) DO NOTHING
                """
                )

                await session.execute(
                    query,
                    {
                        "crl_id": crl_id,
                        "serial_number": revoked_cert["serial_number"],
                        "revocation_date": revoked_cert["revocation_date"],
                        "reason_code": revoked_cert["reason_code"],
                    },
                )

            await session.commit()

    async def check_certificate_revocation_status(
        self, certificate_hash: str, check_ocsp: bool = False
    ) -> dict[str, Any]:
        """
        Check comprehensive revocation status for a certificate.

        Args:
            certificate_hash: SHA256 hash of certificate
            check_ocsp: Whether to perform OCSP check

        Returns:
            Comprehensive revocation status
        """
        # Get DSC from database
        dscs = await self.db_manager.get_dsc_certificates(certificate_hash=certificate_hash)

        if not dscs:
            return {
                "found": False,
                "certificate_hash": certificate_hash,
                "error": "Certificate not found",
            }

        dsc = dscs[0]

        # Check CRL status
        crl_status = await self._check_crl_status(dsc["serial_number"], dsc["issuer_dn"])

        # Check OCSP if requested and URL available
        ocsp_status = None
        if check_ocsp:
            # TODO: Extract OCSP URL from certificate extensions
            ocsp_url = self._extract_ocsp_url(dsc["certificate_data"])
            if ocsp_url:
                # TODO: Get issuer certificate
                pass

        # Determine final status
        final_status = RevocationStatus.UNKNOWN
        if crl_status["found"]:
            if crl_status["revoked"]:
                final_status = RevocationStatus.BAD
            else:
                final_status = RevocationStatus.GOOD

        if ocsp_status and ocsp_status["success"]:
            final_status = RevocationStatus(ocsp_status["status"])

        return {
            "found": True,
            "certificate_hash": certificate_hash,
            "serial_number": dsc["serial_number"],
            "current_status": final_status.value,
            "last_checked": dsc["revocation_checked_at"],
            "crl_status": crl_status,
            "ocsp_status": ocsp_status,
            "sources": {"crl": dsc["crl_source"], "ocsp": dsc["ocsp_source"]},
        }

    async def _check_crl_status(self, serial_number: str, issuer_dn: str) -> dict[str, Any]:
        """Check if certificate is in any current CRL."""
        async with self.db_manager.get_session() as session:
            query = text(
                """
                SELECT rc.revocation_date, rc.reason_code, cc.this_update, cc.next_update
                FROM trust_svc.revoked_certificates rc
                JOIN trust_svc.crl_cache cc ON rc.crl_id = cc.id
                WHERE rc.serial_number = :serial_number
                AND cc.issuer_dn = :issuer_dn
                AND cc.status = 'active'
                AND NOW() BETWEEN cc.this_update AND cc.next_update
                ORDER BY cc.this_update DESC
                LIMIT 1
            """
            )

            result = await session.execute(
                query, {"serial_number": serial_number, "issuer_dn": issuer_dn}
            )

            row = result.fetchone()

            if row:
                return {
                    "found": True,
                    "revoked": True,
                    "revocation_date": row.revocation_date,
                    "reason_code": row.reason_code,
                    "crl_this_update": row.this_update,
                    "crl_next_update": row.next_update,
                }
            else:
                # Check if there's an active CRL for this issuer
                crl_query = text(
                    """
                    SELECT this_update, next_update FROM trust_svc.crl_cache
                    WHERE issuer_dn = :issuer_dn
                    AND status = 'active'
                    AND NOW() BETWEEN this_update AND next_update
                    ORDER BY this_update DESC
                    LIMIT 1
                """
                )

                crl_result = await session.execute(crl_query, {"issuer_dn": issuer_dn})
                crl_row = crl_result.fetchone()

                return {
                    "found": crl_row is not None,
                    "revoked": False,
                    "crl_this_update": crl_row.this_update if crl_row else None,
                    "crl_next_update": crl_row.next_update if crl_row else None,
                }

    def _extract_ocsp_url(self, certificate_data: bytes) -> str | None:
        """Extract OCSP URL from certificate Authority Information Access extension."""
        try:
            cert = x509.load_der_x509_certificate(certificate_data)

            try:
                aia_ext = cert.extensions.get_extension_for_oid(
                    ExtensionOID.AUTHORITY_INFORMATION_ACCESS
                ).value

                for access_description in aia_ext:
                    if access_description.access_method == x509.AuthorityInformationAccessOID.OCSP:
                        return access_description.access_location.value

            except x509.ExtensionNotFound:
                pass

        except Exception as e:
            logger.warning(f"Failed to extract OCSP URL: {e}")

        return None
