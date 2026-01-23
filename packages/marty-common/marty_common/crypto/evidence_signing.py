"""
Evidence Signing System for Tamper-Evident Audit Logs

This module implements a comprehensive evidence signing system that creates
tamper-evident audit logs for all verification outcomes and critical security
operations. It ensures integrity and non-repudiation of verification results.

Key Features:
1. Sign all verification outcomes with cryptographic evidence
2. Create immutable audit trails
3. Support various evidence formats (JSON, CBOR, etc.)
4. Timestamping and chaining for temporal integrity
5. Role-based evidence signing with proper key separation
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from .kms_provider import KeyOperation, KMSManager
from .role_separation import CryptoRole, KeyIdentity, KeyPurpose, create_evidence_key_identity


class EvidenceType(Enum):
    """Types of evidence that can be signed."""

    DOCUMENT_VERIFICATION = "document_verification"
    CERTIFICATE_VALIDATION = "certificate_validation"
    SIGNATURE_VERIFICATION = "signature_verification"
    PKI_PATH_VALIDATION = "pki_path_validation"
    REVOCATION_CHECK = "revocation_check"
    POLICY_EVALUATION = "policy_evaluation"
    TRUST_ANCHOR_VALIDATION = "trust_anchor_validation"
    BIOMETRIC_VERIFICATION = "biometric_verification"
    AUDIT_LOG_ENTRY = "audit_log_entry"
    SYSTEM_SECURITY_EVENT = "system_security_event"


class EvidenceFormat(Enum):
    """Supported evidence formats."""

    JSON = "json"
    CBOR = "cbor"
    XML = "xml"
    JWT = "jwt"  # For interoperability


class VerificationOutcome(Enum):
    """Possible outcomes of verification operations."""

    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"
    ERROR = "error"
    REVOKED = "revoked"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class EvidenceMetadata:
    """Metadata for evidence entries."""

    evidence_id: str
    evidence_type: EvidenceType
    timestamp: datetime
    version: str = "1.0"
    signer_id: str = ""
    chain_hash: str | None = None  # Hash of previous evidence for chaining
    correlation_id: str | None = None  # For correlating related evidence

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "signer_id": self.signer_id,
            "chain_hash": self.chain_hash,
            "correlation_id": self.correlation_id,
        }


@dataclass
class VerificationEvidence:
    """Evidence of a verification operation."""

    metadata: EvidenceMetadata
    subject: str  # What was verified (document ID, certificate DN, etc.)
    verification_method: str  # How it was verified
    outcome: VerificationOutcome
    details: dict[str, Any]  # Specific verification details
    errors: list[str] = None  # Any errors encountered
    warnings: list[str] = None  # Any warnings
    context: dict[str, Any] | None = None  # Additional context

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "metadata": self.metadata.to_dict(),
            "subject": self.subject,
            "verification_method": self.verification_method,
            "outcome": self.outcome.value,
            "details": self.details,
            "errors": self.errors,
            "warnings": self.warnings,
            "context": self.context,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


@dataclass
class SignedEvidence:
    """Evidence with cryptographic signature."""

    evidence: VerificationEvidence
    signature: bytes
    signature_algorithm: str
    signer_key_id: str
    signature_timestamp: datetime
    evidence_hash: str  # Hash of the evidence data

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "evidence": self.evidence.to_dict(),
            "signature": self.signature.hex(),
            "signature_algorithm": self.signature_algorithm,
            "signer_key_id": self.signer_key_id,
            "signature_timestamp": self.signature_timestamp.isoformat(),
            "evidence_hash": self.evidence_hash,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


class EvidenceChain:
    """Maintains a chain of evidence entries for temporal integrity."""

    def __init__(self):
        self.entries: list[SignedEvidence] = []
        self._last_hash: str | None = None

    def add_evidence(self, evidence: SignedEvidence) -> None:
        """Add evidence to the chain."""
        # Update chain hash in metadata if needed
        if self._last_hash and evidence.evidence.metadata.chain_hash is None:
            evidence.evidence.metadata.chain_hash = self._last_hash

        self.entries.append(evidence)
        self._last_hash = evidence.evidence_hash

    def verify_chain_integrity(self) -> bool:
        """Verify the integrity of the evidence chain."""
        if not self.entries:
            return True

        for i, entry in enumerate(self.entries):
            # Verify evidence hash
            computed_hash = self._compute_evidence_hash(entry.evidence)
            if computed_hash != entry.evidence_hash:
                return False

            # Verify chain linkage
            if i > 0:
                expected_chain_hash = self.entries[i - 1].evidence_hash
                if entry.evidence.metadata.chain_hash != expected_chain_hash:
                    return False

        return True

    def _compute_evidence_hash(self, evidence: VerificationEvidence) -> str:
        """Compute SHA-256 hash of evidence data."""
        evidence_json = evidence.to_json()
        return hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()

    def get_evidence_by_id(self, evidence_id: str) -> SignedEvidence | None:
        """Find evidence by ID."""
        for entry in self.entries:
            if entry.evidence.metadata.evidence_id == evidence_id:
                return entry
        return None

    def get_evidence_by_correlation(self, correlation_id: str) -> list[SignedEvidence]:
        """Find all evidence with the same correlation ID."""
        return [
            entry
            for entry in self.entries
            if entry.evidence.metadata.correlation_id == correlation_id
        ]


class EvidenceSigner:
    """Signs verification evidence for tamper-evident audit logs."""

    def __init__(self, kms_manager: KMSManager, service_id: str = "default"):
        self.kms_manager = kms_manager
        self.service_id = service_id
        self.evidence_chain = EvidenceChain()

        # Create evidence signing key identity
        self.evidence_key_identity = create_evidence_key_identity(service_id)

    async def initialize(self, algorithm: str = "ES256") -> None:
        """Initialize the evidence signer with a signing key."""
        # Generate evidence signing key if it doesn't exist
        if not await self.kms_manager.provider.key_exists(self.evidence_key_identity):
            await self.kms_manager.generate_key_for_role(
                role=CryptoRole.EVIDENCE,
                purpose=KeyPurpose.EVIDENCE_SIGNING,
                key_id=f"evidence-{self.service_id}",
                algorithm=algorithm,
            )

    async def sign_verification_outcome(
        self,
        subject: str,
        verification_method: str,
        outcome: VerificationOutcome,
        details: dict[str, Any],
        evidence_type: EvidenceType = EvidenceType.DOCUMENT_VERIFICATION,
        errors: list[str] = None,
        warnings: list[str] = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> SignedEvidence:
        """Sign a verification outcome to create tamper-evident evidence."""

        # Create evidence metadata
        evidence_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)

        metadata = EvidenceMetadata(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            timestamp=timestamp,
            signer_id=self.service_id,
            correlation_id=correlation_id,
        )

        # Create verification evidence
        evidence = VerificationEvidence(
            metadata=metadata,
            subject=subject,
            verification_method=verification_method,
            outcome=outcome,
            details=details,
            errors=errors or [],
            warnings=warnings or [],
            context=context,
        )

        # Compute evidence hash
        evidence_hash = hashlib.sha256(evidence.to_json().encode("utf-8")).hexdigest()

        # Sign the evidence hash
        signature = await self.kms_manager.sign_with_role_validation(
            key_identity=self.evidence_key_identity,
            data=evidence_hash.encode("utf-8"),
            requesting_role=CryptoRole.EVIDENCE,
            algorithm="SHA256",
        )

        # Create signed evidence
        signed_evidence = SignedEvidence(
            evidence=evidence,
            signature=signature,
            signature_algorithm="ES256",
            signer_key_id=self.evidence_key_identity.full_key_id,
            signature_timestamp=timestamp,
            evidence_hash=evidence_hash,
        )

        # Add to evidence chain
        self.evidence_chain.add_evidence(signed_evidence)

        return signed_evidence

    async def verify_evidence_signature(self, signed_evidence: SignedEvidence) -> bool:
        """Verify the signature on a piece of evidence."""
        try:
            # Get the public key for verification
            public_key_pem = await self.kms_manager.get_public_key_for_verification(
                key_identity=self.evidence_key_identity, requesting_role=CryptoRole.VERIFIER
            )

            # Load public key
            public_key = serialization.load_pem_public_key(public_key_pem)

            # Verify signature
            if isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(
                    signed_evidence.signature,
                    signed_evidence.evidence_hash.encode("utf-8"),
                    ec.ECDSA(hashes.SHA256()),
                )
                return True
            elif isinstance(public_key, rsa.RSAPublicKey):
                from cryptography.hazmat.primitives.asymmetric import padding

                public_key.verify(
                    signed_evidence.signature,
                    signed_evidence.evidence_hash.encode("utf-8"),
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
                return True
            else:
                return False

        except Exception:
            return False

    async def create_audit_log_evidence(
        self,
        operation: str,
        actor: str,
        resource: str,
        outcome: str,
        details: dict[str, Any],
        correlation_id: str | None = None,
    ) -> SignedEvidence:
        """Create signed evidence for audit log entries."""

        audit_details = {
            "operation": operation,
            "actor": actor,
            "resource": resource,
            "outcome": outcome,
            **details,
        }

        return await self.sign_verification_outcome(
            subject=f"{actor}:{resource}",
            verification_method="audit_logging",
            outcome=(
                VerificationOutcome.VALID if outcome == "success" else VerificationOutcome.ERROR
            ),
            details=audit_details,
            evidence_type=EvidenceType.AUDIT_LOG_ENTRY,
            correlation_id=correlation_id,
        )

    def get_evidence_chain(self) -> EvidenceChain:
        """Get the current evidence chain."""
        return self.evidence_chain

    def export_evidence_chain(self, format: EvidenceFormat = EvidenceFormat.JSON) -> str:
        """Export the evidence chain in the specified format."""
        if format == EvidenceFormat.JSON:
            chain_data = {
                "chain_metadata": {
                    "total_entries": len(self.evidence_chain.entries),
                    "export_timestamp": datetime.now(timezone.utc).isoformat(),
                    "signer_service": self.service_id,
                },
                "entries": [entry.to_dict() for entry in self.evidence_chain.entries],
            }
            return json.dumps(chain_data, indent=2, sort_keys=True)
        else:
            raise NotImplementedError(f"Format {format} not implemented")


class EvidenceVerifier:
    """Verifies signed evidence and evidence chains."""

    def __init__(self, kms_manager: KMSManager):
        self.kms_manager = kms_manager

    async def verify_evidence(self, signed_evidence: SignedEvidence) -> bool:
        """Verify a single piece of signed evidence."""
        try:
            # Recompute evidence hash
            computed_hash = hashlib.sha256(
                signed_evidence.evidence.to_json().encode("utf-8")
            ).hexdigest()

            if computed_hash != signed_evidence.evidence_hash:
                return False

            # Create key identity from signer key ID
            # This would need to be enhanced to parse the full key ID properly
            evidence_key_identity = KeyIdentity(
                role=CryptoRole.EVIDENCE,
                purpose=KeyPurpose.EVIDENCE_SIGNING,
                key_id=signed_evidence.signer_key_id.split(":")[-1],
            )

            # Get public key
            public_key_pem = await self.kms_manager.get_public_key_for_verification(
                key_identity=evidence_key_identity, requesting_role=CryptoRole.VERIFIER
            )

            # Load and verify signature
            public_key = serialization.load_pem_public_key(public_key_pem)

            if isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(
                    signed_evidence.signature,
                    signed_evidence.evidence_hash.encode("utf-8"),
                    ec.ECDSA(hashes.SHA256()),
                )
                return True
            elif isinstance(public_key, rsa.RSAPublicKey):
                from cryptography.hazmat.primitives.asymmetric import padding

                public_key.verify(
                    signed_evidence.signature,
                    signed_evidence.evidence_hash.encode("utf-8"),
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
                return True

            return False

        except Exception:
            return False

    async def verify_evidence_chain(self, evidence_chain: EvidenceChain) -> bool:
        """Verify an entire evidence chain."""
        # Verify chain integrity
        if not evidence_chain.verify_chain_integrity():
            return False

        # Verify each individual evidence signature
        for entry in evidence_chain.entries:
            if not await self.verify_evidence(entry):
                return False

        return True


# Example usage functions
async def example_document_verification_evidence(evidence_signer: EvidenceSigner):
    """Example of creating evidence for document verification."""

    # Simulate document verification
    document_id = "passport:US:123456789"
    verification_details = {
        "document_type": "passport",
        "issuing_country": "US",
        "document_number": "123456789",
        "security_features_checked": ["mrz", "chip", "visual_security"],
        "verification_timestamp": datetime.now(timezone.utc).isoformat(),
        "trust_anchor": "csca:us:generation:3",
    }

    # Create signed evidence
    signed_evidence = await evidence_signer.sign_verification_outcome(
        subject=document_id,
        verification_method="multi_factor_verification",
        outcome=VerificationOutcome.VALID,
        details=verification_details,
        evidence_type=EvidenceType.DOCUMENT_VERIFICATION,
    )

    print(f"Created evidence with ID: {signed_evidence.evidence.metadata.evidence_id}")
    return signed_evidence


async def example_audit_trail_creation(evidence_signer: EvidenceSigner):
    """Example of creating an audit trail for security operations."""

    correlation_id = str(uuid.uuid4())

    # Evidence for key generation
    await evidence_signer.create_audit_log_evidence(
        operation="key_generation",
        actor="system:key_manager",
        resource="dsc:us:passport:001",
        outcome="success",
        details={"algorithm": "ES256", "key_size": 256},
        correlation_id=correlation_id,
    )

    # Evidence for certificate creation
    await evidence_signer.create_audit_log_evidence(
        operation="certificate_creation",
        actor="system:csca_service",
        resource="dsc:us:passport:001",
        outcome="success",
        details={"validity_period": "3_years", "subject_dn": "CN=US Passport Signer"},
        correlation_id=correlation_id,
    )

    # Evidence for policy application
    await evidence_signer.create_audit_log_evidence(
        operation="policy_validation",
        actor="system:policy_engine",
        resource="document:passport:US:123456789",
        outcome="success",
        details={"policies_applied": ["security_level_1", "biometric_required"]},
        correlation_id=correlation_id,
    )

    # Get all related evidence
    related_evidence = evidence_signer.evidence_chain.get_evidence_by_correlation(correlation_id)
    print(f"Created audit trail with {len(related_evidence)} evidence entries")

    return related_evidence


if __name__ == "__main__":
    import asyncio

    from .kms_provider import KMSProvider, create_kms_manager

    async def main():
        # Create KMS manager
        kms = create_kms_manager(KMSProvider.SOFTWARE_HSM)

        # Create evidence signer
        evidence_signer = EvidenceSigner(kms, "verification_service_001")
        await evidence_signer.initialize()

        # Example usage
        await example_document_verification_evidence(evidence_signer)
        await example_audit_trail_creation(evidence_signer)

        # Export evidence chain
        chain_export = evidence_signer.export_evidence_chain()
        print("Evidence chain exported:")
        print(chain_export[:500] + "..." if len(chain_export) > 500 else chain_export)

        # Verify evidence chain
        verifier = EvidenceVerifier(kms)
        is_valid = await verifier.verify_evidence_chain(evidence_signer.get_evidence_chain())
        print(f"Evidence chain verification: {'VALID' if is_valid else 'INVALID'}")

    asyncio.run(main())
