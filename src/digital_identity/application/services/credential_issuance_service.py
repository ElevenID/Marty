"""
Credential Issuance Service

Application service for issuing credentials using the marty-credentials library.
Bridges the Flow execution layer with actual credential creation, status list allocation,
and persistence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from digital_identity.domain.entities import (
    CredentialTemplate,
    IssuedCredential,
    FlowExecution,
)
from digital_identity.domain.value_objects import (
    CredentialFormat,
    CredentialStatus,
    StatusListEntryRef,
)
from digital_identity.application.ports.outbound import (
    IssuedCredentialRepositoryPort,
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
        status_list_service: Any,  # StatusListService from status_list module
        jwt_issuer: Any | None = None,  # RustCredentialIssuer from marty_credentials
        mdoc_issuer: Any | None = None,  # RustMdocIssuer from marty_credentials
    ):
        self._credential_repo = credential_repository
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
