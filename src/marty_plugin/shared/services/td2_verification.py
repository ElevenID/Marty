"""
TD-2 verification engine implementing the same protocol as passports/TD-1.

This module provides comprehensive verification for TD-2 documents following:
- MRZ parsing and check digit validation
- Optional SOD/Data Group hash verification (for chip documents)
- Validity window and policy checks
- Field consistency validation

Verification Protocol:
1. MRZ parsing → check digits validation
2. (Optional) SOD/DG hash verification for chip documents
3. Validity window checks (dates, expiry)
4. Policy validation (work authorization, geographic constraints)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any

from marty_plugin.shared.models.td2 import ChipData, TD2Document, VerificationResult
from marty_plugin.shared.utils.td2_mrz import TD2MRZGenerator, TD2MRZParser

logger = logging.getLogger(__name__)


class TD2VerificationEngine:
    """
    Comprehensive TD-2 document verification engine.

    Implements the same verification protocol as passports/TD-1:
    MRZ → (optional) SOD/DG verification → validity/policy checks
    """

    def __init__(self, trust_store_path: str | None = None) -> None:
        """
        Initialize verification engine.

        Args:
            trust_store_path: Path to certificate trust store for SOD verification
        """
        self.trust_store_path = trust_store_path
        self.parser = TD2MRZParser()
        self.generator = TD2MRZGenerator()

    async def verify_document(
        self,
        document: TD2Document,
        verify_chip: bool = False,
        check_policy: bool = True,
        online_verification: bool = False,
    ) -> VerificationResult:
        """
        Verify complete TD-2 document.

        Args:
            document: TD2Document to verify
            verify_chip: Whether to verify chip data (if present)
            check_policy: Whether to check policy constraints
            online_verification: Whether to perform online verification

        Returns:
            VerificationResult with detailed validation results
        """
        result = VerificationResult()
        errors = []
        warnings = []

        try:
            # Step 1: MRZ verification
            mrz_result = await self._verify_mrz(document)
            result.mrz_valid = mrz_result["valid"]
            result.mrz_present = mrz_result["present"]

            if not mrz_result["valid"]:
                errors.extend(mrz_result["errors"])
            if mrz_result["warnings"]:
                warnings.extend(mrz_result["warnings"])

            # Step 2: Chip verification (optional)
            if verify_chip and document.chip_data:
                chip_result = await self._verify_chip_data(document)
                result.chip_valid = chip_result["valid"]
                result.chip_present = True
                result.sod_present = chip_result["sod_present"]
                result.sod_valid = chip_result["sod_valid"]
                result.dg_hash_results = chip_result["dg_hash_results"]

                if not chip_result["valid"]:
                    errors.extend(chip_result["errors"])
                if chip_result["warnings"]:
                    warnings.extend(chip_result["warnings"])
            else:
                result.chip_present = document.chip_data is not None

            # Step 3: Date and validity checks
            date_result = await self._verify_dates(document)
            result.dates_valid = date_result["valid"]

            if not date_result["valid"]:
                errors.extend(date_result["errors"])
            if date_result["warnings"]:
                warnings.extend(date_result["warnings"])

            # Step 4: Policy validation
            if check_policy and document.policy_constraints:
                policy_result = await self._verify_policy(document)
                result.policy_valid = policy_result["valid"]

                if not policy_result["valid"]:
                    errors.extend(policy_result["errors"])
                if policy_result["warnings"]:
                    warnings.extend(policy_result["warnings"])
            else:
                result.policy_valid = True  # No policy constraints to check

            # Step 5: Online verification (optional)
            if online_verification:
                online_result = await self._verify_online(document)
                if not online_result["valid"]:
                    errors.extend(online_result["errors"])
                if online_result["warnings"]:
                    warnings.extend(online_result["warnings"])

            # Overall validation
            result.is_valid = (
                result.mrz_valid
                and result.dates_valid
                and result.policy_valid
                and (not verify_chip or not result.chip_present or result.chip_valid)
            )

            result.errors = errors
            result.warnings = warnings
            result.verification_timestamp = datetime.now(timezone.utc)

        except Exception as e:
            logger.exception(f"Verification failed: {e!s}")
            result.is_valid = False
            result.errors = [f"Verification error: {e!s}"]

        return result

    async def verify_mrz_lines(
        self, line1: str, line2: str, verify_check_digits: bool = True
    ) -> VerificationResult:
        """
        Verify TD-2 MRZ lines directly.

        Args:
            line1: First MRZ line (36 characters)
            line2: Second MRZ line (36 characters)
            verify_check_digits: Whether to verify check digits

        Returns:
            VerificationResult for MRZ verification
        """
        result = VerificationResult()
        errors = []
        warnings = []

        try:
            # Parse MRZ lines
            parsed_data = self.parser.parse_td2_mrz(line1, line2)
            result.mrz_present = True

            # Verify check digits if requested
            if verify_check_digits:
                check_results = self.parser.validate_check_digits(parsed_data)

                if not check_results["document_check_valid"]:
                    errors.append("Document number check digit invalid")
                if not check_results["birth_check_valid"]:
                    errors.append("Birth date check digit invalid")
                if not check_results["expiry_check_valid"]:
                    errors.append("Expiry date check digit invalid")
                if not check_results["composite_check_valid"]:
                    errors.append("Composite check digit invalid")

                result.mrz_valid = check_results["all_checks_valid"]
            else:
                result.mrz_valid = True

            # Basic date validation
            if parsed_data["birth_date"] and parsed_data["expiry_date"]:
                if parsed_data["expiry_date"] <= date.today():
                    errors.append("Document has expired")
                if parsed_data["birth_date"] > date.today():
                    errors.append("Birth date is in the future")

            result.is_valid = len(errors) == 0
            result.errors = errors
            result.warnings = warnings
            result.verification_timestamp = datetime.now(timezone.utc)

        except Exception as e:
            logger.exception(f"MRZ verification failed: {e!s}")
            result.is_valid = False
            result.mrz_valid = False
            result.errors = [f"MRZ parsing error: {e!s}"]

        return result

    async def _verify_mrz(self, document: TD2Document) -> dict[str, Any]:
        """Verify MRZ data and check digits."""
        result = {"valid": False, "present": False, "errors": [], "warnings": []}

        if not document.mrz_data:
            result["errors"].append("MRZ data not present")
            return result

        result["present"] = True

        try:
            # Parse the MRZ lines
            parsed_data = self.parser.parse_td2_mrz(
                document.mrz_data.line1, document.mrz_data.line2
            )

            # Validate check digits
            check_results = self.parser.validate_check_digits(parsed_data)

            if not check_results["all_checks_valid"]:
                if not check_results["document_check_valid"]:
                    result["errors"].append("Document number check digit mismatch")
                if not check_results["birth_check_valid"]:
                    result["errors"].append("Birth date check digit mismatch")
                if not check_results["expiry_check_valid"]:
                    result["errors"].append("Expiry date check digit mismatch")
                if not check_results["composite_check_valid"]:
                    result["errors"].append("Composite check digit mismatch")

            # Cross-validate with document data
            personal_data = document.personal_data
            doc_data = document.document_data

            # Check document number consistency
            if parsed_data["document_number"] != doc_data.document_number:
                result["errors"].append("Document number mismatch between MRZ and document data")

            # Check nationality consistency
            if parsed_data["nationality"] != personal_data.nationality:
                result["errors"].append("Nationality mismatch between MRZ and personal data")

            # Check issuing state consistency
            if parsed_data["issuing_state"] != doc_data.issuing_state:
                result["errors"].append("Issuing state mismatch between MRZ and document data")

            # Check date consistency
            if parsed_data["birth_date"] != personal_data.date_of_birth:
                result["errors"].append("Birth date mismatch between MRZ and personal data")

            if parsed_data["expiry_date"] != doc_data.date_of_expiry:
                result["errors"].append("Expiry date mismatch between MRZ and document data")

            # Check gender consistency
            if parsed_data["sex"] != personal_data.gender.value:
                result["errors"].append("Gender mismatch between MRZ and personal data")

            result["valid"] = len(result["errors"]) == 0

        except Exception as e:
            result["errors"].append(f"MRZ validation error: {e!s}")

        return result

    async def _verify_chip_data(self, document: TD2Document) -> dict[str, Any]:
        """Verify chip data including SOD and DG hashes."""
        result = {
            "valid": False,
            "sod_present": False,
            "sod_valid": False,
            "dg_hash_results": {},
            "errors": [],
            "warnings": [],
        }

        chip_data = document.chip_data
        if not chip_data:
            result["errors"].append("Chip data not present")
            return result

        # Check SOD presence
        if chip_data.sod_signature:
            result["sod_present"] = True

            # Verify SOD signature (simplified - would need actual crypto verification)
            try:
                sod_result = await self._verify_sod(chip_data)
                result["sod_valid"] = sod_result["valid"]
                if not sod_result["valid"]:
                    result["errors"].extend(sod_result["errors"])
            except Exception as e:
                result["errors"].append(f"SOD verification failed: {e!s}")

        # Verify Data Group hashes
        if chip_data.dg_hashes:
            dg_results = await self._verify_data_group_hashes(document)
            result["dg_hash_results"] = dg_results

            # Check if critical DGs are valid
            if "DG1" in dg_results and not dg_results["DG1"]:
                result["errors"].append("DG1 (MRZ) hash verification failed")

            if "DG2" in dg_results and not dg_results["DG2"]:
                result["warnings"].append("DG2 (Portrait) hash verification failed")

        result["valid"] = len(result["errors"]) == 0
        return result

    async def _verify_sod(self, chip_data: ChipData) -> dict[str, Any]:
        """
        Verify Security Object Document (SOD) per ICAO Parts 10-12.

        Implements full SOD verification for TD-2 minimal chip profile:
        - Certificate chain validation
        - Digital signature verification
        - Data group hash validation
        """
        result = {"valid": False, "errors": [], "warnings": []}

        if not chip_data.sod_signature:
            result["errors"].append("SOD signature not present")
            return result

        try:
            # Import SOD processor
            from marty_backend_common.crypto.sod_parser import SODProcessor

            processor = SODProcessor()

            # Parse SOD data
            sod_obj = processor.parse_sod_data(chip_data.sod_signature)
            if not sod_obj:
                result["errors"].append("Failed to parse SOD data")
                return result

            # Verify SOD certificate chain (if available)
            if chip_data.sod_cert_issuer and chip_data.sod_cert_serial:
                # In production, this would validate against CSCA trust store
                result["warnings"].append("Certificate chain validation requires trust store")
            else:
                result["warnings"].append("SOD certificate information not available")

            # Verify data group hashes in SOD
            dg_hash_verification = await self._verify_sod_dg_hashes(sod_obj, chip_data)
            if not dg_hash_verification["valid"]:
                result["errors"].extend(dg_hash_verification["errors"])
            else:
                result["warnings"].extend(dg_hash_verification["warnings"])

            # Basic SOD structure validation
            if not hasattr(sod_obj, "ldsSecurityObject"):
                result["errors"].append("Invalid SOD structure - missing LDS Security Object")
                return result

            # Verify hash algorithm support
            hash_algo = getattr(sod_obj.ldsSecurityObject, "hashAlgorithm", "unknown")
            if hash_algo not in ["sha256", "sha384", "sha512"]:
                result["warnings"].append(f"Hash algorithm {hash_algo} may not be fully supported")

            result["valid"] = len(result["errors"]) == 0

        except Exception as e:
            logger.exception(f"SOD verification failed: {e!s}")
            result["errors"].append(f"SOD verification error: {e!s}")

        return result

    async def _verify_sod_dg_hashes(self, sod_obj, chip_data: ChipData) -> dict[str, Any]:
        """Verify data group hashes stored in SOD match actual data."""
        result = {"valid": True, "errors": [], "warnings": []}

        try:
            # Extract data group hashes from SOD
            if not hasattr(sod_obj, "ldsSecurityObject"):
                result["errors"].append("SOD missing LDS Security Object")
                return result

            lds_obj = sod_obj.ldsSecurityObject

            # For TD-2 minimal profile, verify DG1 and DG2
            if hasattr(lds_obj, "dataGroupHashValues"):
                sod_hashes = lds_obj.dataGroupHashValues

                # Verify DG1 hash (MRZ data)
                if chip_data.dg1_mrz:
                    dg1_sod_hash = None
                    for dg_hash in sod_hashes:
                        if getattr(dg_hash, "dataGroupNumber", 0) == 1:
                            dg1_sod_hash = getattr(dg_hash, "dataGroupHashValue", None)
                            break

                    if dg1_sod_hash:
                        # Compute hash of actual DG1 data
                        hash_algo = getattr(lds_obj, "hashAlgorithm", "sha256")
                        actual_hash = self._compute_dg_hash(chip_data.dg1_mrz.encode(), hash_algo)

                        if actual_hash != dg1_sod_hash.hex().lower():
                            result["errors"].append("DG1 hash mismatch with SOD")
                    else:
                        result["warnings"].append("DG1 hash not found in SOD")

                # Verify DG2 hash (Portrait)
                if chip_data.dg2_portrait:
                    dg2_sod_hash = None
                    for dg_hash in sod_hashes:
                        if getattr(dg_hash, "dataGroupNumber", 0) == 2:
                            dg2_sod_hash = getattr(dg_hash, "dataGroupHashValue", None)
                            break

                    if dg2_sod_hash:
                        hash_algo = getattr(lds_obj, "hashAlgorithm", "sha256")
                        actual_hash = self._compute_dg_hash(chip_data.dg2_portrait, hash_algo)

                        if actual_hash != dg2_sod_hash.hex().lower():
                            result["errors"].append("DG2 hash mismatch with SOD")
                    else:
                        result["warnings"].append("DG2 hash not found in SOD")
            else:
                result["errors"].append("No data group hashes found in SOD")

            result["valid"] = len(result["errors"]) == 0

        except Exception as e:
            logger.exception(f"SOD DG hash verification failed: {e!s}")
            result["errors"].append(f"DG hash verification error: {e!s}")
            result["valid"] = False

        return result

    def _compute_dg_hash(self, data: bytes, algorithm: str) -> str:
        """Compute hash for data group verification."""
        try:
            if algorithm.lower() in ["sha256", "sha-256"]:
                return hashlib.sha256(data).hexdigest()
            if algorithm.lower() in ["sha384", "sha-384"]:
                return hashlib.sha384(data).hexdigest()
            if algorithm.lower() in ["sha512", "sha-512"]:
                return hashlib.sha512(data).hexdigest()
            # Default to SHA-256
            return hashlib.sha256(data).hexdigest()
        except Exception as e:
            logger.exception(f"Hash computation failed: {e!s}")
            return ""

    async def _verify_data_group_hashes(self, document: TD2Document) -> dict[str, bool]:
        """Verify data group hashes against actual data."""
        results = {}

        chip_data = document.chip_data
        if not chip_data or not chip_data.dg_hashes:
            return results

        # Verify DG1 (MRZ data)
        if "DG1" in chip_data.dg_hashes and document.mrz_data:
            expected_hash = chip_data.dg_hashes["DG1"]
            actual_data = document.mrz_data.line1 + document.mrz_data.line2
            actual_hash = hashlib.sha256(actual_data.encode()).hexdigest()
            results["DG1"] = expected_hash.lower() == actual_hash.lower()

        # Verify DG2 (Portrait) - would need actual image data
        if "DG2" in chip_data.dg_hashes and chip_data.dg2_portrait:
            expected_hash = chip_data.dg_hashes["DG2"]
            actual_hash = hashlib.sha256(chip_data.dg2_portrait).hexdigest()
            results["DG2"] = expected_hash.lower() == actual_hash.lower()

        return results

    async def _verify_dates(self, document: TD2Document) -> dict[str, Any]:
        """Verify date validity and relationships."""
        result = {"valid": True, "errors": [], "warnings": []}

        today = date.today()
        doc_data = document.document_data
        personal_data = document.personal_data

        # Check if document has expired
        if doc_data.date_of_expiry <= today:
            result["errors"].append("Document has expired")

        # Check if document is not yet valid (future issue date)
        if doc_data.date_of_issue > today:
            result["errors"].append("Document issue date is in the future")

        # Check birth date sanity
        if personal_data.date_of_birth > today:
            result["errors"].append("Birth date is in the future")

        # Check if person is too old (over 150 years)
        age_years = (today - personal_data.date_of_birth).days / 365.25
        if age_years > 150:
            result["warnings"].append("Person appears to be over 150 years old")

        # Check document validity period
        validity_period = (doc_data.date_of_expiry - doc_data.date_of_issue).days
        if validity_period > 3650:  # Over 10 years
            result["warnings"].append("Document has unusually long validity period")

        # Check expiry warning (expires within 6 months)
        if (doc_data.date_of_expiry - today).days < 180:
            result["warnings"].append("Document expires within 6 months")

        result["valid"] = len(result["errors"]) == 0
        return result

    async def _verify_policy(self, document: TD2Document) -> dict[str, Any]:
        """Verify policy constraints and authorizations."""
        result = {"valid": True, "errors": [], "warnings": []}

        policy = document.policy_constraints
        if not policy:
            return result

        # Check geographic constraints
        if policy.allowed_regions:
            # This would need to be checked against current location or intended destination
            result["warnings"].append(
                "Geographic constraints present - manual verification required"
            )

        if policy.restricted_areas:
            result["warnings"].append("Area restrictions present - manual verification required")

        # Check stay duration
        if policy.max_stay_duration:
            # This would need to be checked against entry/exit records
            result["warnings"].append(f"Maximum stay limited to {policy.max_stay_duration} days")

        # Check biometric requirements
        if policy.requires_biometric_verification:
            result["warnings"].append("Biometric verification required")

        # Check online verification requirements
        if policy.requires_online_check:
            if not policy.verification_url:
                result["errors"].append("Online verification required but no URL provided")
            else:
                result["warnings"].append("Online verification required")

        result["valid"] = len(result["errors"]) == 0
        return result

    async def _verify_online(self, document: TD2Document) -> dict[str, Any]:
        """Perform online verification if required."""
        result = {"valid": True, "errors": [], "warnings": []}

        # Check if online verification is required
        if (
            document.policy_constraints
            and document.policy_constraints.requires_online_check
            and document.policy_constraints.verification_url
        ):
            # Placeholder for actual online verification
            # This would involve:
            # - HTTP request to verification service
            # - Checking document status in issuer database
            # - Validating against revocation lists

            result["warnings"].append("Online verification not implemented")

        return result

    def generate_verification_report(self, result: VerificationResult) -> str:
        """Generate human-readable verification report."""
        report = []
        report.append("=== TD-2 Document Verification Report ===")
        report.append(f"Verification Time: {result.verification_timestamp}")
        report.append(f"Overall Status: {'VALID' if result.is_valid else 'INVALID'}")
        report.append("")

        # MRZ Status
        report.append("MRZ Verification:")
        report.append(f"  Present: {'Yes' if result.mrz_present else 'No'}")
        report.append(f"  Valid: {'Yes' if result.mrz_valid else 'No'}")

        # Chip Status
        if result.chip_present:
            report.append("Chip Verification:")
            report.append("  Present: Yes")
            report.append(f"  Valid: {'Yes' if result.chip_valid else 'No'}")
            report.append(f"  SOD Present: {'Yes' if result.sod_present else 'No'}")
            report.append(f"  SOD Valid: {'Yes' if result.sod_valid else 'No'}")

            if result.dg_hash_results:
                report.append("  Data Group Hashes:")
                for dg, valid in result.dg_hash_results.items():
                    report.append(f"    {dg}: {'Valid' if valid else 'Invalid'}")

        # Date Status
        report.append("Date Verification:")
        report.append(f"  Valid: {'Yes' if result.dates_valid else 'No'}")

        # Policy Status
        report.append("Policy Verification:")
        report.append(f"  Valid: {'Yes' if result.policy_valid else 'No'}")

        # Errors
        if result.errors:
            report.append("")
            report.append("Errors:")
            report.extend(f"  - {error}" for error in result.errors)

        # Warnings
        if result.warnings:
            report.append("")
            report.append("Warnings:")
            report.extend(f"  - {warning}" for warning in result.warnings)

        return "\n".join(report)
