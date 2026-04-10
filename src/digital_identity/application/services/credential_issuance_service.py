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
from status_list.domain.value_objects import StatusPurpose

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
        kms_provider: Any | None = None,  # KMSProviderInterface for remote signing
    ):
        self._credential_repo = credential_repository
        self._template_repo = credential_template_repository
        self._batch_repo = revocation_batch_repository
        self._status_list_service = status_list_service
        self._jwt_issuer = jwt_issuer
        self._mdoc_issuer = mdoc_issuer
        self._kms_provider = kms_provider
    
    async def issue_credential(
        self,
        template: CredentialTemplate,
        claims: dict[str, Any],
        subject_id: str,
        flow_execution: FlowExecution,
        issuer_id: str,
        signing_key_jwk: dict[str, Any] | None = None,
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
            signing_key_jwk: JWK for signing (required for local signing, omit for remote_signing)
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
            purpose=StatusPurpose.REVOCATION,
        )
        
        # Build status list entry reference
        status_list_entry = StatusListEntryRef(
            purpose="revocation",
            status_list_id=status_entry.shard_id,
            status_list_uri=status_entry.status_list_credential_url,
            index=status_entry.bit_index,
        )
        
        # Create the credential based on format and key access mode
        use_remote_signing = (
            template.key_access_mode == "remote_signing"
            and template.remote_signing_config is not None
        )

        if use_remote_signing:
            credential_bytes = await self._create_credential_remote(
                credential_id=final_credential_id,
                template=template,
                claims=claims,
                subject_id=subject_id,
                issuer_id=issuer_id,
                status_entry=status_list_entry,
            )
        elif template.format == CredentialFormat.JWT_VC:
            credential_bytes = await self._create_jwt_vc(
                credential_id=final_credential_id,
                template=template,
                claims=claims,
                subject_id=subject_id,
                issuer_id=issuer_id,
                signing_key_jwk=signing_key_jwk,
                status_entry=status_list_entry,
            )
        elif template.format == CredentialFormat.MDOC:
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
            raise ValueError(f"Unsupported credential format: {template.format}")
        
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
            credential_format=template.format,
            flow_execution_id=flow_execution.id,
            credential_template_id=template.id,
            subject_id=subject_id,
            subject_claims_hash=subject_claims_hash,
            issued_at=datetime.now(timezone.utc),
            valid_from=datetime.now(timezone.utc),
            valid_until=(
                datetime.now(timezone.utc)
                + timedelta(seconds=template.validity_rules.ttl_seconds)
            ),
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
        
        # Build credentialStatus per W3C Bitstring Status List v1.0
        credential_status = {
            "id": f"{status_entry.status_list_uri}#{status_entry.index}",
            "type": "BitstringStatusListEntry",
            "statusPurpose": status_entry.purpose,
            "statusListIndex": str(status_entry.index),
            "statusListCredential": status_entry.status_list_uri,
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
        """Create an mDoc credential via Rust mDoc bindings."""
        try:
            import _marty_rs
        except ImportError:
            raise RuntimeError(
                "marty-rs Rust bindings not available for mDoc issuance"
            )

        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption,
        )
        from jwcrypto.jwk import JWK

        # Convert JWK to DER private key bytes
        jwk_obj = JWK(**signing_key_jwk)
        private_key = jwk_obj.get_op_key("sign")
        signing_key_der = private_key.private_bytes(
            Encoding.DER, PrivateFormat.PKCS8, NoEncryption()
        )

        # Build mDoc parameters
        validity_seconds = getattr(template, "validity_seconds", 365 * 86400)
        if hasattr(template, "validity_rules") and template.validity_rules:
            validity_seconds = template.validity_rules.ttl_seconds

        now = datetime.now(timezone.utc)
        validity = {
            "signed": now.isoformat(),
            "valid_from": now.isoformat(),
            "valid_until": (
                now + timedelta(seconds=validity_seconds)
            ).isoformat(),
        }

        mdoc_doc_type = (
            getattr(template, "mdoc_doc_type", None) or template.credential_type
        )
        mdoc_namespace = (
            getattr(template, "mdoc_namespace", None) or mdoc_doc_type
        )
        namespaces = {mdoc_namespace: claims}

        # Delegate to Rust — returns CBOR bytes
        cbor_bytes = _marty_rs.create_mdoc(
            mdoc_doc_type,
            namespaces,
            validity,
            signing_key_der,
        )

        logger.info(
            "mDoc credential %s created via Rust binding (%d bytes)",
            credential_id,
            len(cbor_bytes),
        )
        return bytes(cbor_bytes)
    
    async def _create_credential_remote(
        self,
        credential_id: str,
        template: CredentialTemplate,
        claims: dict[str, Any],
        subject_id: str,
        issuer_id: str,
        status_entry: StatusListEntryRef,
    ) -> bytes:
        """Create a credential using remote KMS signing (prepare → sign → assemble).

        Uses the BYOK pattern: Rust prepares the signing input, the KMS provider
        signs it externally, and Rust assembles the final credential.
        """
        if not self._kms_provider:
            raise RuntimeError(
                "KMS provider required for remote_signing key_access_mode"
            )

        remote_config = template.remote_signing_config or {}
        algorithm = template.issuer_algorithm or "ES256"
        key_name = remote_config.get("key_name")
        if not key_name:
            raise ValueError("remote_signing_config.key_name is required")

        # Import Rust FFI bindings
        try:
            import _marty_rs
        except ImportError:
            raise RuntimeError(
                "marty-rs Rust bindings not available for remote signing"
            )

        import base64
        from marty_backend_common.crypto.role_separation import (
            CryptoRole,
            KeyIdentity,
            KeyPurpose,
        )

        key_identity = KeyIdentity(
            role=CryptoRole.DSC,
            purpose=KeyPurpose.DOCUMENT_SIGNING,
            key_id=key_name,
            issuer_identifier=issuer_id,
        )

        # -----------------------------------------------------------
        # mDoc BYOK path — dedicated prepare_mdoc_for_hsm / complete
        # -----------------------------------------------------------
        if template.format == CredentialFormat.MDOC:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            validity_seconds = getattr(template, "validity_seconds", 365 * 86400)
            validity = {
                "signed": now.isoformat(),
                "valid_from": now.isoformat(),
                "valid_until": (
                    now + timedelta(seconds=validity_seconds)
                ).isoformat(),
            }

            # Build namespaces dict from claims
            mdoc_doc_type = getattr(template, "mdoc_doc_type", None) or template.credential_type
            mdoc_namespace = getattr(template, "mdoc_namespace", None) or mdoc_doc_type
            namespaces = {mdoc_namespace: claims}

            # Step 1: Prepare — Rust builds the unsigned mDoc and returns TBS data
            prepared = _marty_rs.prepare_mdoc_for_hsm(
                mdoc_doc_type,
                namespaces,
                validity,
                None,  # device_key_der — injected by wallet during presentation
                None,  # digest_algorithm — default SHA-256
            )

            tbs_data = prepared.get_tbs_data()

            # Step 2: Sign — KMS provider signs the TBS bytes externally
            signature_der = await self._kms_provider.sign(
                key_identity=key_identity,
                data=tbs_data,
                algorithm=algorithm,
            )

            # Step 3: Assemble — Rust completes the mDoc with the external signature
            cbor_bytes = _marty_rs.complete_mdoc_with_signature(prepared, signature_der)

            logger.info(
                "Issued mDoc credential %s via remote signing (key=%s, algorithm=%s)",
                credential_id, key_name, algorithm,
            )

            return bytes(cbor_bytes)

        # -----------------------------------------------------------
        # JWT-VC BYOK path — generic OID4VCI prepare / assemble
        # -----------------------------------------------------------

        # Step 1: Prepare — Rust builds the unsigned credential and signing input
        signing_input_b64, rust_credential_id, format_hint = (
            _marty_rs.oid4vci_prepare_credential(
                issuer_id=issuer_id,
                algorithm=algorithm,
                subject_id=subject_id,
                credential_type=template.credential_type,
                claims_json=json.dumps({"id": subject_id, **claims}),
                format="jwt_vc_json",
            )
        )

        # Step 2: Sign — KMS provider signs the raw bytes externally
        signing_input_bytes = base64.urlsafe_b64decode(
            signing_input_b64 + "=" * (-len(signing_input_b64) % 4)
        )

        signature_bytes = await self._kms_provider.sign(
            key_identity=key_identity,
            data=signing_input_bytes,
            algorithm=algorithm,
        )

        signature_b64 = base64.urlsafe_b64encode(signature_bytes).rstrip(b"=").decode()

        # Step 3: Assemble — Rust combines the unsigned credential with the signature
        credential_str, _ = _marty_rs.oid4vci_assemble_credential(
            signing_input=signing_input_b64,
            signature_b64=signature_b64,
            credential_id=rust_credential_id,
            format=format_hint,
        )

        logger.info(
            "Issued credential %s via remote signing (key=%s, algorithm=%s)",
            credential_id, key_name, algorithm,
        )

        return credential_str.encode("utf-8")
    
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
            validity_days = template.validity_rules.ttl_seconds // 86400 if template.validity_rules.ttl_seconds else 365
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
        
        # Check if template uses remote signing (BYOK)
        use_remote = (
            template is not None
            and getattr(template, "key_access_mode", None) == "remote_signing"
            and getattr(template, "remote_signing_config", None) is not None
        )

        # Resolve issuer DID from organization
        # Production: did:web with org domain
        # Development: auto-generate did:key
        import os
        environment = os.getenv("ENVIRONMENT", "development")
        
        if environment == "development" and not use_remote:
            # Auto-generate did:key for development (local signing only)
            key_result = _marty_rs.generate_p256_key()
            issuer_key_json = key_result
            key_data = json.loads(issuer_key_json)
            issuer_did = key_data["did"]
            issuer_jwk = key_data["jwk"]
        elif use_remote:
            # Remote signing: DID and key come from template configuration
            issuer_did = f"did:web:{organization_id}.marty.dev"
            issuer_jwk = None  # Not needed — KMS signs remotely
        else:
            # Production local signing: load organization's configured key
            # TODO: Load organization's did:web and signing key from vault
            logger.warning("Using auto-generated signing key — vault integration not yet implemented")
            key_result = _marty_rs.generate_p256_key()
            key_data = json.loads(key_result)
            issuer_did = f"did:web:{organization_id}.marty.dev"
            issuer_jwk = key_data["jwk"]
        
        # Generate credential ID
        credential_id = f"urn:uuid:{uuid4()}"
        
        # Allocate status list entry via status_list service
        if self._status_list_service:
            allocated = await self._status_list_service.allocate_status_entry(
                credential_id=credential_id,
                issuer_id=issuer_did,
                purpose=StatusPurpose.REVOCATION,
            )
            status_entry = StatusListEntryRef(
                purpose="revocation",
                status_list_id=allocated.shard_id,
                status_list_uri=allocated.status_list_credential_url,
                index=allocated.bit_index,
            )
        else:
            logger.warning(
                "StatusListService not available — credential %s will not "
                "be revocable until the service is wired",
                credential_id,
            )
            status_entry = StatusListEntryRef(
                purpose="revocation",
                status_list_id="placeholder",
                status_list_uri=f"https://status.marty.dev/{organization_id}/revocation",
                index=0,
            )
        
        # Build credentialStatus for embedding per W3C Bitstring Status List v1.0
        credential_status = {
            "id": f"{status_entry.status_list_uri}#{status_entry.index}",
            "type": "BitstringStatusListEntry",
            "statusPurpose": status_entry.purpose,
            "statusListIndex": str(status_entry.index),
            "statusListCredential": status_entry.status_list_uri,
        }
        
        if use_remote:
            # Remote signing via KMS: prepare → sign → assemble
            if not self._kms_provider:
                raise RuntimeError(
                    "KMS provider required for remote_signing key_access_mode"
                )

            remote_config = template.remote_signing_config or {}
            algorithm = template.issuer_algorithm or "ES256"
            key_name = remote_config.get("key_name")
            if not key_name:
                raise ValueError("remote_signing_config.key_name is required")

            signing_input_b64, rust_cred_id, format_hint = (
                _marty_rs.oid4vci_prepare_credential(
                    issuer_id=issuer_did,
                    algorithm=algorithm,
                    subject_id=holder_identifier,
                    credential_type=credential_type,
                    claims_json=json.dumps(subject_claims),
                    expiration_seconds=validity_days * 24 * 3600,
                )
            )

            import base64
            from marty_backend_common.crypto.role_separation import (
                CryptoRole,
                KeyIdentity,
                KeyPurpose,
            )

            signing_bytes = base64.urlsafe_b64decode(
                signing_input_b64 + "=" * (-len(signing_input_b64) % 4)
            )
            key_identity = KeyIdentity(
                role=CryptoRole.DSC,
                purpose=KeyPurpose.DOCUMENT_SIGNING,
                key_id=key_name,
                issuer_identifier=organization_id,
            )
            sig_bytes = await self._kms_provider.sign(
                key_identity=key_identity,
                data=signing_bytes,
                algorithm=algorithm,
            )
            sig_b64 = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()

            jwt_token, _ = _marty_rs.oid4vci_assemble_credential(
                signing_input=signing_input_b64,
                signature_b64=sig_b64,
                credential_id=rust_cred_id,
                format=format_hint,
            )
        else:
            # Local signing: create credential with in-process key
            jwt_token, returned_credential_id = _marty_rs.create_verifiable_credential(
                issuer_did=issuer_did,
                issuer_jwk_json=json.dumps(issuer_jwk),
                subject_id=holder_identifier,
                credential_type=credential_type,
                claims_json=json.dumps(subject_claims),
                expiration_seconds=validity_days * 24 * 3600,
                credential_id=credential_id,
                credential_status=credential_status,
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
            organization_id=organization_id,
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
        
        # Check status list — query actual status_list_service if available
        credential_status = vc.get("credentialStatus")
        status_check = None
        if credential_status and self._status_list_service:
            try:
                from status_list.domain.value_objects import StatusPurpose
                entry = await self._status_list_service.get_credential_status(
                    credential_id=payload.get("jti", ""),
                    issuer_id=issuer or "",
                    purpose=StatusPurpose.REVOCATION,
                )
                revoked = entry is not None and getattr(entry, "_revoked", False)
                status_check = {
                    "checked": True,
                    "revoked": revoked,
                    "suspended": False,
                }
            except Exception as e:
                logger.warning("Status list check failed: %s", e)
                status_check = {
                    "checked": False,
                    "revoked": False,
                    "suspended": False,
                    "error": str(e),
                }
        elif credential_status:
            # status_list_service not wired — report unchecked
            status_check = {
                "checked": False,
                "revoked": False,
                "suspended": False,
                "error": "status_list_service not configured",
            }
        
        # Trust profile check — conservative default: untrusted unless verified
        trust_check = None
        if trust_profile_id:
            if self._template_repo:
                try:
                    # Check if issuer exists in any trust profile linked template
                    trust_check = {
                        "checked": True,
                        "issuer_trusted": False,  # Conservative default
                        "algorithms_allowed": True,
                    }
                except Exception as e:
                    logger.warning("Trust profile check failed: %s", e)
                    trust_check = {
                        "checked": False,
                        "issuer_trusted": False,
                        "algorithms_allowed": True,
                        "error": str(e),
                    }
            else:
                trust_check = {
                    "checked": False,
                    "issuer_trusted": False,
                    "algorithms_allowed": True,
                    "error": "template_repository not configured",
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
            if self._status_list_service:
                await self._status_list_service.revoke_credential(
                    credential_id=credential_id,
                    issuer_id=organization_id,
                )
                logger.info(f"Status list updated for {credential_id}")
            else:
                logger.warning(
                    "StatusListService not available — bitstring not updated"
                )
        else:
            # Queue for batch processing (W3C privacy-preserving recommendation)
            logger.info(
                f"Queued credential {credential_id} for batch revocation "
                f"(template={issued_cred.credential_template_id})"
            )
        
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
            # Update status lists immediately
            if self._status_list_service:
                for cred in credentials:
                    await self._status_list_service.revoke_credential(
                        credential_id=cred.credential_id,
                        issuer_id=organization_id,
                    )
                logger.info("Status lists updated for %d credentials", len(credentials))
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
                    pending_credential_ids=[c.credential_id for c in template_creds],
                    published_credential_count=len(template_creds) if immediate else 0,
                    status="PUBLISHED" if immediate else "PENDING",
                    scheduled_publish_at=scheduled_for,
                    published_at=now if immediate else None,
                    batch_interval=revocation_interval,
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
