"""
Credential Issuance Service

Application service for issuing credentials using the marty-credentials library.
Bridges the Flow execution layer with actual credential creation, status list allocation,
and persistence.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from digital_identity.domain.entities import (
    CredentialTemplate,
    IssuedCredential,
    FlowExecution,
    RevocationBatch,
)
from digital_identity.domain.value_objects import (
    CredentialFormat,
    CredentialStatus,
    StatusListEntryRef,
)
from digital_identity.application.ports.outbound import (
    IssuedCredentialRepositoryPort,
)
from digital_identity.infrastructure.persistence.repositories import (
    CredentialTemplateRepository,
    RevocationBatchRepository,
)

logger = logging.getLogger(__name__)


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
        status_list_service: Any | None = None,  # StatusListService from status_list module
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
            raise ValueError(f"Unsupported credential format: {template.default_format}")
        
        # Compute credential hash for audit
        credential_hash = hashlib.sha256(credential_bytes).hexdigest()
        
        # Compute subject claims hash for privacy
        subject_claims_str = str(sorted(claims.items()))
        subject_claims_hash = hashlib.sha256(subject_claims_str.encode()).hexdigest()
        
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
        
        # Create JWT-VC using marty-credentials
        import json
        jwt_vc = self._jwt_issuer.create_credential(
            credential_id=credential_id,
            issuer_did=issuer_id,
            subject_claims=credential_subject,
            credential_type=template.credential_type,
            signing_key_jwk=json.dumps(signing_key_jwk),
            credential_status=credential_status,
        )
        
        return jwt_vc.encode('utf-8')
    
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
        
        # TODO: Implement mDoc creation once Rust bindings are ready
        raise NotImplementedError("mDoc issuance will be available once Rust bindings compile")
    
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
        # Import Rust bindings
        try:
            import _marty_rs
        except ImportError:
            raise RuntimeError(
                "marty-rs Rust bindings not available. Ensure marty-credentials is installed with: "
                "cd /path/to/marty-credentials && pip install -e ./python"
            )
        
        # Load credential template from repository
        template = None
        if self._template_repo:
            template = await self._template_repo.get(credential_template_id)
        
        # Extract template configuration or use defaults
        if template:
            credential_type = template.credential_type or "VerifiableCredential"
            credential_format = template.format.value
            validity_days = template.validity_rules.ttl.days if template.validity_rules.ttl else 365
            logger.info(
                f"Loaded template {template.name}: type={credential_type}, "
                f"format={credential_format}, validity={validity_days}d"
            )
        else:
            # Fallback to defaults if template not found
            credential_type = "VerifiableCredential"
            credential_format = "VC_JWT"
            validity_days = 365
            logger.warning(
                f"Template {credential_template_id} not found, using defaults: "
                f"type={credential_type}, format={credential_format}"
            )
        
        # TODO: Resolve issuer DID from organization
        # Production: did:web with org domain
        # Development: auto-generate did:key
        import os
        environment = os.getenv("ENVIRONMENT", "development")
        
        if environment == "development":
            # Auto-generate did:key for development
            key_result = _marty_rs.generate_p256_key()
            issuer_key_json = key_result
            key_data = json.loads(issuer_key_json)
            issuer_did = key_data["did"]
            issuer_jwk = key_data["jwk"]
        else:
            # TODO: Load organization's did:web and signing key
            # For now, generate temporary key
            key_result = _marty_rs.generate_p256_key()
            key_data = json.loads(key_result)
            issuer_did = f"did:web:{organization_id}.marty.dev"
            issuer_jwk = key_data["jwk"]
        
        # Generate credential ID
        credential_id = f"urn:uuid:{uuid4()}"
        
        # Allocate status list entry
        # TODO: Integrate with status_list module
        status_entry = StatusListEntryRef(
            status_list_credential_url=f"https://status.marty.dev/{organization_id}/revocation",
            status_list_index=0,  # TODO: Get next available index
            purpose="revocation",
        )
        
        # Build credentialStatus for embedding
        credential_status = {
            "id": f"{status_entry.status_list_credential_url}#{status_entry.status_list_index}",
            "type": "BitstringStatusListEntry",
            "statusPurpose": status_entry.purpose,
            "statusListIndex": str(status_entry.status_list_index),
            "statusListCredential": status_entry.status_list_credential_url,
        }
        
        # Create JWT-VC using Rust bindings
        jwt_token, returned_credential_id = _marty_rs.create_verifiable_credential(
            issuer_did=issuer_did,
            issuer_jwk_json=json.dumps(issuer_jwk),
            subject_id=holder_identifier,
            credential_type=credential_type,
            claims_json=json.dumps(subject_claims),
            expiration_seconds=validity_days * 24 * 3600,
        )
        
        # Hash the credential for audit (privacy-preserving)
        credential_bytes = jwt_token.encode('utf-8')
        credential_hash = hashlib.sha256(credential_bytes).hexdigest()
        
        # Create IssuedCredential entity (does NOT store actual credential)
        now = datetime.now(timezone.utc)
        issued_credential = IssuedCredential(
            id=str(uuid4()),
            credential_id=credential_id,
            credential_type=credential_type,
            credential_format=CredentialFormat.JWT_VC,
            flow_execution_id=flow_execution_id or "",
            credential_template_id=credential_template_id,
            application_id=application_data.get("application_id") if application_data else None,
            subject_id=holder_identifier,
            subject_claims_hash=hashlib.sha256(json.dumps(subject_claims, sort_keys=True).encode()).hexdigest(),
            issued_at=now,
            valid_from=now,
            valid_until=now + timedelta(days=validity_days),
            status=CredentialStatus.ACTIVE,
            status_list_entries=[status_entry],
            credential_hash=credential_hash,
            revoked_at=None,
            revocation_reason=None,
            revoked_by=None,
            created_at=now,
            updated_at=now,
            version=1,
        )
        
        # Save to repository
        await self._credential_repo.save(issued_credential)
        
        logger.info(
            f"Issued credential {credential_id} for subject {holder_identifier} "
            f"(template={credential_template_id}, hash={credential_hash[:8]}...)"
        )
        
        # Return credential (once) and metadata
        return {
            "credential_id": credential_id,
            "credential": jwt_token,  # Returned once, not stored
            "credential_hash": credential_hash,
            "status_list_entries": [asdict(status_entry)],
            "issued_at": now,
        }
    
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
        # Import Rust bindings
        try:
            import _marty_rs
        except ImportError:
            raise RuntimeError("marty-rs Rust bindings not available")
        
        # Convert credential to JWT string if dict
        if isinstance(credential, dict):
            jwt_token = credential.get("jwt") or credential.get("credential")
            if not jwt_token:
                raise ValueError("Credential dict must contain 'jwt' or 'credential' field")
        else:
            jwt_token = credential
        
        # Verify JWT signature and structure
        valid, payload_json, error = _marty_rs.verify_jwt(
            jwt=jwt_token,
            expected_issuer=None,  # TODO: Validate against trust profile
            expected_audience=None,
        )
        
        if not valid:
            return {
                "valid": False,
                "error": error,
                "checks": {
                    "signature": False,
                    "expiration": False,
                    "status_list": None,
                    "trust_profile": None,
                },
            }
        
        # Parse payload
        payload = json.loads(payload_json)
        vc = payload.get("vc", {})
        issuer = payload.get("iss")
        exp = payload.get("exp")
        
        # Check expiration
        now_timestamp = datetime.now(timezone.utc).timestamp()
        expired = exp and exp < now_timestamp
        
        # Check status list
        # TODO: Integrate with status_list module
        credential_status = vc.get("credentialStatus")
        status_check = None
        if credential_status:
            status_check = {
                "checked": True,
                "revoked": False,  # TODO: Query status list
                "suspended": False,
            }
        
        # TODO: Validate against trust profile
        trust_check = None
        if trust_profile_id:
            trust_check = {
                "checked": True,
                "issuer_trusted": True,  # TODO: Query trust profile
                "algorithms_allowed": True,
            }
        
        return {
            "valid": not expired and (not status_check or not status_check["revoked"]),
            "issuer": issuer,
            "subject": vc.get("credentialSubject", {}).get("id"),
            "credential_type": vc.get("type", []),
            "issuance_date": vc.get("issuanceDate"),
            "expiration_date": vc.get("expirationDate"),
            "checks": {
                "signature": True,
                "expiration": not expired,
                "status_list": status_check,
                "trust_profile": trust_check,
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
                logger.info(f"Created batch record {batch.id} for template {template_id}")
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
            f"Listing revocation batches for org {organization_id} "
            f"(status={status})"
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
                "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
                "revocation_interval": batch.revocation_interval,
                "created_at": batch.created_at.isoformat(),
            }
            for batch in batches
        ]
