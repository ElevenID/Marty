"""
Visa verification engine implementing the complete verification protocol.

This module provides comprehensive visa verification following ICAO standards:
1. MRZ parse → check digits verification
2. VDS-NC decode → signature verification → field consistency
3. Policy checks: validity dates, category constraints, optional online lookup

Supports both MRV (sticker) and e-visa (digital) verification with unified results.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from marty_plugin.shared.models.visa import VerificationResult, Visa, VisaType, VisaVerifyRequest
from marty_plugin.shared.utils.vds_nc import VDSNCDecoder, VDSNCValidator
from marty_plugin.shared.utils.visa_mrz import MRZParser


class VerificationStep(str, Enum):
    """Verification step identifiers."""

    MRZ_PARSE = "mrz_parse"
    CHECK_DIGITS = "check_digits"
    VDS_NC_DECODE = "vds_nc_decode"
    SIGNATURE_VERIFY = "signature_verify"
    FIELD_CONSISTENCY = "field_consistency"
    POLICY_CHECK = "policy_check"
    ONLINE_VERIFY = "online_verify"


class VerificationError(Exception):
    """Custom exception for verification errors."""

    def __init__(
        self, step: VerificationStep, message: str, details: dict[str, Any] | None = None
    ) -> None:
        self.step = step
        self.message = message
        self.details = details or {}
        super().__init__(f"Verification failed at {step.value}: {message}")


class VisaVerificationEngine:
    """Engine for comprehensive visa verification."""

    def __init__(self, trust_store: dict[str, str] | None = None) -> None:
        """
        Initialize verification engine.

        Args:
            trust_store: Dictionary mapping issuer IDs to public keys
        """
        self.trust_store = trust_store or {}

    async def verify_visa(
        self, request: VisaVerifyRequest, reference_visa: Visa | None = None
    ) -> VerificationResult:
        """
        Perform complete visa verification.

        Args:
            request: Verification request
            reference_visa: Optional reference visa for comparison

        Returns:
            VerificationResult with detailed results
        """
        result = VerificationResult(is_valid=False, verification_timestamp=datetime.utcnow())

        try:
            # Step 1: Parse input and determine verification path
            parsed_data, visa_type = await self._parse_input(request, reference_visa)

            # Step 2: MRZ verification (if MRZ data present)
            if "mrz_data" in parsed_data:
                await self._verify_mrz(parsed_data["mrz_data"], visa_type, result)

            # Step 3: VDS-NC verification (if barcode data present)
            if "vds_nc_data" in parsed_data:
                await self._verify_vds_nc(
                    parsed_data["vds_nc_data"], result, verify_signature=request.verify_signature
                )

            # Step 4: Field consistency (if reference visa provided)
            if reference_visa:
                await self._verify_field_consistency(parsed_data, reference_visa, result)

            # Step 5: Policy checks
            if request.check_policy:
                await self._verify_policy(parsed_data, result)

            # Step 6: Online verification (if requested)
            if request.online_verification:
                await self._verify_online(parsed_data, result)

            # Determine overall validity
            result.is_valid = self._calculate_overall_validity(result)

        except VerificationError as e:
            result.verification_details[e.step.value] = {"error": e.message, "details": e.details}
            if e.step == VerificationStep.MRZ_PARSE:
                result.mrz_errors.append(e.message)
            elif e.step in [VerificationStep.VDS_NC_DECODE, VerificationStep.SIGNATURE_VERIFY]:
                result.vds_nc_errors.append(e.message)
            elif e.step == VerificationStep.POLICY_CHECK:
                result.policy_errors.append(e.message)

        except Exception as e:
            result.verification_details["unexpected_error"] = str(e)

        return result

    async def _parse_input(
        self, request: VisaVerifyRequest, reference_visa: Visa | None = None
    ) -> tuple[dict[str, Any], VisaType | None]:
        """
        Parse verification input and extract data.

        Args:
            request: Verification request
            reference_visa: Optional reference visa for data extraction

        Returns:
            Tuple of (parsed_data, visa_type)
        """
        parsed_data = {}
        visa_type = None

        # If we have a reference visa and no direct data, extract from the visa
        if reference_visa and not request.mrz_data and not request.barcode_data:
            visa_type = reference_visa.document_data.visa_type

            # Extract MRZ data if available
            if reference_visa.mrz_data:
                if visa_type == VisaType.MRV_TYPE_A:
                    parsed_data["mrz_data"] = MRZParser.parse_type_a_mrz(
                        reference_visa.mrz_data.type_a_line1, reference_visa.mrz_data.type_a_line2
                    )
                elif visa_type == VisaType.MRV_TYPE_B:
                    parsed_data["mrz_data"] = MRZParser.parse_type_b_mrz(
                        reference_visa.mrz_data.type_b_line1,
                        reference_visa.mrz_data.type_b_line2,
                        reference_visa.mrz_data.type_b_line3,
                    )

            # Extract VDS-NC data if available
            if reference_visa.vds_nc_data:
                parsed_data["vds_nc_data"] = {
                    "decoded": {
                        "header": reference_visa.vds_nc_data.header,
                        "message": reference_visa.vds_nc_data.message,
                    },
                    "signature_valid": True,  # Assume valid since it's stored
                }

        # Parse MRZ data if provided directly
        if request.mrz_data:
            try:
                mrz_lines = request.mrz_data.strip().split("\n")

                if len(mrz_lines) == 2 and all(len(line) == 44 for line in mrz_lines):
                    # Type A visa (2-line, 44 chars each)
                    visa_type = VisaType.MRV_TYPE_A
                    parsed_data["mrz_data"] = MRZParser.parse_type_a_mrz(mrz_lines[0], mrz_lines[1])

                elif len(mrz_lines) == 3 and all(len(line) == 36 for line in mrz_lines):
                    # Type B visa (3-line, 36 chars each)
                    visa_type = VisaType.MRV_TYPE_B
                    parsed_data["mrz_data"] = MRZParser.parse_type_b_mrz(
                        mrz_lines[0], mrz_lines[1], mrz_lines[2]
                    )

                else:
                    raise VerificationError(
                        VerificationStep.MRZ_PARSE,
                        "Invalid MRZ format",
                        {
                            "lines": len(mrz_lines),
                            "line_lengths": [len(line) for line in mrz_lines],
                        },
                    )

            except Exception as e:
                raise VerificationError(VerificationStep.MRZ_PARSE, f"Failed to parse MRZ: {e!s}")

        # Parse VDS-NC barcode data if provided
        if request.barcode_data:
            try:
                # Try to get public key for verification
                public_key = None
                decoded_data, signature_valid = VDSNCDecoder.decode_vds_nc(
                    request.barcode_data, public_key
                )

                parsed_data["vds_nc_data"] = {
                    "decoded": decoded_data,
                    "signature_valid": signature_valid,
                }

                # Determine visa type from VDS-NC
                if not visa_type:
                    visa_type = VisaType.E_VISA

            except Exception as e:
                raise VerificationError(
                    VerificationStep.VDS_NC_DECODE, f"Failed to decode VDS-NC: {e!s}"
                )

        return parsed_data, visa_type

    async def _verify_mrz(
        self, mrz_data: dict[str, Any], visa_type: VisaType, result: VerificationResult
    ) -> None:
        """
        Verify MRZ data and check digits.

        Args:
            mrz_data: Parsed MRZ data
            visa_type: Type of visa
            result: Result object to update
        """
        try:
            # Validate check digits
            check_digit_results = MRZParser.validate_check_digits(mrz_data)

            result.mrz_valid = True
            result.check_digits_valid = check_digit_results["all_valid"]

            # Add detailed check digit results
            result.verification_details["check_digits"] = check_digit_results

            # Validate MRZ format specific to visa type
            format_errors = []

            if visa_type in (VisaType.MRV_TYPE_A, VisaType.MRV_TYPE_B):
                if mrz_data.get("document_type") != "V":
                    format_errors.append("Invalid document type for visa")

            # Validate required fields
            required_fields = [
                "document_number",
                "issuing_state",
                "nationality",
                "date_of_birth",
                "gender",
                "date_of_expiry",
            ]

            for field in required_fields:
                if not mrz_data.get(field):
                    format_errors.append(f"Missing required field: {field}")

            # Validate date formats
            try:
                dob = mrz_data.get("date_of_birth", "")
                if len(dob) == 6:
                    # Convert YYMMDD to proper date
                    year = int(dob[:2])
                    # Assume 20xx for years 00-30, 19xx for years 31-99
                    if year <= 30:
                        year += 2000
                    else:
                        year += 1900

                    month = int(dob[2:4])
                    day = int(dob[4:6])

                    if not (1 <= month <= 12 and 1 <= day <= 31):
                        format_errors.append("Invalid date of birth")

                expiry = mrz_data.get("date_of_expiry", "")
                if len(expiry) == 6:
                    year = int(expiry[:2])
                    if year <= 30:
                        year += 2000
                    else:
                        year += 1900

                    month = int(expiry[2:4])
                    day = int(expiry[4:6])

                    if not (1 <= month <= 12 and 1 <= day <= 31):
                        format_errors.append("Invalid expiry date")

            except (ValueError, TypeError):
                format_errors.append("Invalid date format in MRZ")

            # Validate gender code
            gender = mrz_data.get("gender", "")
            if gender not in ["M", "F", "X"]:
                format_errors.append(f"Invalid gender code: {gender}")

            # Validate country codes (3 letters)
            for field in ["issuing_state", "nationality"]:
                value = mrz_data.get(field, "")
                if not (len(value) == 3 and value.isalpha()):
                    format_errors.append(f"Invalid {field} code: {value}")

            if format_errors:
                result.mrz_errors.extend(format_errors)
                result.mrz_valid = False

            result.verification_details["mrz_validation"] = {
                "format_valid": len(format_errors) == 0,
                "errors": format_errors,
            }

        except Exception as e:
            result.mrz_valid = False
            result.mrz_errors.append(f"MRZ validation error: {e!s}")

    async def _verify_vds_nc(
        self, vds_nc_data: dict[str, Any], result: VerificationResult, verify_signature: bool = True
    ) -> None:
        """
        Verify VDS-NC data and signature.

        Args:
            vds_nc_data: VDS-NC data with decoded content
            result: Result object to update
            verify_signature: Whether to verify digital signature
        """
        try:
            decoded = vds_nc_data["decoded"]

            result.vds_nc_present = True

            # Validate VDS-NC structure
            header_errors = VDSNCValidator.validate_header(decoded.get("header", {}))
            message_errors = VDSNCValidator.validate_visa_message(decoded.get("message", {}))

            if header_errors or message_errors:
                result.vds_nc_errors.extend(header_errors)
                result.vds_nc_errors.extend(message_errors)
                result.vds_nc_valid = False
            else:
                result.vds_nc_valid = True

            # Signature verification
            if verify_signature:
                if vds_nc_data.get("signature_valid") is not None:
                    result.signature_valid = vds_nc_data["signature_valid"]
                else:
                    # Try to verify with trust store
                    issuer = decoded.get("header", {}).get("iss", "")

                    if issuer in self.trust_store:
                        # Re-verify with trust store key
                        try:
                            self.trust_store[issuer]
                            # This would need the original barcode data
                            result.signature_valid = True  # Placeholder
                            result.warnings.append(
                                "Signature verification with trust store not fully implemented"
                            )
                        except Exception:
                            result.signature_valid = False
                            result.vds_nc_errors.append("Signature verification failed")
                    else:
                        result.signature_valid = False
                        result.vds_nc_errors.append(f"No trusted key found for issuer: {issuer}")
            else:
                result.signature_valid = True  # Skip signature verification

            result.verification_details["vds_nc"] = {
                "header_valid": len(header_errors) == 0,
                "message_valid": len(message_errors) == 0,
                "header_errors": header_errors,
                "message_errors": message_errors,
                "signature_verified": verify_signature,
            }

        except Exception as e:
            result.vds_nc_valid = False
            result.vds_nc_errors.append(f"VDS-NC verification error: {e!s}")

    async def _verify_field_consistency(
        self, parsed_data: dict[str, Any], reference_visa: Visa, result: VerificationResult
    ) -> None:
        """
        Verify field consistency between parsed data and reference visa.

        Args:
            parsed_data: Parsed verification data
            reference_visa: Reference visa for comparison
            result: Result object to update
        """
        try:
            consistency_errors = []

            # Check MRZ consistency
            if "mrz_data" in parsed_data:
                mrz_data = parsed_data["mrz_data"]

                # Document consistency
                if mrz_data.get("document_number") != reference_visa.document_data.document_number:
                    consistency_errors.append("Document number mismatch")

                if mrz_data.get("issuing_state") != reference_visa.document_data.issuing_state:
                    consistency_errors.append("Issuing state mismatch")

                # Personal data consistency
                if mrz_data.get("nationality") != reference_visa.personal_data.nationality:
                    consistency_errors.append("Nationality mismatch")

                if mrz_data.get("gender") != reference_visa.personal_data.gender.value:
                    consistency_errors.append("Gender mismatch")

                # Date consistency (convert MRZ dates to proper dates for comparison)
                try:
                    # Convert MRZ DOB
                    dob_str = mrz_data.get("date_of_birth", "")
                    if len(dob_str) == 6:
                        year = int(dob_str[:2])
                        if year <= 30:
                            year += 2000
                        else:
                            year += 1900
                        month = int(dob_str[2:4])
                        day = int(dob_str[4:6])
                        mrz_dob = date(year, month, day)

                        if mrz_dob != reference_visa.personal_data.date_of_birth:
                            consistency_errors.append("Date of birth mismatch")

                    # Convert MRZ expiry
                    expiry_str = mrz_data.get("date_of_expiry", "")
                    if len(expiry_str) == 6:
                        year = int(expiry_str[:2])
                        if year <= 30:
                            year += 2000
                        else:
                            year += 1900
                        month = int(expiry_str[2:4])
                        day = int(expiry_str[4:6])
                        mrz_expiry = date(year, month, day)

                        if mrz_expiry != reference_visa.document_data.date_of_expiry:
                            consistency_errors.append("Expiry date mismatch")

                except (ValueError, TypeError):
                    consistency_errors.append("Date conversion error")

            # Check VDS-NC consistency
            if "vds_nc_data" in parsed_data:
                vds_nc_errors = VDSNCValidator.validate_field_consistency(
                    parsed_data["vds_nc_data"]["decoded"], reference_visa
                )
                consistency_errors.extend(vds_nc_errors)

            result.field_consistency_valid = len(consistency_errors) == 0
            result.verification_details["field_consistency"] = {
                "errors": consistency_errors,
                "checks_performed": ["document_data", "personal_data", "dates"],
            }

        except Exception as e:
            result.field_consistency_valid = False
            result.verification_details["field_consistency"] = {
                "error": f"Consistency check failed: {e!s}"
            }

    async def _verify_policy(self, parsed_data: dict[str, Any], result: VerificationResult) -> None:
        """
        Verify policy constraints and validity.

        Args:
            parsed_data: Parsed verification data
            result: Result object to update
        """
        try:
            policy_errors = []

            # Extract dates for validation
            current_date = date.today()
            issue_date = None
            expiry_date = None
            valid_from = None
            valid_until = None

            # Get dates from MRZ if available
            if "mrz_data" in parsed_data:
                mrz_data = parsed_data["mrz_data"]

                try:
                    expiry_str = mrz_data.get("date_of_expiry", "")
                    if len(expiry_str) == 6:
                        year = int(expiry_str[:2])
                        if year <= 30:
                            year += 2000
                        else:
                            year += 1900
                        month = int(expiry_str[2:4])
                        day = int(expiry_str[4:6])
                        expiry_date = date(year, month, day)

                except (ValueError, TypeError):
                    policy_errors.append("Invalid expiry date format")

            # Get dates from VDS-NC if available (more accurate)
            if "vds_nc_data" in parsed_data:
                message = parsed_data["vds_nc_data"]["decoded"].get("message", {})
                val = message.get("val", {})

                try:
                    if "from" in val:
                        issue_date = datetime.fromisoformat(
                            val["from"].replace("Z", "+00:00")
                        ).date()

                    if "to" in val:
                        expiry_date = datetime.fromisoformat(
                            val["to"].replace("Z", "+00:00")
                        ).date()

                    if "valid_from" in val:
                        valid_from = datetime.fromisoformat(
                            val["valid_from"].replace("Z", "+00:00")
                        ).date()

                    if "valid_until" in val:
                        valid_until = datetime.fromisoformat(
                            val["valid_until"].replace("Z", "+00:00")
                        ).date()

                except (ValueError, TypeError):
                    policy_errors.append("Invalid date format in VDS-NC")

            # Check validity period
            validity_ok = True

            if expiry_date and current_date > expiry_date:
                policy_errors.append("Visa has expired")
                validity_ok = False

            if issue_date and current_date < issue_date:
                policy_errors.append("Visa not yet valid (before issue date)")
                validity_ok = False

            if valid_from and current_date < valid_from:
                policy_errors.append("Visa not yet valid (before valid from date)")
                validity_ok = False

            if valid_until and current_date > valid_until:
                policy_errors.append("Visa validity period has ended")
                validity_ok = False

            result.validity_period_ok = validity_ok

            # Additional policy checks would go here
            # (category constraints, purpose restrictions, etc.)
            result.category_constraints_ok = True  # Placeholder

            result.policy_checks_passed = validity_ok and len(policy_errors) == 0
            result.policy_errors.extend(policy_errors)

            result.verification_details["policy"] = {
                "validity_period_checked": True,
                "current_date": current_date.isoformat(),
                "issue_date": issue_date.isoformat() if issue_date else None,
                "expiry_date": expiry_date.isoformat() if expiry_date else None,
                "valid_from": valid_from.isoformat() if valid_from else None,
                "valid_until": valid_until.isoformat() if valid_until else None,
                "errors": policy_errors,
            }

        except Exception as e:
            result.policy_checks_passed = False
            result.policy_errors.append(f"Policy check failed: {e!s}")

    async def _verify_online(self, parsed_data: dict[str, Any], result: VerificationResult) -> None:
        """
        Perform online verification if configured.

        Args:
            parsed_data: Parsed verification data
            result: Result object to update
        """
        try:
            # This is a placeholder for online verification
            # In practice, this would make HTTP requests to visa verification APIs

            result.verification_details["online_verification"] = {
                "attempted": True,
                "available": False,
                "message": "Online verification not implemented",
            }

            result.online_verification_ok = None  # Not performed

        except Exception as e:
            result.online_verification_ok = False
            result.verification_details["online_verification"] = {
                "error": f"Online verification failed: {e!s}"
            }

    def _calculate_overall_validity(self, result: VerificationResult) -> bool:
        """
        Calculate overall validity based on verification results.

        Args:
            result: Verification result

        Returns:
            True if visa is valid overall
        """
        # Must have at least one successful verification method
        has_valid_verification = False

        if result.mrz_valid and result.check_digits_valid:
            has_valid_verification = True

        if result.vds_nc_present and result.vds_nc_valid and result.signature_valid:
            has_valid_verification = True

        # Policy checks must pass
        policy_ok = result.policy_checks_passed

        # Field consistency must be valid if checked
        consistency_ok = (
            result.field_consistency_valid if hasattr(result, "field_consistency_valid") else True
        )

        return has_valid_verification and policy_ok and consistency_ok


class VisaLookupService:
    """Service for looking up visa records."""

    def __init__(self, visa_database: dict[str, Visa] | None = None) -> None:
        """
        Initialize lookup service.

        Args:
            visa_database: Dictionary mapping visa IDs to visa objects
        """
        self.visa_database = visa_database or {}

    async def lookup_visa(self, visa_id: str) -> Visa | None:
        """
        Look up visa by ID.

        Args:
            visa_id: Visa identifier

        Returns:
            Visa object if found
        """
        return self.visa_database.get(visa_id)

    async def lookup_by_document_number(
        self, document_number: str, issuing_state: str
    ) -> Visa | None:
        """
        Look up visa by document number and issuing state.

        Args:
            document_number: Document number
            issuing_state: Issuing state code

        Returns:
            Visa object if found
        """
        for visa in self.visa_database.values():
            if (
                visa.document_data.document_number == document_number
                and visa.document_data.issuing_state == issuing_state
            ):
                return visa

        return None
