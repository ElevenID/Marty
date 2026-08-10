"""
Revocation Processing Service

Handles CRL parsing, OCSP checking, and DSC revocation status management.

This module uses Rust implementations from marty-verification for core cryptographic
operations (CRL parsing, OCSP request building/response parsing) while maintaining
Python async HTTP handling for network operations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp
from sqlalchemy import text  # Added for raw SQL queries

from marty_plugin.native_backends import require_backend

from .database import DatabaseManager
from .models import RevocationStatus

logger = logging.getLogger(__name__)


class RevocationProcessor:
    """Processes certificate revocation lists and OCSP responses."""

    def __init__(self, db_manager: DatabaseManager, ocsp_timeout: int = 10):
        self.native = require_backend("marty_verification")
        self.db_manager = db_manager
        self.ocsp_timeout = ocsp_timeout
        self.session: aiohttp.ClientSession | None = None
        logger.info("Using Rust bindings for OCSP/CRL operations")

    async def initialize(self) -> None:
        """Initialize HTTP session for OCSP requests."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.ocsp_timeout)
        )

    async def close(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()

    async def process_crl(
        self,
        crl_data: bytes,
        issuer_dn: str,
        issuer_certificate_der: bytes | None = None,
    ) -> dict[str, Any]:
        """
        Process a Certificate Revocation List.

        Args:
            crl_data: Raw CRL data (DER or PEM)
            issuer_dn: Issuer distinguished name

        Returns:
            Dictionary with processing results
        """
        try:
            der_data = self._crl_der(crl_data)
            crl = self.native.parse_crl(der_data)
            if self._normalize_dn(crl.issuer) != self._normalize_dn(issuer_dn):
                raise ValueError("CRL issuer does not match the expected issuer")
            if issuer_certificate_der is None:
                raise ValueError(
                    "Issuer certificate is required for CRL signature verification"
                )
            if not self.native.verify_crl_signature(der_data, issuer_certificate_der):
                raise ValueError("CRL signature verification failed")

            this_update = self._parse_datetime(crl.this_update)
            next_update = self._parse_datetime(crl.next_update)
            crl_number = crl.crl_number
            crl_hash = bytes(self.native.hash_data("sha256", der_data)).hex()
            native_revoked = list(crl.revoked_certificates())

            # Store CRL in cache
            crl_cache_data = {
                "issuer_dn": issuer_dn,
                "issuer_certificate_hash": None,  # TODO: Link to issuer certificate
                "crl_url": None,
                "crl_number": crl_number,
                "this_update": this_update,
                "next_update": next_update,
                "crl_data": der_data,
                "crl_hash": crl_hash,
                "signature_valid": True,
                "revoked_count": len(native_revoked),
                "status": "active",
            }

            crl_id = await self.db_manager.add_crl(crl_cache_data)

            # Process revoked certificates
            revoked_certificates = []
            updated_dscs = 0

            for revoked_cert in native_revoked:
                serial_number = revoked_cert.serial_number
                revocation_date = self._parse_datetime(revoked_cert.revocation_date)
                reason_code = self._reason_code(revoked_cert.reason)

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
        self, certificate_der: bytes, issuer_certificate_der: bytes, ocsp_url: str
    ) -> dict[str, Any]:
        """
        Check certificate status via OCSP.

        Args:
            certificate_der: DER-encoded certificate to check
            issuer_certificate_der: DER-encoded issuer certificate
            ocsp_url: OCSP responder URL

        Returns:
            Dictionary with OCSP response data
        """
        if not self.session:
            await self.initialize()

        try:
            # Build OCSP request using Rust
            request_der = self.native.build_ocsp_request(
                certificate_der, issuer_certificate_der
            )

            # Send OCSP request
            async with self.session.post(
                ocsp_url,
                data=request_der,
                headers={"Content-Type": "application/ocsp-request"},
            ) as response:
                if response.status != 200:
                    raise ValueError(
                        f"OCSP request failed with status {response.status}"
                    )

                response_data = await response.read()

            # Parse OCSP response using Rust
            parsed = self.native.parse_ocsp_response(response_data)
            status_str = parsed.get("cert_status", "unknown")
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

            # Update DSC status using Rust sha256
            cert_hash = bytes(self.native.hash_data("sha256", certificate_der)).hex()
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
        self, certificate_der: bytes, issuer_dn: str, crl_der: bytes
    ) -> tuple[bool, str | None]:
        """
        Check if a certificate is revoked according to a CRL using Rust.

        This is a synchronous method that uses Rust for fast revocation checking
        without parsing the entire CRL in Python.

        Args:
            certificate_der: DER-encoded certificate to check
            issuer_dn: Issuer distinguished name
            crl_der: DER-encoded CRL data

        Returns:
            Tuple of (is_revoked: bool, reason: Optional[str])
        """

        certificate_info = self.native.get_certificate_info(certificate_der)
        return self.native.check_certificate_revocation(
            certificate_info["serial_number"], issuer_dn, crl_der
        )

    def get_ocsp_url_from_certificate(self, certificate_der: bytes) -> str | None:
        """
        Extract OCSP responder URL from certificate's AIA extension.

        Uses Rust for fast extraction.

        Args:
            certificate_der: DER-encoded certificate to extract URL from

        Returns:
            OCSP responder URL or None if not present
        """
        return self.native.get_ocsp_responder_url(certificate_der)

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
                        issuer_certificate_der = await self._find_issuer_certificate(
                            crl_data["issuer_dn"]
                        )
                        if issuer_certificate_der is None:
                            results["crls_failed"] += 1
                            results["errors"].append(
                                f"Issuer certificate not found for {crl_data['issuer_dn']}"
                            )
                            continue
                        process_result = await self.process_crl(
                            crl_result["data"],
                            crl_data["issuer_dn"],
                            issuer_certificate_der,
                        )

                        if process_result["success"]:
                            results["crls_processed"] += 1
                            results["total_revoked"] += process_result["revoked_count"]
                            results["updated_dscs"] += process_result["updated_dscs"]
                        else:
                            results["crls_failed"] += 1
                            results["errors"].append(
                                process_result.get("error", "Unknown error")
                            )
                    else:
                        results["crls_failed"] += 1
                        results["errors"].append(
                            crl_result.get("error", "Failed to fetch CRL")
                        )

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
        self,
        serial_number: str,
        revocation_date: datetime,
        reason_code: int | None,
        source: str,
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
        dscs = await self.db_manager.get_dsc_certificates(
            certificate_hash=certificate_hash
        )

        if not dscs:
            return {
                "found": False,
                "certificate_hash": certificate_hash,
                "error": "Certificate not found",
            }

        dsc = dscs[0]

        # Check CRL status
        crl_status = await self._check_crl_status(
            dsc["serial_number"], dsc["issuer_dn"]
        )

        # Check OCSP if requested and URL available
        ocsp_status = None
        if check_ocsp:
            ocsp_url = self._extract_ocsp_url(dsc["certificate_data"])
            if ocsp_url:
                issuer_certificate_der = await self._find_issuer_certificate(
                    dsc["issuer_dn"], dsc.get("country_code")
                )
                if issuer_certificate_der is None:
                    ocsp_status = {
                        "success": False,
                        "error": "Issuer certificate required for OCSP was not found",
                        "ocsp_url": ocsp_url,
                    }
                else:
                    ocsp_status = await self.check_ocsp_status(
                        dsc["certificate_data"], issuer_certificate_der, ocsp_url
                    )

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

    async def _check_crl_status(
        self, serial_number: str, issuer_dn: str
    ) -> dict[str, Any]:
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
            return self.native.get_ocsp_responder_url(certificate_data)
        except Exception as e:
            logger.warning(f"Failed to extract OCSP URL: {e}")

        return None

    async def _find_issuer_certificate(
        self, issuer_dn: str, country_code: str | None = None
    ) -> bytes | None:
        """Resolve one active trust anchor by normalized subject DN."""
        anchors = await self.db_manager.get_trust_anchors(
            country_code=country_code, active_only=True
        )
        matches = [
            anchor
            for anchor in anchors
            if self._normalize_dn(anchor["subject_dn"]) == self._normalize_dn(issuer_dn)
        ]
        if len(matches) != 1:
            logger.error(
                "Expected exactly one issuer certificate for %s, found %d",
                issuer_dn,
                len(matches),
            )
            return None
        return bytes(matches[0]["certificate_data"])

    def get_crl_urls_from_certificate(self, certificate_der: bytes) -> list[str]:
        """Extract CRL distribution points using native X.509 parsing."""
        return list(self.native.get_crl_distribution_points(certificate_der))

    def _crl_der(self, crl_data: bytes) -> bytes:
        if crl_data.lstrip().startswith(b"-----BEGIN"):
            return bytes(self.native.crl_pem_to_der(crl_data.decode("ascii")))
        return crl_data

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime:
        if not value:
            raise ValueError("Native revocation result omitted a required timestamp")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _normalize_dn(value: str) -> str:
        return value.upper().replace(" ", "").replace(",", "")

    @staticmethod
    def _reason_code(reason: str | None) -> int | None:
        return {
            "KeyCompromise": 1,
            "CaCompromise": 2,
            "AffiliationChanged": 3,
            "Superseded": 4,
            "CessationOfOperation": 5,
            "CertificateHold": 6,
            "RemoveFromCrl": 8,
            "PrivilegeWithdrawn": 9,
            "AaCompromise": 10,
        }.get(reason or "")
