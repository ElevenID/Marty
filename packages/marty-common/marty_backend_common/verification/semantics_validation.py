"""
Semantics Validation Layer for Unified Verification Protocol

This module implements Layer 4 of the unified verification protocol:
- Validity windows (issue/expiry dates)
- Category constraints (document-specific business rules)
- Issuer policy flags and compliance checks
- Cross-field consistency validation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

# Import from our document detection module
from .document_detection import DocumentClass


class SemanticsValidationLevel(Enum):
    """Semantics validation strictness levels."""

    BASIC = "basic"  # Essential date and format checks
    STANDARD = "standard"  # + policy constraints and category rules
    STRICT = "strict"  # + cross-field validation and issuer compliance


class PolicyViolationLevel(Enum):
    """Severity levels for policy violations."""

    INFO = "info"  # Informational, non-blocking
    WARNING = "warning"  # May cause issues, review recommended
    ERROR = "error"  # Compliance violation, blocking
    CRITICAL = "critical"  # Security or legal violation, immediate block


@dataclass
class SemanticsResult:
    """Result of a semantics validation check."""

    check_name: str
    passed: bool
    details: str
    violation_level: PolicyViolationLevel = PolicyViolationLevel.INFO
    confidence: float = 1.0
    error_code: str | None = None
    policy_reference: str | None = None


class DateValidator:
    """Validates dates and date ranges for travel documents."""

    @staticmethod
    def parse_mrz_date(mrz_date: str) -> date:
        """
        Parse MRZ date format (YYMMDD) to Python date.

        Handles Y2K window:
        - 00-29 → 2000-2029
        - 30-99 → 1930-1999
        """
        if not mrz_date or len(mrz_date) != 6 or not mrz_date.isdigit():
            msg = f"Invalid MRZ date format: {mrz_date}"
            raise ValueError(msg)

        year = int(mrz_date[:2])
        month = int(mrz_date[2:4])
        day = int(mrz_date[4:6])

        # Y2K window logic
        full_year = 2000 + year if year <= 29 else 1900 + year

        try:
            return date(full_year, month, day)
        except ValueError as e:
            msg = f"Invalid date components in {mrz_date}: {e}"
            raise ValueError(msg)

    @staticmethod
    def validate_validity_window(
        issue_date: date | None, expiry_date: date, current_date: date | None = None
    ) -> list[SemanticsResult]:
        """Validate document validity window against current date."""
        results = []

        if current_date is None:
            current_date = date.today()

        # Check if document is expired
        if expiry_date < current_date:
            days_expired = (current_date - expiry_date).days
            results.append(
                SemanticsResult(
                    check_name="document_expiry",
                    passed=False,
                    details=f"Document expired {days_expired} days ago on {expiry_date}",
                    violation_level=PolicyViolationLevel.CRITICAL,
                    confidence=1.0,
                    error_code="DOC_EXPIRED",
                )
            )
        else:
            # Check if document is near expiry (within 6 months)
            days_until_expiry = (expiry_date - current_date).days
            if days_until_expiry <= 180:
                results.append(
                    SemanticsResult(
                        check_name="document_near_expiry",
                        passed=True,
                        details=f"Document expires in {days_until_expiry} days on {expiry_date}",
                        violation_level=PolicyViolationLevel.WARNING,
                        confidence=1.0,
                        error_code="DOC_NEAR_EXPIRY",
                    )
                )
            else:
                results.append(
                    SemanticsResult(
                        check_name="document_validity",
                        passed=True,
                        details=f"Document valid until {expiry_date} ({days_until_expiry} days)",
                        violation_level=PolicyViolationLevel.INFO,
                        confidence=1.0,
                    )
                )

        # Validate issue date if available
        if issue_date:
            if issue_date > current_date:
                results.append(
                    SemanticsResult(
                        check_name="document_issue_date",
                        passed=False,
                        details=f"Document issue date {issue_date} is in the future",
                        violation_level=PolicyViolationLevel.ERROR,
                        confidence=1.0,
                        error_code="FUTURE_ISSUE_DATE",
                    )
                )
            elif issue_date >= expiry_date:
                results.append(
                    SemanticsResult(
                        check_name="issue_expiry_order",
                        passed=False,
                        details=f"Issue date {issue_date} is not before expiry date {expiry_date}",
                        violation_level=PolicyViolationLevel.ERROR,
                        confidence=1.0,
                        error_code="INVALID_DATE_ORDER",
                    )
                )
            else:
                results.append(
                    SemanticsResult(
                        check_name="document_issue_date",
                        passed=True,
                        details=f"Valid issue date: {issue_date}",
                        violation_level=PolicyViolationLevel.INFO,
                        confidence=1.0,
                    )
                )

        return results

    @staticmethod
    def validate_age_consistency(
        birth_date: date, current_date: date | None = None
    ) -> list[SemanticsResult]:
        """Validate birth date and calculate age for consistency checks."""
        results = []

        if current_date is None:
            current_date = date.today()

        # Check if birth date is reasonable
        if birth_date > current_date:
            results.append(
                SemanticsResult(
                    check_name="birth_date_future",
                    passed=False,
                    details=f"Birth date {birth_date} is in the future",
                    violation_level=PolicyViolationLevel.ERROR,
                    confidence=1.0,
                    error_code="FUTURE_BIRTH_DATE",
                )
            )
            return results

        # Calculate age
        age = current_date.year - birth_date.year
        if current_date.month < birth_date.month or (
            current_date.month == birth_date.month and current_date.day < birth_date.day
        ):
            age -= 1

        # Age reasonableness checks
        if age < 0:
            results.append(
                SemanticsResult(
                    check_name="age_calculation",
                    passed=False,
                    details=f"Invalid age calculation: {age} years",
                    violation_level=PolicyViolationLevel.ERROR,
                    confidence=1.0,
                    error_code="INVALID_AGE",
                )
            )
        elif age > 150:
            results.append(
                SemanticsResult(
                    check_name="age_maximum",
                    passed=False,
                    details=f"Age {age} exceeds reasonable maximum (150 years)",
                    violation_level=PolicyViolationLevel.WARNING,
                    confidence=0.8,
                    error_code="EXCESSIVE_AGE",
                )
            )
        elif age < 1:
            results.append(
                SemanticsResult(
                    check_name="age_minimum",
                    passed=True,
                    details=f"Infant age detected: {age} years",
                    violation_level=PolicyViolationLevel.INFO,
                    confidence=1.0,
                )
            )
        else:
            results.append(
                SemanticsResult(
                    check_name="age_validation",
                    passed=True,
                    details=f"Valid age: {age} years (born {birth_date})",
                    violation_level=PolicyViolationLevel.INFO,
                    confidence=1.0,
                )
            )

        return results


class CategoryConstraintValidator:
    """Validates document-specific category constraints and business rules."""

    # Document validity periods (in years)
    VALIDITY_PERIODS = {
        DocumentClass.PASSPORT: {"adult": 10, "minor": 5},
        DocumentClass.CMC: {"standard": 5},
        DocumentClass.VISA: {"tourist": 1, "business": 2, "diplomatic": 5},
        DocumentClass.TD1: {"standard": 10},
        DocumentClass.TD2: {"standard": 10},
        DocumentClass.TRAVEL_DOC: {"refugee": 2, "stateless": 2},
    }

    # Age categories
    MINOR_AGE_THRESHOLD = 18

    def validate_validity_period(
        self,
        doc_class: DocumentClass,
        issue_date: date | None,
        expiry_date: date,
        age: int | None = None,
        visa_category: str | None = None,
    ) -> list[SemanticsResult]:
        """Validate document validity period against expected ranges."""
        results = []

        if not issue_date:
            results.append(
                SemanticsResult(
                    check_name="validity_period_check",
                    passed=False,
                    details="Cannot validate validity period without issue date",
                    violation_level=PolicyViolationLevel.WARNING,
                    confidence=0.5,
                    error_code="MISSING_ISSUE_DATE",
                )
            )
            return results

        # Calculate actual validity period
        validity_period = (expiry_date - issue_date).days / 365.25

        # Get expected validity periods for document type
        expected_periods = self.VALIDITY_PERIODS.get(doc_class, {})

        if doc_class == DocumentClass.PASSPORT and age is not None:
            category = "minor" if age < self.MINOR_AGE_THRESHOLD else "adult"
            expected_years = expected_periods.get(category, 10)
        elif doc_class == DocumentClass.VISA and visa_category:
            expected_years = expected_periods.get(visa_category, 1)
        else:
            expected_years = expected_periods.get("standard", 10)

        # Validate against expected period (allow ±10% tolerance)
        tolerance = expected_years * 0.1
        min_period = expected_years - tolerance
        max_period = expected_years + tolerance

        if min_period <= validity_period <= max_period:
            results.append(
                SemanticsResult(
                    check_name="validity_period",
                    passed=True,
                    details=f"Valid period: {validity_period:.1f} years (expected: {expected_years})",
                    violation_level=PolicyViolationLevel.INFO,
                    confidence=0.9,
                )
            )
        else:
            violation_level = (
                PolicyViolationLevel.WARNING
                if abs(validity_period - expected_years) <= 1
                else PolicyViolationLevel.ERROR
            )
            results.append(
                SemanticsResult(
                    check_name="validity_period",
                    passed=False,
                    details=f"Unexpected validity period: {validity_period:.1f} years (expected: {expected_years})",
                    violation_level=violation_level,
                    confidence=0.8,
                    error_code="INVALID_VALIDITY_PERIOD",
                )
            )

        return results

    def validate_document_category(
        self, doc_class: DocumentClass, document_data: dict[str, Any]
    ) -> list[SemanticsResult]:
        """Validate document-specific category constraints."""
        results = []

        if doc_class == DocumentClass.CMC:
            # CMC-specific validations
            results.extend(self._validate_cmc_constraints(document_data))
        elif doc_class == DocumentClass.VISA:
            # Visa-specific validations
            results.extend(self._validate_visa_constraints(document_data))
        elif doc_class == DocumentClass.PASSPORT:
            # Passport-specific validations
            results.extend(self._validate_passport_constraints(document_data))

        return results

    def _validate_cmc_constraints(self, document_data: dict[str, Any]) -> list[SemanticsResult]:
        """Validate Crew Member Certificate specific constraints."""
        results = []

        # CMC should have employer information
        if not document_data.get("employer_info"):
            results.append(
                SemanticsResult(
                    check_name="cmc_employer_info",
                    passed=False,
                    details="CMC missing employer information",
                    violation_level=PolicyViolationLevel.WARNING,
                    confidence=0.7,
                    error_code="MISSING_EMPLOYER_INFO",
                    policy_reference="ICAO Annex 9",
                )
            )

        # CMC nationality should match issuing authority in most cases
        nationality = document_data.get("nationality", "")
        issuing_authority = document_data.get("issuing_authority", "")
        if nationality and issuing_authority and nationality != issuing_authority[:3]:
            results.append(
                SemanticsResult(
                    check_name="cmc_nationality_issuer",
                    passed=False,
                    details=f"CMC nationality {nationality} differs from issuer {issuing_authority}",
                    violation_level=PolicyViolationLevel.INFO,
                    confidence=0.6,
                    policy_reference="ICAO Annex 9",
                )
            )

        return results

    def _validate_visa_constraints(self, document_data: dict[str, Any]) -> list[SemanticsResult]:
        """Validate visa-specific constraints."""
        results = []

        # Visa should have entry/exit information
        entries_allowed = document_data.get("entries_allowed")
        if entries_allowed is not None and isinstance(entries_allowed, str):
            if entries_allowed.upper() not in ["SINGLE", "MULTIPLE", "M", "S"]:
                results.append(
                    SemanticsResult(
                        check_name="visa_entry_type",
                        passed=False,
                        details=f"Invalid visa entry type: {entries_allowed}",
                        violation_level=PolicyViolationLevel.WARNING,
                        confidence=0.8,
                        error_code="INVALID_ENTRY_TYPE",
                    )
                )

        return results

    def _validate_passport_constraints(
        self, document_data: dict[str, Any]
    ) -> list[SemanticsResult]:
        """Validate passport-specific constraints."""
        # Passport should have complete personal information
        required_fields = ["given_names", "surname", "nationality"]
        return [
            SemanticsResult(
                check_name=f"passport_{field}",
                passed=False,
                details=f"Passport missing required field: {field}",
                violation_level=PolicyViolationLevel.WARNING,
                confidence=0.8,
                error_code="MISSING_REQUIRED_FIELD",
            )
            for field in required_fields
            if not document_data.get(field)
        ]


class IssuerPolicyValidator:
    """Validates issuer-specific policies and compliance flags."""

    # Known issuer policy flags
    POLICY_FLAGS = {
        "biometric_required": "Document requires biometric verification",
        "chip_mandatory": "Document must contain electronic chip",
        "photo_required": "Document must include photograph",
        "signature_required": "Document must include signature",
        "emergency_issuance": "Document issued under emergency procedures",
        "limited_validity": "Document has restricted validity conditions",
        "provisional": "Provisional document pending full issuance",
    }

    def validate_policy_compliance(
        self,
        doc_class: DocumentClass,
        document_data: dict[str, Any],
        policy_flags: dict[str, bool] | None = None,
    ) -> list[SemanticsResult]:
        """Validate compliance with issuer policy flags."""
        results = []

        if not policy_flags:
            policy_flags = {}

        # Check biometric requirements
        if policy_flags.get("biometric_required", False):
            has_biometric = bool(
                document_data.get("biometric_data") or document_data.get("chip_data")
            )
            results.append(
                SemanticsResult(
                    check_name="biometric_compliance",
                    passed=has_biometric,
                    details=(
                        "Biometric data required but not present"
                        if not has_biometric
                        else "Biometric requirement satisfied"
                    ),
                    violation_level=(
                        PolicyViolationLevel.ERROR
                        if not has_biometric
                        else PolicyViolationLevel.INFO
                    ),
                    confidence=0.9,
                    error_code="MISSING_BIOMETRIC" if not has_biometric else None,
                    policy_reference="Issuer Policy: biometric_required",
                )
            )

        # Check chip requirements
        if policy_flags.get("chip_mandatory", False):
            has_chip = bool(document_data.get("chip_data"))
            results.append(
                SemanticsResult(
                    check_name="chip_compliance",
                    passed=has_chip,
                    details=(
                        "Electronic chip required but not present"
                        if not has_chip
                        else "Chip requirement satisfied"
                    ),
                    violation_level=(
                        PolicyViolationLevel.ERROR if not has_chip else PolicyViolationLevel.INFO
                    ),
                    confidence=0.9,
                    error_code="MISSING_CHIP" if not has_chip else None,
                    policy_reference="Issuer Policy: chip_mandatory",
                )
            )

        # Check emergency issuance implications
        if policy_flags.get("emergency_issuance", False):
            results.append(
                SemanticsResult(
                    check_name="emergency_issuance",
                    passed=True,
                    details="Document issued under emergency procedures - additional verification may be required",
                    violation_level=PolicyViolationLevel.WARNING,
                    confidence=0.7,
                    policy_reference="Issuer Policy: emergency_issuance",
                )
            )

        # Check provisional status
        if policy_flags.get("provisional", False):
            results.append(
                SemanticsResult(
                    check_name="provisional_status",
                    passed=True,
                    details="Provisional document - validity may be limited pending full issuance",
                    violation_level=PolicyViolationLevel.INFO,
                    confidence=0.8,
                    policy_reference="Issuer Policy: provisional",
                )
            )

        return results


class SemanticsValidator:
    """
    Main semantics validation orchestrator.

    Implements Layer 4 of the unified verification protocol:
    validates business rules, policies, and semantic consistency.
    """

    def __init__(self) -> None:
        self.date_validator = DateValidator()
        self.category_validator = CategoryConstraintValidator()
        self.policy_validator = IssuerPolicyValidator()

    def validate_semantics(
        self,
        document_data: dict[str, Any],
        doc_class: DocumentClass,
        validation_level: SemanticsValidationLevel = SemanticsValidationLevel.STANDARD,
    ) -> list[SemanticsResult]:
        """
        Execute complete semantics validation.

        Args:
            document_data: Document data including MRZ, dates, and metadata
            doc_class: Detected document class
            validation_level: Strictness level for validation

        Returns:
            List of semantics validation results
        """
        all_results = []

        # Extract dates from MRZ or document data
        try:
            birth_date_str = document_data.get("date_of_birth", "")
            expiry_date_str = document_data.get("date_of_expiry", "")
            issue_date_str = document_data.get("date_of_issue", "")

            # Parse dates
            birth_date = (
                self.date_validator.parse_mrz_date(birth_date_str) if birth_date_str else None
            )
            expiry_date = (
                self.date_validator.parse_mrz_date(expiry_date_str) if expiry_date_str else None
            )
            issue_date = (
                self.date_validator.parse_mrz_date(issue_date_str) if issue_date_str else None
            )

            if not expiry_date:
                all_results.append(
                    SemanticsResult(
                        check_name="required_expiry_date",
                        passed=False,
                        details="Document expiry date is required for semantics validation",
                        violation_level=PolicyViolationLevel.ERROR,
                        confidence=1.0,
                        error_code="MISSING_EXPIRY_DATE",
                    )
                )
                return all_results

        except ValueError as e:
            all_results.append(
                SemanticsResult(
                    check_name="date_parsing",
                    passed=False,
                    details=f"Failed to parse document dates: {e}",
                    violation_level=PolicyViolationLevel.ERROR,
                    confidence=1.0,
                    error_code="INVALID_DATE_FORMAT",
                )
            )
            return all_results

        # 1. Validity window validation
        all_results.extend(self.date_validator.validate_validity_window(issue_date, expiry_date))

        # 2. Age consistency validation
        if birth_date:
            age_results = self.date_validator.validate_age_consistency(birth_date)
            all_results.extend(age_results)

            # Extract age for category validation
            age = None
            for result in age_results:
                if result.check_name == "age_validation" and result.passed:
                    age_str = result.details.split("Valid age: ")[1].split(" years")[0]
                    age = int(age_str)
                    break
        else:
            age = None

        # 3. Category constraints (if STANDARD or STRICT)
        if validation_level in [SemanticsValidationLevel.STANDARD, SemanticsValidationLevel.STRICT]:
            # Validity period validation
            if issue_date and expiry_date:
                visa_category = document_data.get("visa_category")
                all_results.extend(
                    self.category_validator.validate_validity_period(
                        doc_class, issue_date, expiry_date, age, visa_category
                    )
                )

            # Document category validation
            all_results.extend(
                self.category_validator.validate_document_category(doc_class, document_data)
            )

        # 4. Policy compliance (if STANDARD or STRICT)
        if validation_level in [SemanticsValidationLevel.STANDARD, SemanticsValidationLevel.STRICT]:
            policy_flags = document_data.get("policy_flags", {})
            all_results.extend(
                self.policy_validator.validate_policy_compliance(
                    doc_class, document_data, policy_flags
                )
            )

        # 5. Cross-field validation (if STRICT)
        if validation_level == SemanticsValidationLevel.STRICT:
            all_results.extend(self._validate_cross_field_consistency(document_data, doc_class))

        return all_results

    def _validate_cross_field_consistency(
        self, document_data: dict[str, Any], doc_class: DocumentClass
    ) -> list[SemanticsResult]:
        """Validate consistency across multiple document fields."""
        results = []

        # Nationality consistency checks
        nationality = document_data.get("nationality", "")
        issuing_authority = document_data.get("issuing_authority", "")

        if nationality and issuing_authority:
            # For most documents, nationality should match issuing authority
            issuer_code = (
                issuing_authority[:3] if len(issuing_authority) >= 3 else issuing_authority
            )

            if nationality != issuer_code and doc_class != DocumentClass.VISA:
                # Note: Visas are often issued by countries different from holder's nationality
                results.append(
                    SemanticsResult(
                        check_name="nationality_issuer_consistency",
                        passed=False,
                        details=f"Nationality {nationality} differs from issuing authority {issuer_code}",
                        violation_level=PolicyViolationLevel.WARNING,
                        confidence=0.7,
                        error_code="NATIONALITY_ISSUER_MISMATCH",
                    )
                )

        # Gender consistency (if multiple sources available)
        mrz_gender = document_data.get("gender", "")
        biometric_gender = document_data.get("biometric_data", {}).get("gender", "")

        if mrz_gender and biometric_gender and mrz_gender != biometric_gender:
            results.append(
                SemanticsResult(
                    check_name="gender_consistency",
                    passed=False,
                    details=f"Gender mismatch: MRZ={mrz_gender}, Biometric={biometric_gender}",
                    violation_level=PolicyViolationLevel.WARNING,
                    confidence=0.8,
                    error_code="GENDER_MISMATCH",
                )
            )

        return results
