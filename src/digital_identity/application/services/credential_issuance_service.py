"""
Credential Issuance Service

Application service for issuing credentials using the marty-credentials library.
Bridges the Flow execution layer with actual credential creation, status list allocation,
and persistence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from digital_identity.application.ports.outbound import (
    IssuedCredentialRepositoryPort,
)
from digital_identity.domain.entities import (
    CredentialTemplate,
    FlowExecution,
    IssuedCredential,
    RevocationBatch,
)
from digital_identity.domain.value_objects import (
    CredentialFormat,
    CredentialStatus,
    StatusListEntryRef,
)
from digital_identity.infrastructure.persistence.repositories import (
    CredentialTemplateRepository,
    RevocationBatchRepository,
)

logger = logging.getLogger(__name__)


def _native_sha256(data: bytes) -> str:
    """Return a SHA-256 hex digest from the canonical Rust backend."""

    from marty_plugin.native_backends import require_backend

    return require_backend("_marty_rs").sha256(data).hex()


class CredentialIssuanceService:
    """
    Service for issuing credentials.

    Integrates with:
    - marty-credentials Rust library for JWT-VC/mDoc creation
    - status_list module for revocation tracking
    - IssuedCredentialRepository for persistence
    """

    def __init__(
        self,
        credential_repository: IssuedCredentialRepositoryPort,
        credential_template_repository: CredentialTemplateRepository | None = None,
        revocation_batch_repository: RevocationBatchRepository | None = None,
        status_list_service: Any
        | None = None,  # StatusListService from status_list module
        jwt_issuer: Any | None = None,  # RustCredentialIssuer from marty_credentials
        mdoc_issuer: Any | None = None,  # RustMdocIssuer from marty_credentials
    ):
        self._credential_repo = credential_repository
        self._template_repo = credential_template_repository
        self._batch_repo = revocation_batch_repository
        self._status_list_service = status_list_service
        self._jwt_issuer = jwt_issuer
        self._mdoc_issuer = mdoc_issuer

    async def issue_credential(
        self,
        template: CredentialTemplate,
        claims: dict[str, Any],
        subject_id: str,
        flow_execution: FlowExecution,
        issuer_id: str,
        signing_key_jwk: dict[str, Any],
        credential_id: str | None = None,
    ) -> IssuedCredential:
        """
        Issue a credential.

        Args:
            template: The credential template defining structure
            claims: The claims to include in the credential
            subject_id: DID or identifier of the credential holder
            flow_execution: The flow execution that triggered issuance
            issuer_id: Identifier of the issuer
            signing_key_jwk: JWK for signing the credential
            credential_id: Optional custom credential ID (defaults to urn:uuid:...)

        Returns:
            IssuedCredential entity with metadata

        Raises:
            ValueError: If required parameters are missing or invalid
            RuntimeError: If credential creation fails
        """
        # Generate credential ID if not provided
        final_credential_id = credential_id or f"urn:uuid:{uuid4()}"

        # Validate credential_id format
        if not final_credential_id.startswith(("urn:", "http://", "https://")):
            raise ValueError("credential_id must be a valid URI")

        # Allocate status list entry for revocation
        logger.info(f"Allocating status entry for credential {final_credential_id}")
        status_entry = await self._status_list_service.allocate_status_entry(
            credential_id=final_credential_id,
            issuer_id=issuer_id,
            purpose="revocation",  # StatusPurpose.REVOCATION
        )

        # Build status list entry reference
        status_list_entry = StatusListEntryRef(
            purpose="revocation",
            status_list_credential_url=f"https://{issuer_id}/status/revocation/{status_entry.shard_index}",
            status_list_index=status_entry.bit_index,
            shard_id=status_entry.shard_id,
        )

        # Create the credential based on format
        if template.default_format == CredentialFormat.JWT_VC:
            credential_bytes = await self._create_jwt_vc(
                credential_id=final_credential_id,
                template=template,
                claims=claims,
                subject_id=subject_id,
                issuer_id=issuer_id,
                signing_key_jwk=signing_key_jwk,
                status_entry=status_list_entry,
            )
        elif template.default_format == CredentialFormat.MDOC:
            credential_bytes = await self._create_mdoc(
                credential_id=final_credential_id,
                template=template,
                claims=claims,
                subject_id=subject_id,
                issuer_id=issuer_id,
                signing_key_jwk=signing_key_jwk,
                status_entry=status_list_entry,
            )
        else:
            raise ValueError(
                f"Unsupported credential format: {template.default_format}"
            )

        # Compute credential hash for audit
        credential_hash = _native_sha256(credential_bytes)

        # Compute subject claims hash for privacy
        subject_claims_str = str(sorted(claims.items()))
        subject_claims_hash = _native_sha256(subject_claims_str.encode())

        # Create IssuedCredential entity
        issued_credential = IssuedCredential(
            id=str(uuid4()),
            credential_id=final_credential_id,
            credential_type=template.credential_type,
            credential_format=template.default_format,
            flow_execution_id=flow_execution.id,
            credential_template_id=template.id,
            subject_id=subject_id,
            subject_claims_hash=subject_claims_hash,
            issued_at=datetime.now(timezone.utc),
            valid_from=datetime.now(timezone.utc),
            valid_until=None,  # TODO: Calculate from template validity rules
            status=CredentialStatus.ACTIVE,
            status_list_entries=[status_list_entry],
            credential_hash=credential_hash,
        )

        # Persist
        await self._credential_repo.save(issued_credential)

        logger.info(f"Issued credential {final_credential_id} for subject {subject_id}")

        return issued_credential

    async def _create_jwt_vc(
        self,
        credential_id: str,
        template: CredentialTemplate,
        claims: dict[str, Any],
        subject_id: str,
        issuer_id: str,
        signing_key_jwk: dict[str, Any],
        status_entry: StatusListEntryRef,
    ) -> bytes:
        """Create a JWT Verifiable Credential."""
        if not self._jwt_issuer:
            raise RuntimeError("JWT issuer not configured")

        # Build credential subject
        credential_subject = {
            "id": subject_id,
            **claims,
        }

        # Build credentialStatus
        credential_status = {
            "id": f"{status_entry.status_list_credential_url}#{status_entry.status_list_index}",
            "type": "BitstringStatusListEntry",
            "statusPurpose": status_entry.purpose,
            "statusListIndex": str(status_entry.status_list_index),
            "statusListCredential": status_entry.status_list_credential_url,
        }

        # Create JWT-VC using the configured native-backed issuer.
        jwt_vc = self._jwt_issuer.create_credential(
            credential_id=credential_id,
            issuer_did=issuer_id,
            subject_claims=credential_subject,
            credential_type=template.credential_type,
            signing_key_jwk=json.dumps(signing_key_jwk),
            credential_status=credential_status,
        )

        return jwt_vc.encode("utf-8")

    async def _create_mdoc(
        self,
        credential_id: str,
        template: CredentialTemplate,
        claims: dict[str, Any],
        subject_id: str,
        issuer_id: str,
        signing_key_jwk: dict[str, Any],
        status_entry: StatusListEntryRef,
    ) -> bytes:
        """Create an mDoc credential."""
        if not self._mdoc_issuer:
            raise RuntimeError("mDoc issuer not configured")

        from marty_plugin.native_backends import NativeOperationError

        raise NativeOperationError(
            "mDoc issuance requires the native issuer adapter; no Python fallback is available"
        )

    async def issue_credential_from_request(
        self,
        organization_id: str,
        credential_template_id: str,
        flow_execution_id: str | None,
        subject_claims: dict[str, Any],
        holder_identifier: str,
        application_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Issue a credential from REST API request.

        Returns credential to caller (not stored) along with metadata.
        Only stores approved application data + hash + status list entries.
        """
        raise RuntimeError(
            "Credential issuance requires an organization-scoped issuer profile "
            "and native or remote signer; ephemeral Python/provider keys are disabled"
        )

    async def verify_credential(
        self,
        organization_id: str,
        credential: dict[str, Any] | str,
        presentation_policy_id: str | None,
        trust_profile_id: str | None,
    ) -> dict[str, Any]:
        """
        Verify a credential.

        Uses marty-credentials VerificationService with trust profile validation.
        """
        # Convert credential to JWT string if dict
        if isinstance(credential, dict):
            if not (credential.get("jwt") or credential.get("credential")):
                raise ValueError(
                    "Credential dict must contain 'jwt' or 'credential' field"
                )
        elif not isinstance(credential, str) or not credential:
            raise ValueError("Credential must be a non-empty compact token")

        # A token cannot be verified until its issuer key is resolved through
        # the selected trust profile. Parsing claims before that boundary would
        # recreate the old fail-open behavior of the non-cryptographic
        # ``verify_jwt`` helper.
        return {
            "valid": False,
            "error": (
                "Credential verification requires issuer key resolution through "
                "a configured trust profile"
            ),
            "checks": {
                "signature": False,
                "expiration": False,
                "status_list": None,
                "trust_profile": False,
            },
        }

    async def revoke_credential(
        self,
        organization_id: str,
        credential_id: str,
        revocation_reason: str | None,
        immediate: bool = False,
    ) -> dict[str, Any]:
        """
        Revoke a single credential.

        If immediate=True, updates status list immediately (privacy warning).
        If immediate=False, queues for batch processing based on template interval.
        """
        # Load issued credential
        issued_cred = await self._credential_repo.get_by_credential_id(credential_id)
        if not issued_cred:
            raise ValueError(f"Credential {credential_id} not found")

        # Update status
        now = datetime.now(timezone.utc)
        issued_cred.status = CredentialStatus.REVOKED
        issued_cred.revoked_at = now
        issued_cred.revocation_reason = revocation_reason
        issued_cred.revoked_by = organization_id  # TODO: Get from auth context
        issued_cred.updated_at = now
        issued_cred.version += 1

        # Update status list
        if immediate:
            # WARNING: Immediate update may compromise privacy (correlatable timing)
            logger.warning(
                f"Immediate revocation for {credential_id} may compromise holder privacy"
            )
            # TODO: Call status_list service to update bitstring immediately
            for entry in issued_cred.status_list_entries:
                logger.info(
                    f"Updating status list {entry.status_list_credential_url} "
                    f"index {entry.status_list_index} to revoked"
                )
        else:
            # Queue for batch processing (W3C privacy-preserving recommendation)
            logger.info(
                f"Queued credential {credential_id} for batch revocation "
                f"(template={issued_cred.credential_template_id})"
            )
            # TODO: Add to revocation batch queue

        # Save updated credential
        await self._credential_repo.save(issued_cred)

        logger.info(
            f"Revoked credential {credential_id} "
            f"(immediate={immediate}, reason={revocation_reason})"
        )

        return {
            "credential_id": credential_id,
            "status": "revoked",
            "revoked_at": now.isoformat(),
            "immediate": immediate,
            "privacy_warning": immediate,
        }

    async def batch_revoke_credentials(
        self,
        organization_id: str,
        credential_ids: list[str],
        revocation_reason: str | None,
        immediate: bool = False,
    ) -> dict[str, Any]:
        """
        Batch revoke multiple credentials.

        Follows W3C Bitstring Status List privacy recommendations by batching.
        Interval determined by credential template configuration (1h/6h/24h).
        """
        batch_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Load all credentials
        credentials = []
        for cred_id in credential_ids:
            cred = await self._credential_repo.get_by_credential_id(cred_id)
            if cred:
                credentials.append(cred)
            else:
                logger.warning(f"Credential {cred_id} not found, skipping")

        if not credentials:
            raise ValueError("No valid credentials found to revoke")

        # Group by credential template for batch processing
        by_template = {}
        for cred in credentials:
            template_id = cred.credential_template_id
            if template_id not in by_template:
                by_template[template_id] = []
            by_template[template_id].append(cred)

        # Update all credential statuses
        for cred in credentials:
            cred.status = CredentialStatus.REVOKED
            cred.revoked_at = now
            cred.revocation_reason = revocation_reason
            cred.revoked_by = organization_id
            cred.updated_at = now
            cred.version += 1
            await self._credential_repo.save(cred)

        # Determine scheduling
        if immediate:
            # Update all status lists now (privacy warning)
            logger.warning(
                f"Immediate batch revocation for {len(credentials)} credentials "
                f"may compromise holder privacy"
            )
            scheduled_for = now
            revocation_interval = "0h"
            # TODO: Update status lists immediately
        else:
            # Schedule for next batch window (default 6h)
            # TODO: Get interval from credential template config
            batch_interval_hours = 6
            scheduled_for = now + timedelta(hours=batch_interval_hours)
            revocation_interval = f"{batch_interval_hours}h"
            logger.info(
                f"Scheduled batch {batch_id} with {len(credentials)} credentials "
                f"for {scheduled_for.isoformat()} "
                f"(interval={batch_interval_hours}h)"
            )

        # Create batch record for each template
        if self._batch_repo:
            for template_id, template_creds in by_template.items():
                batch = RevocationBatch(
                    id=f"{batch_id}-{template_id}",
                    organization_id=organization_id,
                    credential_template_id=template_id,
                    credential_count=len(template_creds),
                    credential_ids=[c.credential_id for c in template_creds],
                    status="completed" if immediate else "queued",
                    scheduled_for=scheduled_for,
                    completed_at=now if immediate else None,
                    revocation_interval=revocation_interval,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
                await self._batch_repo.save(batch)
                logger.info(
                    f"Created batch record {batch.id} for template {template_id}"
                )
        else:
            logger.warning("Batch repository not available, skipping batch persistence")

        return {
            "batch_id": batch_id,
            "credential_count": len(credentials),
            "scheduled_for": scheduled_for.isoformat(),
            "immediate": immediate,
            "templates": list(by_template.keys()),
            "message": (
                "Batch revocation queued. Status lists will be updated at scheduled time "
                "to preserve holder privacy per W3C recommendations."
            ),
        }

    async def list_revocation_batches(
        self,
        organization_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List pending and completed revocation batches.

        Returns batch status per credential template.
        """
        logger.info(
            f"Listing revocation batches for org {organization_id} (status={status})"
        )

        if not self._batch_repo:
            logger.warning("Batch repository not available, returning empty list")
            return []

        # Query batches from repository
        batches = await self._batch_repo.list_by_organization(
            organization_id=organization_id,
            skip=0,
            limit=100,
        )

        # Filter by status if specified
        if status:
            batches = [b for b in batches if b.status == status]

        # Convert to response format
        return [
            {
                "batch_id": batch.id,
                "organization_id": batch.organization_id,
                "credential_template_id": batch.credential_template_id,
                "credential_count": batch.credential_count,
                "status": batch.status,
                "scheduled_for": batch.scheduled_for.isoformat(),
                "completed_at": batch.completed_at.isoformat()
                if batch.completed_at
                else None,
                "revocation_interval": batch.revocation_interval,
                "created_at": batch.created_at.isoformat(),
            }
            for batch in batches
        ]
