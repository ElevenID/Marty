"""ICAO Doc 9303 Annex 9 Policy Constraints Implementation

This module implements policy constraints and requirements for Crew Member Certificates
as specified in ICAO Doc 9303 Annex 9, including:
- Background verification tracking and record keeping
- Electronic record management for enhanced security
- Visa-free entry eligibility management and validation
- Compliance monitoring and audit trail maintenance
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from shared.logging_config import get_logger

logger = get_logger(__name__)


class BackgroundCheckStatus(str, Enum):
    """Background check verification status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class VisaFreeEntryStatus(str, Enum):
    """Visa-free entry eligibility status."""

    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    SUSPENDED = "suspended"
    UNDER_REVIEW = "under_review"


class BackgroundCheckRecord(BaseModel):
    """Background verification record per Annex 9 requirements."""

    record_id: UUID = Field(default_factory=uuid4)
    cmc_id: str = Field(description="Associated CMC certificate ID")
    check_authority: str = Field(description="Authority performing background check")
    check_reference: str = Field(description="Reference number for the check")
    check_type: str = Field(default="comprehensive", description="Type of background check")
    status: BackgroundCheckStatus = Field(default=BackgroundCheckStatus.PENDING)

    # Timing information
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None

    # Check details
    check_scope: list[str] = Field(default_factory=list, description="Scope of background check")
    findings: dict[str, Any] = Field(default_factory=dict, description="Check findings")
    verification_code: str | None = Field(None, description="Verification code for authenticity")

    # Compliance tracking
    annex9_compliant: bool = Field(False, description="Meets Annex 9 requirements")
    retention_period_years: int = Field(default=10, description="Record retention period")

    model_config = {
        "json_encoders": {
            datetime: lambda dt: dt.isoformat() if dt else None,
            UUID: str,
        }
    }

    def generate_verification_code(self) -> str:
        """Generate verification code for record authenticity."""
        data = f"{self.record_id}{self.cmc_id}{self.check_authority}{self.check_reference}"
        return hashlib.sha256(data.encode()).hexdigest()[:16].upper()

    def is_expired(self) -> bool:
        """Check if background check has expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def update_status(
        self, status: BackgroundCheckStatus, findings: dict[str, Any] | None = None
    ) -> None:
        """Update background check status with timestamp."""
        self.status = status
        now = datetime.now(timezone.utc)

        if status == BackgroundCheckStatus.IN_PROGRESS and not self.started_at:
            self.started_at = now
        elif status == BackgroundCheckStatus.COMPLETED:
            self.completed_at = now
            self.annex9_compliant = self._assess_annex9_compliance(findings or {})
        elif status == BackgroundCheckStatus.FAILED:
            self.completed_at = now
            self.annex9_compliant = False

        if findings:
            self.findings.update(findings)

        # Generate verification code when completed
        if status in [BackgroundCheckStatus.COMPLETED, BackgroundCheckStatus.FAILED]:
            self.verification_code = self.generate_verification_code()

    def _assess_annex9_compliance(self, findings: dict[str, Any]) -> bool:
        """Assess if background check meets Annex 9 compliance requirements."""
        required_checks = [
            "criminal_history",
            "employment_history",
            "identity_verification",
            "security_clearance",
            "aviation_experience",
        ]

        for check in required_checks:
            if check not in findings or not findings[check].get("passed", False):
                logger.warning(f"Annex 9 compliance failed for {check}")
                return False

        return True


class ElectronicRecord(BaseModel):
    """Electronic record for enhanced CMC security per Annex 9."""

    record_id: UUID = Field(default_factory=uuid4)
    cmc_id: str = Field(description="Associated CMC certificate ID")
    issuer_authority: str = Field(description="Issuing authority maintaining record")

    # Record metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = Field(default=1, description="Record version number")

    # Digital signature for integrity
    record_hash: str | None = Field(None, description="SHA-256 hash of record content")
    digital_signature: str | None = Field(None, description="Digital signature for integrity")
    signature_algorithm: str = Field(default="ES256", description="Signature algorithm used")

    # Record content
    holder_data: dict[str, Any] = Field(default_factory=dict, description="Certificate holder data")
    background_checks: list[str] = Field(
        default_factory=list, description="Background check record IDs"
    )
    audit_trail: list[dict[str, Any]] = Field(
        default_factory=list, description="Access and modification log"
    )

    # Retention and compliance
    retention_period_years: int = Field(default=10, description="Record retention period")
    archival_date: datetime | None = Field(None, description="When record will be archived")
    compliance_status: dict[str, bool] = Field(
        default_factory=dict, description="Compliance check results"
    )

    model_config = {
        "json_encoders": {
            datetime: lambda dt: dt.isoformat() if dt else None,
            UUID: str,
        }
    }

    def calculate_record_hash(self) -> str:
        """Calculate SHA-256 hash of record content for integrity."""
        content = {
            "record_id": str(self.record_id),
            "cmc_id": self.cmc_id,
            "issuer_authority": self.issuer_authority,
            "version": self.version,
            "holder_data": self.holder_data,
            "background_checks": sorted(self.background_checks),
        }

        content_str = str(sorted(content.items()))
        return hashlib.sha256(content_str.encode()).hexdigest()

    def add_audit_entry(
        self, action: str, actor: str, details: dict[str, Any] | None = None
    ) -> None:
        """Add entry to audit trail."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            "details": details or {},
        }
        self.audit_trail.append(entry)
        self.last_updated = datetime.now(timezone.utc)
        self.version += 1
        self.record_hash = self.calculate_record_hash()

    def verify_integrity(self) -> bool:
        """Verify record integrity using hash."""
        if not self.record_hash:
            return False
        return self.record_hash == self.calculate_record_hash()


class VisaFreeEntryRecord(BaseModel):
    """Visa-free entry eligibility record per Annex 9."""

    record_id: UUID = Field(default_factory=uuid4)
    cmc_id: str = Field(description="Associated CMC certificate ID")
    status: VisaFreeEntryStatus = Field(default=VisaFreeEntryStatus.NOT_ELIGIBLE)

    # Authority information
    granting_authority: str = Field(description="Authority granting visa-free status")
    authorization_reference: str = Field(description="Authorization reference number")

    # Validity period
    granted_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    # Eligibility criteria
    eligible_countries: list[str] = Field(
        default_factory=list, description="Countries for visa-free entry"
    )
    entry_purposes: list[str] = Field(default_factory=list, description="Permitted entry purposes")
    restrictions: list[str] = Field(default_factory=list, description="Entry restrictions")

    # Status tracking
    status_history: list[dict[str, Any]] = Field(
        default_factory=list, description="Status change history"
    )
    last_verification: datetime | None = None
    next_review_date: datetime | None = None

    model_config = {
        "json_encoders": {
            datetime: lambda dt: dt.isoformat() if dt else None,
            UUID: str,
        }
    }

    def update_status(
        self,
        new_status: VisaFreeEntryStatus,
        authority: str,
        reason: str,
        valid_until: datetime | None = None,
    ) -> None:
        """Update visa-free entry status with audit trail."""
        old_status = self.status

        status_change = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "old_status": old_status.value,
            "new_status": new_status.value,
            "authority": authority,
            "reason": reason,
        }

        self.status = new_status
        self.status_history.append(status_change)

        if new_status == VisaFreeEntryStatus.ELIGIBLE:
            self.granted_at = datetime.now(timezone.utc)
            self.valid_from = datetime.now(timezone.utc)
            self.valid_until = valid_until
        elif new_status in [VisaFreeEntryStatus.SUSPENDED, VisaFreeEntryStatus.NOT_ELIGIBLE]:
            self.valid_until = datetime.now(timezone.utc)

    def is_currently_eligible(self) -> bool:
        """Check if currently eligible for visa-free entry."""
        if self.status != VisaFreeEntryStatus.ELIGIBLE:
            return False

        now = datetime.now(timezone.utc)

        if self.valid_from and now < self.valid_from:
            return False

        return not (self.valid_until and now > self.valid_until)

    def is_eligible_for_country(self, country_code: str) -> bool:
        """Check if eligible for visa-free entry to specific country."""
        if not self.is_currently_eligible():
            return False

        return country_code in self.eligible_countries or not self.eligible_countries


class Annex9PolicyManager:
    """Manager for ICAO Doc 9303 Annex 9 policy constraints and compliance."""

    def __init__(self, storage_service=None, notification_service=None) -> None:
        """Initialize policy manager with dependencies."""
        self.storage = storage_service
        self.notification = notification_service

        # In-memory storage for development (replace with persistent storage)
        self._background_checks: dict[str, BackgroundCheckRecord] = {}
        self._electronic_records: dict[str, ElectronicRecord] = {}
        self._visa_free_records: dict[str, VisaFreeEntryRecord] = {}

    async def initiate_background_check(
        self, cmc_id: str, check_authority: str, check_scope: list[str] | None = None
    ) -> BackgroundCheckRecord:
        """Initiate background verification process."""
        logger.info(f"Initiating background check for CMC: {cmc_id}")

        check_reference = f"BGC-{cmc_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"

        background_check = BackgroundCheckRecord(
            cmc_id=cmc_id,
            check_authority=check_authority,
            check_reference=check_reference,
            check_scope=check_scope
            or [
                "criminal_history",
                "employment_history",
                "identity_verification",
                "security_clearance",
                "aviation_experience",
            ],
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),  # 1 year validity
        )

        self._background_checks[str(background_check.record_id)] = background_check

        if self.storage:
            await self.storage.store_background_check(background_check)

        logger.info(f"Background check initiated: {check_reference}")
        return background_check

    async def update_background_check(
        self, record_id: str, status: BackgroundCheckStatus, findings: dict[str, Any] | None = None
    ) -> BackgroundCheckRecord | None:
        """Update background check status and findings."""
        if record_id not in self._background_checks:
            logger.error(f"Background check record not found: {record_id}")
            return None

        background_check = self._background_checks[record_id]
        background_check.update_status(status, findings)

        if self.storage:
            await self.storage.update_background_check(background_check)

        logger.info(f"Background check updated: {record_id} -> {status.value}")
        return background_check

    async def create_electronic_record(
        self, cmc_id: str, issuer_authority: str, holder_data: dict[str, Any]
    ) -> ElectronicRecord:
        """Create electronic record for enhanced CMC security."""
        logger.info(f"Creating electronic record for CMC: {cmc_id}")

        electronic_record = ElectronicRecord(
            cmc_id=cmc_id,
            issuer_authority=issuer_authority,
            holder_data=holder_data,
            archival_date=datetime.now(timezone.utc)
            + timedelta(days=365 * 10),  # 10 year retention
        )

        electronic_record.record_hash = electronic_record.calculate_record_hash()
        electronic_record.add_audit_entry("created", issuer_authority, {"initial_creation": True})

        self._electronic_records[str(electronic_record.record_id)] = electronic_record

        if self.storage:
            await self.storage.store_electronic_record(electronic_record)

        logger.info(f"Electronic record created: {electronic_record.record_id}")
        return electronic_record

    async def link_background_check(
        self, electronic_record_id: str, background_check_id: str
    ) -> bool:
        """Link background check to electronic record."""
        if electronic_record_id not in self._electronic_records:
            logger.error(f"Electronic record not found: {electronic_record_id}")
            return False

        if background_check_id not in self._background_checks:
            logger.error(f"Background check not found: {background_check_id}")
            return False

        electronic_record = self._electronic_records[electronic_record_id]
        electronic_record.background_checks.append(background_check_id)
        electronic_record.add_audit_entry(
            "background_check_linked", "system", {"background_check_id": background_check_id}
        )

        if self.storage:
            await self.storage.update_electronic_record(electronic_record)

        logger.info(f"Background check linked: {background_check_id} -> {electronic_record_id}")
        return True

    async def manage_visa_free_status(
        self,
        cmc_id: str,
        status: VisaFreeEntryStatus,
        granting_authority: str,
        reason: str,
        eligible_countries: list[str] | None = None,
        valid_until: datetime | None = None,
    ) -> VisaFreeEntryRecord:
        """Manage visa-free entry eligibility status."""
        logger.info(f"Managing visa-free status for CMC: {cmc_id}")

        # Find existing record or create new one
        visa_record = None
        for record in self._visa_free_records.values():
            if record.cmc_id == cmc_id:
                visa_record = record
                break

        if not visa_record:
            visa_record = VisaFreeEntryRecord(
                cmc_id=cmc_id,
                granting_authority=granting_authority,
                authorization_reference=f"VFE-{cmc_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                eligible_countries=eligible_countries or [],
                entry_purposes=["crew_duties", "transit"],
                next_review_date=datetime.now(timezone.utc) + timedelta(days=365),
            )
            self._visa_free_records[str(visa_record.record_id)] = visa_record

        visa_record.update_status(status, granting_authority, reason, valid_until)

        if self.storage:
            await self.storage.store_visa_free_record(visa_record)

        logger.info(f"Visa-free status updated: {cmc_id} -> {status.value}")
        return visa_record

    async def verify_annex9_compliance(self, cmc_id: str) -> dict[str, Any]:
        """Verify full Annex 9 compliance for CMC."""
        logger.info(f"Verifying Annex 9 compliance for CMC: {cmc_id}")

        compliance_result = {
            "cmc_id": cmc_id,
            "compliant": False,
            "checks": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Check background verification
        background_compliant = False
        for bg_check in self._background_checks.values():
            if bg_check.cmc_id == cmc_id and bg_check.status == BackgroundCheckStatus.COMPLETED:
                background_compliant = bg_check.annex9_compliant
                break

        compliance_result["checks"]["background_verification"] = {
            "compliant": background_compliant,
            "details": (
                "Background check completed and verified"
                if background_compliant
                else "Background check not completed or failed"
            ),
        }

        # Check electronic record keeping
        electronic_record_compliant = False
        for record in self._electronic_records.values():
            if record.cmc_id == cmc_id and record.verify_integrity():
                electronic_record_compliant = True
                break

        compliance_result["checks"]["electronic_record_keeping"] = {
            "compliant": electronic_record_compliant,
            "details": (
                "Electronic record maintained with integrity"
                if electronic_record_compliant
                else "Electronic record not found or integrity compromised"
            ),
        }

        # Check visa-free status management
        visa_free_managed = False
        for vf_record in self._visa_free_records.values():
            if vf_record.cmc_id == cmc_id:
                visa_free_managed = True
                break

        compliance_result["checks"]["visa_free_management"] = {
            "compliant": visa_free_managed,
            "details": (
                "Visa-free status actively managed"
                if visa_free_managed
                else "Visa-free status not managed"
            ),
        }

        # Overall compliance
        compliance_result["compliant"] = all(
            check["compliant"] for check in compliance_result["checks"].values()
        )

        logger.info(f"Annex 9 compliance verified: {cmc_id} -> {compliance_result['compliant']}")
        return compliance_result

    async def get_background_check(self, record_id: str) -> BackgroundCheckRecord | None:
        """Retrieve background check record."""
        return self._background_checks.get(record_id)

    async def get_electronic_record(self, record_id: str) -> ElectronicRecord | None:
        """Retrieve electronic record."""
        return self._electronic_records.get(record_id)

    async def get_visa_free_record(self, cmc_id: str) -> VisaFreeEntryRecord | None:
        """Retrieve visa-free entry record for CMC."""
        for record in self._visa_free_records.values():
            if record.cmc_id == cmc_id:
                return record
        return None

    async def cleanup_expired_records(self) -> dict[str, int]:
        """Clean up expired records and return count of cleaned records."""
        logger.info("Cleaning up expired Annex 9 policy records")

        cleanup_count = {
            "background_checks": 0,
            "electronic_records": 0,
            "visa_free_records": 0,
        }

        now = datetime.now(timezone.utc)

        # Clean up expired background checks
        expired_bg_checks = [
            record_id
            for record_id, bg_check in self._background_checks.items()
            if bg_check.is_expired()
        ]

        for record_id in expired_bg_checks:
            del self._background_checks[record_id]
            cleanup_count["background_checks"] += 1

        # Archive old electronic records (beyond retention period)
        expired_electronic_records = [
            record_id
            for record_id, record in self._electronic_records.items()
            if record.archival_date and now > record.archival_date
        ]

        for record_id in expired_electronic_records:
            if self.storage:
                await self.storage.archive_electronic_record(self._electronic_records[record_id])
            del self._electronic_records[record_id]
            cleanup_count["electronic_records"] += 1

        # Clean up expired visa-free records
        expired_vf_records = [
            record_id
            for record_id, vf_record in self._visa_free_records.items()
            if vf_record.valid_until
            and now > vf_record.valid_until + timedelta(days=30)  # Grace period
        ]

        for record_id in expired_vf_records:
            del self._visa_free_records[record_id]
            cleanup_count["visa_free_records"] += 1

        logger.info(f"Cleanup completed: {cleanup_count}")
        return cleanup_count


# Global policy manager instance
_policy_manager: Annex9PolicyManager | None = None


def get_policy_manager() -> Annex9PolicyManager:
    """Get global Annex 9 policy manager instance."""
    if _policy_manager is None:
        # Initialize on first access
        globals()["_policy_manager"] = Annex9PolicyManager()
    return _policy_manager
