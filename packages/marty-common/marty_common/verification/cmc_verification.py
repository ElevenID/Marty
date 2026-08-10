"""CMC Verification Protocol Implementation

This module implements comprehensive verification for Crew Member Certificates
supporting multiple verification methods:
- TD-1 MRZ validation
- VDS-NC signature verification
- Chip authentication (LDS/SOD)
- Revocation checking
- Background verification (Annex 9)
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from shared.logging_config import get_logger

from marty_common.crypto.data_group_hasher import verify_passport_data_groups
from marty_common.crypto.sod_parser import parse_sod
from marty_common.crypto.sod_signer import verify_sod_signature
from marty_common.models.passport import CMCCertificate, CMCSecurityModel
from marty_common.native_backends import load_native_backend
from marty_common.vds_nc.cmc_vds_nc_service import get_vds_nc_service

logger = get_logger(__name__)


class VerificationResult:
    """Result of a verification check."""

    def __init__(self, check_name: str, passed: bool, details: str = "", error_code: str | None = None) -> None:
        """Initialize verification result.

        Args:
            check_name: Name of the verification check
            passed: Whether the check passed
            details: Additional details about the result
            error_code: Error code if check failed
        """
        self.check_name = check_name
        self.passed = passed
        self.details = details
        self.error_code = error_code

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "details": self.details,
            "error_code": self.error_code,
        }


class CMCVerificationProtocol:
    """Comprehensive verification protocol for CMC certificates."""

    def __init__(
        self,
        trust_anchors: Sequence[Any] | None = None,
        revocation_checker: Callable[[CMCCertificate], bool] | None = None,
    ) -> None:
        """Initialize verification protocol."""
        self.vds_nc_service = get_vds_nc_service()
        self.trust_anchors = tuple(trust_anchors or ())
        self.revocation_checker = revocation_checker
        logger.info("CMC verification protocol initialized")

    def verify_cmc_from_td1_mrz(
        self, td1_mrz: str, stored_cmc: CMCCertificate | None = None
    ) -> tuple[bool, CMCCertificate | None, list[VerificationResult]]:
        """Verify CMC from TD-1 MRZ string.

        Args:
            td1_mrz: TD-1 format MRZ string (3 lines)
            stored_cmc: Optional stored CMC for comparison

        Returns:
            Tuple of (is_valid, cmc_certificate, verification_results)
        """
        try:
            logger.info("Verifying CMC from TD-1 MRZ")
            results = []

            # Parse TD-1 MRZ
            try:
                native = load_native_backend("marty_verification", ("parse_mrz",))
                parsed = native.parse_mrz(td1_mrz.strip().splitlines())
                mrz_data = parsed.to_dict()
                if mrz_data.get("format") != "TD1":
                    raise ValueError("MRZ is not TD1")
                results.append(VerificationResult("MRZ Format", True, "TD-1 MRZ parsed successfully"))
            except Exception as e:
                results.append(
                    VerificationResult("MRZ Format", False, f"Failed to parse TD-1 MRZ: {e!s}", "MRZ_PARSE_ERROR")
                )
                return False, None, results

            # Validate check digits
            check_digit_result = self._verify_td1_check_digits(td1_mrz)
            results.append(check_digit_result)

            # If stored CMC provided, compare MRZ data
            if stored_cmc:
                mrz_comparison = self._compare_mrz_data(mrz_data, stored_cmc)
                results.append(mrz_comparison)

                if mrz_comparison.passed:
                    # Verify stored CMC security
                    security_results = self._verify_cmc_security(stored_cmc)
                    results.extend(security_results)

                    overall_valid = all(r.passed for r in results)
                    return overall_valid, stored_cmc, results

            # Create CMC from MRZ for basic verification
            basic_cmc = self._create_basic_cmc_from_mrz(mrz_data)
            overall_valid = all(r.passed for r in results)

            logger.info(f"TD-1 MRZ verification completed: {overall_valid}")

        except Exception as e:
            logger.exception("TD-1 MRZ verification failed")
            error_result = VerificationResult(
                "MRZ Verification", False, f"Verification error: {e!s}", "VERIFICATION_ERROR"
            )
            return False, None, [error_result]
        else:
            return overall_valid, basic_cmc, results

    def verify_cmc_from_vds_nc_barcode(
        self, barcode_data: str
    ) -> tuple[bool, CMCCertificate | None, list[VerificationResult]]:
        """Verify CMC from VDS-NC barcode.

        Args:
            barcode_data: VDS-NC barcode data string

        Returns:
            Tuple of (is_valid, cmc_certificate, verification_results)
        """
        try:
            logger.info("Verifying CMC from VDS-NC barcode")
            results = []

            # Verify VDS-NC barcode
            is_valid, cmc_certificate, error_messages = self.vds_nc_service.verify_barcode(barcode_data)

            if is_valid and cmc_certificate:
                results.append(VerificationResult("VDS-NC Barcode", True, "VDS-NC barcode verified successfully"))

                # Additional VDS-NC specific checks
                vds_nc_results = self._verify_vds_nc_specific(barcode_data, cmc_certificate)
                results.extend(vds_nc_results)

            else:
                for error in error_messages:
                    results.append(VerificationResult("VDS-NC Barcode", False, error, "VDS_NC_ERROR"))

            overall_valid = all(r.passed for r in results)
            logger.info(f"VDS-NC barcode verification completed: {overall_valid}")

        except Exception as e:
            logger.exception("VDS-NC barcode verification failed")
            error_result = VerificationResult(
                "VDS-NC Verification", False, f"Verification error: {e!s}", "VERIFICATION_ERROR"
            )
            return False, None, [error_result]
        else:
            return overall_valid, cmc_certificate, results

    def verify_cmc_chip_authentication(self, cmc_certificate: CMCCertificate) -> list[VerificationResult]:
        """Verify chip authentication for chip-based CMC.

        Args:
            cmc_certificate: CMC certificate with chip data

        Returns:
            List of verification results
        """
        results = []

        if not cmc_certificate.uses_chip_security:
            results.append(
                VerificationResult(
                    "Chip Authentication",
                    False,
                    "CMC does not use chip security model",
                    "NOT_CHIP_BASED",
                )
            )
            return results

        try:
            logger.info(f"Verifying chip authentication for CMC: {cmc_certificate.cmc_id}")

            # Verify SOD presence
            if not cmc_certificate.security_object:
                results.append(
                    VerificationResult("SOD Presence", False, "No Security Object Document found", "SOD_MISSING")
                )
                return results

            results.append(VerificationResult("SOD Presence", True, "Security Object Document found"))

            # Verify data group integrity
            dg_integrity_result = self._verify_data_group_integrity(cmc_certificate)
            results.append(dg_integrity_result)

            # Verify DG1 (MRZ) matches visual MRZ
            dg1_result = self._verify_dg1_consistency(cmc_certificate)
            results.append(dg1_result)

            # Verify DG2 (face image) if present
            if "DG2" in cmc_certificate.data_groups:
                dg2_result = self._verify_dg2_integrity(cmc_certificate)
                results.append(dg2_result)

            # Verify SOD signature (simplified)
            sod_signature_result = self._verify_sod_signature(cmc_certificate)
            results.append(sod_signature_result)

            logger.info("Chip authentication verification completed")

        except Exception as e:
            logger.exception("Chip authentication verification failed")
            results.append(
                VerificationResult("Chip Authentication", False, f"Verification error: {e!s}", "VERIFICATION_ERROR")
            )
            return results
        else:
            return results

    def verify_cmc_revocation_status(self, cmc_certificate: CMCCertificate) -> VerificationResult:
        """Verify CMC revocation status.

        Args:
            cmc_certificate: CMC certificate to check

        Returns:
            Verification result for revocation status
        """
        try:
            logger.info(f"Checking revocation status for CMC: {cmc_certificate.cmc_id}")

            # Check certificate status
            if cmc_certificate.status == "REVOKED":
                return VerificationResult(
                    "Revocation Status",
                    False,
                    "Certificate has been revoked",
                    "CERTIFICATE_REVOKED",
                )

            if cmc_certificate.status == "SUSPENDED":
                return VerificationResult(
                    "Revocation Status", False, "Certificate is suspended", "CERTIFICATE_SUSPENDED"
                )

            if cmc_certificate.status == "EXPIRED":
                return VerificationResult("Revocation Status", False, "Certificate has expired", "CERTIFICATE_EXPIRED")

            # Check expiry date
            if cmc_certificate.cmc_data.date_of_expiry:
                try:
                    expiry_date = datetime.strptime(cmc_certificate.cmc_data.date_of_expiry, "%Y-%m-%d").replace(
                        tzinfo=UTC
                    )

                    if expiry_date < datetime.now(tz=UTC):
                        return VerificationResult(
                            "Revocation Status",
                            False,
                            "Certificate has expired based on expiry date",
                            "CERTIFICATE_EXPIRED",
                        )
                except ValueError:
                    logger.warning(f"Invalid expiry date format: {cmc_certificate.cmc_data.date_of_expiry}")

            if self.revocation_checker is None:
                return VerificationResult(
                    "Revocation Status",
                    False,
                    "Native CRL/OCSP evidence is required",
                    "REVOCATION_EVIDENCE_MISSING",
                )
            if not self.revocation_checker(cmc_certificate):
                return VerificationResult(
                    "Revocation Status",
                    False,
                    "Native revocation validation did not establish good status",
                    "REVOCATION_CHECK_FAILED",
                )
            return VerificationResult(
                "Revocation Status",
                True,
                "Native revocation evidence established good status",
            )

        except Exception as e:
            logger.exception("Revocation status check failed")
            return VerificationResult(
                "Revocation Status",
                False,
                f"Revocation check error: {e!s}",
                "REVOCATION_CHECK_ERROR",
            )

    def verify_cmc_background_check(self, cmc_certificate: CMCCertificate) -> VerificationResult:
        """Verify background check status (Annex 9 compliance).

        Args:
            cmc_certificate: CMC certificate to check

        Returns:
            Verification result for background check
        """
        try:
            logger.info(f"Verifying background check for CMC: {cmc_certificate.cmc_id}")

            if not cmc_certificate.cmc_data.background_check_verified:
                return VerificationResult(
                    "Background Check",
                    False,
                    "Background verification not completed",
                    "BACKGROUND_CHECK_FAILED",
                )

            # Check electronic record ID presence (Annex 9 requirement)
            if not cmc_certificate.cmc_data.electronic_record_id:
                return VerificationResult(
                    "Background Check",
                    False,
                    "Electronic record ID missing (Annex 9 requirement)",
                    "ELECTRONIC_RECORD_MISSING",
                )

            # Check issuer record keeping flag
            if not cmc_certificate.cmc_data.issuer_record_keeping:
                return VerificationResult(
                    "Background Check",
                    False,
                    "Issuer record keeping not enabled",
                    "RECORD_KEEPING_DISABLED",
                )

            return VerificationResult("Background Check", True, "Background verification completed successfully")

        except Exception as e:
            logger.exception("Background check verification failed")
            return VerificationResult(
                "Background Check",
                False,
                f"Background check error: {e!s}",
                "BACKGROUND_CHECK_ERROR",
            )

    def perform_comprehensive_verification(
        self,
        cmc_certificate: CMCCertificate,
        check_revocation: bool = True,
        check_background: bool = True,
    ) -> tuple[bool, list[VerificationResult]]:
        """Perform comprehensive verification of CMC certificate.

        Args:
            cmc_certificate: CMC certificate to verify
            check_revocation: Whether to check revocation status
            check_background: Whether to check background verification

        Returns:
            Tuple of (is_valid, verification_results)
        """
        try:
            logger.info(f"Performing comprehensive verification for CMC: {cmc_certificate.cmc_id}")
            results = []

            # Verify based on security model
            if cmc_certificate.uses_chip_security:
                chip_results = self.verify_cmc_chip_authentication(cmc_certificate)
                results.extend(chip_results)
            elif cmc_certificate.uses_vds_nc_security:
                # For VDS-NC, we need the original barcode data
                # This is a limitation - ideally we'd store the original barcode
                results.append(
                    VerificationResult(
                        "VDS-NC Security",
                        False,
                        "The signed VDS-NC barcode is required for verification",
                        "VDS_NC_BARCODE_MISSING",
                    )
                )

            # Check revocation status
            if check_revocation:
                revocation_result = self.verify_cmc_revocation_status(cmc_certificate)
                results.append(revocation_result)

            # Check background verification
            if check_background:
                background_result = self.verify_cmc_background_check(cmc_certificate)
                results.append(background_result)

            # Additional consistency checks
            consistency_results = self._verify_cmc_consistency(cmc_certificate)
            results.extend(consistency_results)

            overall_valid = all(r.passed for r in results)
            logger.info(f"Comprehensive verification completed: {overall_valid}")

        except Exception as e:
            logger.exception("Comprehensive verification failed")
            error_result = VerificationResult(
                "Comprehensive Verification",
                False,
                f"Verification error: {e!s}",
                "VERIFICATION_ERROR",
            )
            return False, [error_result]
        else:
            return overall_valid, results

    def _verify_td1_check_digits(self, td1_mrz: str) -> VerificationResult:
        """Verify TD-1 MRZ check digits."""
        try:
            native = load_native_backend("marty_verification", ("parse_mrz",))
            parsed = native.parse_mrz(td1_mrz.strip().splitlines())
            is_valid = parsed.format == "TD1" and bool(parsed.check_digits_valid)
            if is_valid:
                return VerificationResult("MRZ Check Digits", True, "All check digits are valid")
            return VerificationResult("MRZ Check Digits", False, "Invalid check digits detected", "CHECK_DIGIT_ERROR")
        except Exception as e:
            return VerificationResult(
                "MRZ Check Digits",
                False,
                f"Check digit validation error: {e!s}",
                "CHECK_DIGIT_ERROR",
            )

    def _compare_mrz_data(self, parsed_mrz: dict, stored_cmc: CMCCertificate) -> VerificationResult:
        """Compare parsed MRZ data with stored CMC data."""
        try:
            # Compare key fields
            mismatches = []

            if parsed_mrz.get("document_number") != stored_cmc.cmc_data.document_number:
                mismatches.append("document_number")

            if parsed_mrz.get("issuing_country") != stored_cmc.cmc_data.issuing_country:
                mismatches.append("issuing_country")

            if parsed_mrz.get("surname") != stored_cmc.cmc_data.surname:
                mismatches.append("surname")

            if parsed_mrz.get("given_names") != stored_cmc.cmc_data.given_names:
                mismatches.append("given_names")

            if mismatches:
                return VerificationResult(
                    "MRZ Data Consistency",
                    False,
                    f"MRZ data mismatches in fields: {', '.join(mismatches)}",
                    "MRZ_MISMATCH",
                )
            return VerificationResult("MRZ Data Consistency", True, "MRZ data matches stored certificate")

        except Exception as e:
            return VerificationResult(
                "MRZ Data Consistency",
                False,
                f"MRZ comparison error: {e!s}",
                "MRZ_COMPARISON_ERROR",
            )

    def _verify_vds_nc_specific(self, barcode_data: str, cmc_certificate: CMCCertificate) -> list[VerificationResult]:
        """Perform VDS-NC specific verification checks."""
        results = []

        try:
            # Parse VDS-NC structure
            parts = barcode_data.split("~")
            if len(parts) >= 2:
                header, payload = parts[0], parts[1]

                # Verify header format
                if len(header) == 7 and header.startswith("DC"):
                    results.append(VerificationResult("VDS-NC Header", True, f"Valid VDS-NC header: {header}"))
                else:
                    results.append(
                        VerificationResult(
                            "VDS-NC Header",
                            False,
                            f"Invalid VDS-NC header: {header}",
                            "VDS_NC_HEADER_ERROR",
                        )
                    )

                # Verify payload integrity
                try:
                    import json

                    payload_data = json.loads(payload)

                    if payload_data.get("typ") == "CMC":
                        results.append(VerificationResult("VDS-NC Payload", True, "Valid CMC payload in VDS-NC"))
                    else:
                        results.append(
                            VerificationResult(
                                "VDS-NC Payload",
                                False,
                                f"Invalid message type: {payload_data.get('typ')}",
                                "VDS_NC_TYPE_ERROR",
                            )
                        )

                except json.JSONDecodeError:
                    results.append(
                        VerificationResult("VDS-NC Payload", False, "Invalid JSON payload", "VDS_NC_JSON_ERROR")
                    )

        except Exception as e:
            results.append(
                VerificationResult(
                    "VDS-NC Structure",
                    False,
                    f"VDS-NC structure error: {e!s}",
                    "VDS_NC_STRUCTURE_ERROR",
                )
            )

        return results

    def _verify_data_group_integrity(self, cmc_certificate: CMCCertificate) -> VerificationResult:
        """Verify data group hash integrity against SOD."""
        try:
            if not cmc_certificate.data_groups:
                return VerificationResult("Data Group Integrity", False, "No data groups found", "NO_DATA_GROUPS")

            if not cmc_certificate.security_object:
                return VerificationResult("Data Group Integrity", False, "SOD not present", "SOD_MISSING")
            data_groups = {str(dg_type): dg.data for dg_type, dg in cmc_certificate.data_groups.items()}
            valid, errors, details = verify_passport_data_groups(
                cmc_certificate.security_object,
                data_groups,
            )
            if not valid:
                return VerificationResult(
                    "Data Group Integrity",
                    False,
                    "; ".join(errors) or "Native data-group verification failed",
                    "DATA_GROUP_HASH_MISMATCH",
                )
            return VerificationResult(
                "Data Group Integrity",
                True,
                f"Native SOD hashes verified for {details.get('data_groups_verified', 0)} groups",
            )

        except Exception as e:
            return VerificationResult("Data Group Integrity", False, f"Integrity check error: {e!s}", "INTEGRITY_ERROR")

    def _verify_dg1_consistency(self, cmc_certificate: CMCCertificate) -> VerificationResult:
        """Verify DG1 MRZ data matches visual MRZ."""
        try:
            dg1 = cmc_certificate.data_groups.get("DG1")
            if not dg1:
                return VerificationResult("DG1 Consistency", False, "DG1 data group missing", "DG1_MISSING")

            if not dg1.data:
                return VerificationResult("DG1 Consistency", False, "DG1 data is empty", "DG1_EMPTY")

            native = load_native_backend("marty_verification", ("parse_mrz",))
            raw = dg1.data.decode("ascii") if isinstance(dg1.data, bytes) else str(dg1.data)
            parsed = native.parse_mrz(raw.strip().splitlines())
            expected = cmc_certificate.cmc_data
            matches = (
                parsed.format == "TD1"
                and parsed.check_digits_valid
                and parsed.document_number == expected.document_number
                and parsed.issuing_country == expected.issuing_country
                and parsed.surname == expected.surname
                and parsed.given_names == expected.given_names
            )
            if not matches:
                return VerificationResult(
                    "DG1 Consistency",
                    False,
                    "Native DG1 MRZ validation or printed-field comparison failed",
                    "DG1_MISMATCH",
                )
            return VerificationResult("DG1 Consistency", True, "Native DG1 MRZ and printed fields match")

        except Exception as e:
            return VerificationResult("DG1 Consistency", False, f"DG1 check error: {e!s}", "DG1_ERROR")

    def _verify_dg2_integrity(self, cmc_certificate: CMCCertificate) -> VerificationResult:
        """Verify DG2 face image integrity."""
        try:
            dg2 = cmc_certificate.data_groups.get("DG2")
            if not dg2:
                return VerificationResult("DG2 Integrity", False, "DG2 data group missing", "DG2_MISSING")

            if not dg2.data:
                return VerificationResult("DG2 Integrity", False, "DG2 data is empty", "DG2_EMPTY")

            integrity = self._verify_data_group_integrity(cmc_certificate)
            if not integrity.passed:
                return VerificationResult(
                    "DG2 Integrity",
                    False,
                    "DG2 was not authenticated by the native SOD hash check",
                    "DG2_HASH_INVALID",
                )
            return VerificationResult("DG2 Integrity", True, "DG2 was authenticated by its native SOD hash check")

        except Exception as e:
            return VerificationResult("DG2 Integrity", False, f"DG2 check error: {e!s}", "DG2_ERROR")

    def _verify_sod_signature(self, cmc_certificate: CMCCertificate) -> VerificationResult:
        """Verify SOD digital signature."""
        try:
            if not cmc_certificate.security_object:
                return VerificationResult("SOD Signature", False, "SOD not present", "SOD_MISSING")

            if not self.trust_anchors:
                return VerificationResult(
                    "SOD Signature",
                    False,
                    "CSCA trust anchors are required",
                    "SOD_TRUST_ANCHOR_MISSING",
                )
            sod = parse_sod(cmc_certificate.security_object)
            if not verify_sod_signature(sod.der, self.trust_anchors):
                return VerificationResult(
                    "SOD Signature",
                    False,
                    "Native SOD signature or DSC chain validation failed",
                    "SOD_SIGNATURE_INVALID",
                )
            return VerificationResult("SOD Signature", True, "Native SOD signature and DSC chain are valid")

        except Exception as e:
            return VerificationResult("SOD Signature", False, f"SOD signature error: {e!s}", "SOD_SIGNATURE_ERROR")

    def _verify_cmc_consistency(self, cmc_certificate: CMCCertificate) -> list[VerificationResult]:
        """Verify overall CMC consistency."""
        results = []

        try:
            # Check required fields
            if not cmc_certificate.cmc_data.document_number:
                results.append(
                    VerificationResult(
                        "Document Number",
                        False,
                        "Document number is missing",
                        "MISSING_DOCUMENT_NUMBER",
                    )
                )
            else:
                results.append(VerificationResult("Document Number", True, "Document number is present"))

            # Check issuing country
            if not cmc_certificate.cmc_data.issuing_country or len(cmc_certificate.cmc_data.issuing_country) != 3:
                results.append(
                    VerificationResult(
                        "Issuing Country",
                        False,
                        "Invalid issuing country code",
                        "INVALID_COUNTRY_CODE",
                    )
                )
            else:
                results.append(VerificationResult("Issuing Country", True, "Valid issuing country code"))

            # Check security model consistency
            if cmc_certificate.uses_chip_security:
                if not cmc_certificate.data_groups:
                    results.append(
                        VerificationResult(
                            "Security Model",
                            False,
                            "Chip security model but no data groups",
                            "SECURITY_MODEL_INCONSISTENT",
                        )
                    )
                else:
                    results.append(VerificationResult("Security Model", True, "Chip security model is consistent"))

        except Exception as e:
            results.append(
                VerificationResult("CMC Consistency", False, f"Consistency check error: {e!s}", "CONSISTENCY_ERROR")
            )

        return results

    def _create_basic_cmc_from_mrz(self, mrz_data: dict) -> CMCCertificate:
        """Create basic CMC certificate from MRZ data for verification."""
        from marty_common.models.passport import CMCData, CMCTD1MRZData

        # This would be used for basic verification when no stored CMC is available
        # Implementation details would depend on specific requirements
        cmc_data = CMCData(
            document_number=mrz_data.get("document_number", ""),
            issuing_country=mrz_data.get("issuing_country", ""),
            surname=mrz_data.get("surname", ""),
            given_names=mrz_data.get("given_names", ""),
            nationality=mrz_data.get("nationality", ""),
            date_of_birth=mrz_data.get("date_of_birth", ""),
            gender=mrz_data.get("gender", ""),
            date_of_expiry=mrz_data.get("date_of_expiry", ""),
            employer="",
            crew_id="",
            background_check_verified=False,
            electronic_record_id="",
            issuer_record_keeping=False,
        )

        td1_mrz_data = CMCTD1MRZData(
            document_type=mrz_data.get("document_type", "I"),
            issuing_country=mrz_data.get("issuing_country", ""),
            document_number=mrz_data.get("document_number", ""),
            surname=mrz_data.get("surname", ""),
            given_names=mrz_data.get("given_names", ""),
            nationality=mrz_data.get("nationality", ""),
            date_of_birth=mrz_data.get("date_of_birth", ""),
            gender=mrz_data.get("gender", ""),
            date_of_expiry=mrz_data.get("date_of_expiry", ""),
        )

        return CMCCertificate(
            cmc_id=f"mrz-{mrz_data.get('document_number', 'unknown')}",
            cmc_data=cmc_data,
            td1_mrz_data=td1_mrz_data,
            security_model=CMCSecurityModel.VDS_NC,  # Default for MRZ-only verification
            status="ACTIVE",
            created_at=datetime.now(tz=UTC),
        )


# Global verification protocol instance
_verification_protocol: CMCVerificationProtocol | None = None


def get_verification_protocol() -> CMCVerificationProtocol:
    """Get or create global verification protocol instance.

    Returns:
        CMC verification protocol instance
    """
    global _verification_protocol
    if _verification_protocol is None:
        _verification_protocol = CMCVerificationProtocol()
    return _verification_protocol
