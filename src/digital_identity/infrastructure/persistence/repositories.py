"""
Repository Implementations for Digital Identity

PostgreSQL repositories using SQLAlchemy async patterns.
Implements the repository port interfaces from the application layer.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from digital_identity.domain.entities import (
    TrustProfile,
    CredentialTemplate,
    PresentationPolicy,
    DeploymentProfile,
    Flow,
    FlowExecution,
    IssuedCredential,
    OrganizationCustomAnchor,
    ApplicationTemplate,
    CascadeRevocationOperation,
    RevocationProfile,
    VerificationSession,
    ComplianceProfile,
    IssuerEntity,
    TrustProfileIssuer,
    TrustFramework,
    OrganizationTrustProfile,
    Organization,
    Webhook,
    Subscription,
    ApiKey,
    IssuanceRecord,
    PolicySet,
    WalletProfile,
    DeviceRegistration,
    Applicant,
    ReviewerLock,
    VettingCheck,
    BiometricEnrollment,
    NotificationPayload,
)
from digital_identity.domain.value_objects import (
    TrustProfileType,
    CredentialFormat,
    CredentialStatus,
    CryptoAlgorithm,
    RevocationPolicy,
    TimePolicy,
    ClaimDefinition,
    ValidityRules,
    RequiredClaim,
    FreshnessRequirements,
    HolderBindingMethod,
    HolderBindingConfig,
    NetworkMode,
    KeyAccessMode,
    UXConfig,
    UpdatePolicy,
    FlowType,
    FlowStatus,
    ApprovalStrategy,
    StatusListEntryRef,
    PredicateFallbackPolicy,
    CredentialRankingStrategy,
    PrivacyPosture,
    RevocationTimingMode,
)
from digital_identity.infrastructure.persistence.models import (
    TrustProfileModel,
    CredentialTemplateModel,
    PresentationPolicyModel,
    DeploymentProfileModel,
    FlowModel,
    FlowExecutionModel,
    IssuedCredentialModel,
    OrganizationCustomAnchorModel,
    ApplicationTemplateModel,
    CascadeRevocationOperationModel,
    RevocationProfileModel,
    VerificationSessionModel,
    ComplianceProfileModel,
    IssuerEntityModel,
    TrustProfileIssuerModel,
    TrustFrameworkModel,
    OrganizationTrustProfileModel,
    OrganizationModel,
    WebhookModel,
    SubscriptionModel,
    ApiKeyModel,
    IssuanceRecordModel,
    PolicySetModel,
    WalletProfileModel,
    DeviceRegistrationModel,
    ApplicantModel,
    ReviewerLockModel,
    VettingCheckModel,
    BiometricEnrollmentModel,
    NotificationPayloadModel,
)

logger = logging.getLogger(__name__)


class TrustProfileRepository:
    """
    Repository for Trust Profile persistence.
    
    Implements TrustProfileRepositoryPort interface.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: TrustProfile) -> TrustProfile:
        """Save a Trust Profile (create or update)."""
        # Check if exists
        existing = await self._session.get(TrustProfileModel, entity.id)
        
        if existing:
            # Update
            existing.name = entity.name
            existing.display_name = entity.name  # Keep in sync
            existing.description = entity.description
            existing.organization_id = entity.organization_id or None
            existing.profile_type = entity.profile_type.value
            existing.enabled = entity.enabled
            existing.compliance_status = entity.compliance_status
            existing.auto_generated = entity.auto_generated
            existing.manually_configured = entity.manually_configured
            existing.trust_sources = entity.trust_sources
            existing.allowed_algorithms = [a.value for a in entity.allowed_algorithms]
            existing.supported_formats = [f.value for f in entity.supported_formats]
            existing.revocation_policy = self._serialize_revocation_policy(entity.revocation_policy)
            existing.time_policy = self._serialize_time_policy(entity.time_policy)
            existing.revocation_profile_id = entity.revocation_profile_id
            existing.revocation_services = entity.revocation_services
            existing.allowed_issuers = entity.allowed_issuers
            existing.denied_issuers = entity.denied_issuers
            existing.system_issuer_overrides = entity.system_issuer_overrides
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            # Create
            model = TrustProfileModel(
                id=entity.id,
                name=entity.name,
                display_name=entity.name,  # Use name as display_name for now
                description=entity.description,
                organization_id=entity.organization_id or None,
                profile_type=entity.profile_type.value,
                enabled=entity.enabled,
                compliance_status=entity.compliance_status,
                auto_generated=entity.auto_generated,
                manually_configured=entity.manually_configured,
                trust_sources=entity.trust_sources,
                allowed_algorithms=[a.value for a in entity.allowed_algorithms],
                supported_formats=[f.value for f in entity.supported_formats],
                revocation_policy=self._serialize_revocation_policy(entity.revocation_policy),
                time_policy=self._serialize_time_policy(entity.time_policy),
                revocation_profile_id=entity.revocation_profile_id,
                revocation_services=entity.revocation_services,
                allowed_issuers=entity.allowed_issuers,
                denied_issuers=entity.denied_issuers,
                system_issuer_overrides=entity.system_issuer_overrides,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> TrustProfile | None:
        """Get a Trust Profile by ID."""
        model = await self._session.get(TrustProfileModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def get_by_name(self, name: str) -> TrustProfile | None:
        """Get a Trust Profile by name."""
        stmt = select(TrustProfileModel).where(TrustProfileModel.name == name)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        profile_type: TrustProfileType | None = None,
        enabled: bool | None = None,
    ) -> list[TrustProfile]:
        """List Trust Profiles with optional filters."""
        stmt = select(TrustProfileModel)
        
        if profile_type:
            stmt = stmt.where(TrustProfileModel.profile_type == profile_type.value)
        if enabled is not None:
            stmt = stmt.where(TrustProfileModel.enabled == enabled)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Trust Profile."""
        stmt = delete(TrustProfileModel).where(TrustProfileModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Trust Profile exists."""
        model = await self._session.get(TrustProfileModel, entity_id)
        return model is not None
    
    def _to_entity(self, model: TrustProfileModel) -> TrustProfile:
        """Convert model to entity."""
        return TrustProfile(
            id=model.id,
            name=model.name,
            description=model.description,
            organization_id=getattr(model, 'organization_id', '') or '',
            profile_type=TrustProfileType(model.profile_type),
            enabled=model.enabled,
            compliance_status=getattr(model, 'compliance_status', 'SETUP_REQUIRED'),
            auto_generated=getattr(model, 'auto_generated', False),
            manually_configured=getattr(model, 'manually_configured', False),
            trust_sources=model.trust_sources,
            allowed_algorithms=[CryptoAlgorithm(a) for a in model.allowed_algorithms],
            supported_formats=[CredentialFormat(f) for f in model.supported_formats],
            revocation_policy=self._deserialize_revocation_policy(model.revocation_policy),
            time_policy=self._deserialize_time_policy(model.time_policy),
            revocation_profile_id=getattr(model, 'revocation_profile_id', None),
            revocation_services=getattr(model, 'revocation_services', {}) or {},
            allowed_issuers=model.allowed_issuers,
            denied_issuers=model.denied_issuers,
            system_issuer_overrides=getattr(model, 'system_issuer_overrides', {}) or {},
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )
    
    def _serialize_revocation_policy(self, policy: RevocationPolicy) -> dict[str, Any]:
        """Serialize revocation policy to dict."""
        return {
            "check_mode": policy.check_mode.value,
            "cache_ttl_seconds": policy.cache_ttl_seconds,
        }
    
    def _deserialize_revocation_policy(self, data: dict[str, Any]) -> RevocationPolicy:
        """Deserialize revocation policy from dict."""
        from digital_identity.domain.value_objects import RevocationCheckMode
        raw_mode = data.get("check_mode") or data.get("mode", "HARD_FAIL")
        return RevocationPolicy(
            check_mode=RevocationCheckMode(raw_mode),
            cache_ttl_seconds=int(data.get("cache_ttl_seconds", data.get("offline_grace_period_seconds", 300))),
        )
    
    def _serialize_time_policy(self, policy: TimePolicy) -> dict[str, Any]:
        """Serialize time policy to dict."""
        return {
            "clock_skew_seconds": policy.clock_skew_seconds,
            "max_credential_age_seconds": policy.max_credential_age_seconds,
            "require_freshness": policy.require_freshness,
            "freshness_window_seconds": policy.freshness_window_seconds,
        }
    
    def _deserialize_time_policy(self, data: dict[str, Any]) -> TimePolicy:
        """Deserialize time policy from dict."""
        return TimePolicy(
            clock_skew_seconds=int(data.get("clock_skew_seconds", data.get("clock_skew_tolerance_seconds", 300))),
            max_credential_age_seconds=data.get("max_credential_age_seconds"),
            require_freshness=data.get("require_freshness", False),
            freshness_window_seconds=data.get("freshness_window_seconds"),
        )


class CredentialTemplateRepository:
    """
    Repository for Credential Template persistence.
    
    Implements CredentialTemplateRepositoryPort interface.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: CredentialTemplate) -> CredentialTemplate:
        """Save a Credential Template (create or update)."""
        existing = await self._session.get(CredentialTemplateModel, entity.id)
        
        claims_data = [self._serialize_claim(c) for c in entity.claims]
        validity_data = self._serialize_validity_rules(entity.validity_rules)
        
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.credential_type = entity.credential_type
            existing.schema_uri = entity.schema_uri
            existing.claims = claims_data
            existing.validity_rules = validity_data
            existing.issuer_key_ids = entity.issuer_key_ids
            existing.issuer_key_id = entity.issuer_key_id
            existing.issuer_algorithm = entity.issuer_algorithm
            existing.key_access_mode = entity.key_access_mode
            existing.issuer_certificate_chain_pem = entity.issuer_certificate_chain_pem
            existing.issuer_did = entity.issuer_did
            existing.auto_generate_artifacts = entity.auto_generate_artifacts
            existing.compliance_profile_id = entity.compliance_profile_id or None
            existing.application_template_id = entity.application_template_id
            existing.trust_profile_id = entity.trust_profile_id
            existing.revocation_profile_id = entity.revocation_profile_id
            existing.organization_id = getattr(entity, 'organization_id', None)
            existing.status = entity.status
            existing.format = entity.format.value
            existing.namespace = entity.namespace
            existing.privacy_posture = entity.privacy_posture.to_dict()
            existing.vct = entity.vct
            existing.display = entity.display
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = CredentialTemplateModel(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                credential_type=entity.credential_type,
                schema_uri=entity.schema_uri,
                claims=claims_data,
                validity_rules=validity_data,
                issuer_key_ids=entity.issuer_key_ids,
                issuer_key_id=entity.issuer_key_id,
                issuer_algorithm=entity.issuer_algorithm,
                key_access_mode=entity.key_access_mode,
                issuer_certificate_chain_pem=entity.issuer_certificate_chain_pem,
                issuer_did=entity.issuer_did,
                auto_generate_artifacts=entity.auto_generate_artifacts,
                compliance_profile_id=entity.compliance_profile_id or None,
                application_template_id=entity.application_template_id,
                trust_profile_id=entity.trust_profile_id,
                revocation_profile_id=entity.revocation_profile_id,
                organization_id=getattr(entity, 'organization_id', None),
                status=entity.status,
                format=entity.format.value,
                namespace=entity.namespace,
                privacy_posture=entity.privacy_posture.to_dict(),
                vct=entity.vct,
                display=entity.display,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> CredentialTemplate | None:
        """Get a Credential Template by ID."""
        model = await self._session.get(CredentialTemplateModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def get_by_type(self, credential_type: str) -> CredentialTemplate | None:
        """Get a Credential Template by credential type."""
        stmt = select(CredentialTemplateModel).where(
            CredentialTemplateModel.credential_type == credential_type
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        format: str | None = None,
    ) -> list[CredentialTemplate]:
        """List Credential Templates with optional filters."""
        stmt = select(CredentialTemplateModel)
        
        if format:
            stmt = stmt.where(CredentialTemplateModel.format == format)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Credential Template."""
        stmt = delete(CredentialTemplateModel).where(CredentialTemplateModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Credential Template exists."""
        model = await self._session.get(CredentialTemplateModel, entity_id)
        return model is not None
    
    def _to_entity(self, model: CredentialTemplateModel) -> CredentialTemplate:
        """Convert model to entity."""
        return CredentialTemplate(
            id=model.id,
            name=model.name,
            description=model.description,
            credential_type=model.credential_type,
            schema_uri=model.schema_uri,
            vct=getattr(model, 'vct', None),
            claims=[self._deserialize_claim(c) for c in model.claims],
            compliance_profile_id=model.compliance_profile_id or "",
            application_template_id=model.application_template_id,
            trust_profile_id=model.trust_profile_id,
            revocation_profile_id=model.revocation_profile_id,
            validity_rules=self._deserialize_validity_rules(model.validity_rules),
            issuer_key_id=getattr(model, 'issuer_key_id', None),
            issuer_algorithm=getattr(model, 'issuer_algorithm', None),
            key_access_mode=getattr(model, 'key_access_mode', 'key_vault'),
            issuer_certificate_chain_pem=model.issuer_certificate_chain_pem,
            issuer_did=model.issuer_did,
            auto_generate_artifacts=getattr(model, 'auto_generate_artifacts', False),
            issuer_key_ids=model.issuer_key_ids,
            format=CredentialFormat(model.format),
            namespace=model.namespace,
            privacy_posture=(
                PrivacyPosture.from_dict(model.privacy_posture)
                if isinstance(getattr(model, 'privacy_posture', None), dict)
                else PrivacyPosture.from_legacy(getattr(model, 'privacy_posture', 'selective_disclosure'))
            ),
            organization_id=getattr(model, 'organization_id', None),
            status=getattr(model, 'status', 'DRAFT'),
            display=model.display,
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )
    
    def _serialize_claim(self, claim: ClaimDefinition) -> dict[str, Any]:
        """Serialize claim to dict."""
        return {
            "name": claim.name,
            "display_name": claim.display_name,
            "type": claim.claim_type,
            "required": claim.required,
            "selectively_disclosable": claim.selectively_disclosable,
            "derived_from": claim.derived_from,
            "predicate_type": claim.predicate_type,
            "predicate_value": claim.predicate_value,
            "validation_regex": claim.validation_regex,
            "description": claim.description,
        }
    
    def _deserialize_claim(self, data: dict[str, Any]) -> ClaimDefinition:
        """Deserialize claim from dict."""
        return ClaimDefinition(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            claim_type=data.get("type", data.get("data_type", "string")),
            required=data.get("required", True),
            selectively_disclosable=data.get("selectively_disclosable", False),
            derived_from=data.get("derived_from"),
            predicate_type=data.get("predicate_type"),
            predicate_value=data.get("predicate_value"),
            validation_regex=data.get("validation_regex"),
            description=data.get("description"),
        )
    
    def _serialize_validity_rules(self, rules: ValidityRules) -> dict[str, Any]:
        """Serialize validity rules to dict."""
        return {
            "ttl_seconds": rules.ttl_seconds,
            "renewable": rules.renewable,
            "reissue_within_seconds": rules.reissue_within_seconds,
            "not_before_offset_seconds": rules.not_before_offset_seconds,
        }
    
    def _deserialize_validity_rules(self, data: dict[str, Any]) -> ValidityRules:
        """Deserialize validity rules from dict."""
        return ValidityRules(
            ttl_seconds=data.get("ttl_seconds", data.get("default_ttl_seconds", 31536000)),
            renewable=data.get("renewable", data.get("allow_reissue", False)),
            reissue_within_seconds=data.get("reissue_within_seconds"),
            not_before_offset_seconds=data.get("not_before_offset_seconds", 0),
        )


class PresentationPolicyRepository:
    """
    Repository for Presentation Policy persistence.
    
    Implements PresentationPolicyRepositoryPort interface.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: PresentationPolicy) -> PresentationPolicy:
        """Save a Presentation Policy (create or update)."""
        existing = await self._session.get(PresentationPolicyModel, entity.id)
        
        claims_data = [self._serialize_required_claim(c) for c in entity.required_claims]
        freshness_data = self._serialize_freshness(entity.freshness_requirements)
        
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.purpose = entity.purpose
            existing.organization_id = entity.organization_id
            existing.accepted_credential_types = entity.accepted_credential_types
            existing.required_claims = claims_data
            existing.holder_binding = entity.holder_binding.to_dict()
            existing.trust_profile_id = entity.trust_profile_id
            existing.allowed_issuers = entity.allowed_issuers
            existing.issuer_constraints = entity.issuer_constraints
            existing.freshness_requirements = freshness_data
            existing.prefer_predicates = entity.prefer_predicates
            existing.single_presentation = entity.single_presentation
            existing.derived_attribute_preferences = entity.derived_attribute_preferences
            existing.fallback_policy = entity.fallback_policy.value
            existing.supported_circuits = entity.supported_circuits
            existing.credential_ranking_strategy = entity.credential_ranking_strategy.value
            existing.credential_ranking_weights = entity.credential_ranking_weights
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = PresentationPolicyModel(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                purpose=entity.purpose,
                organization_id=entity.organization_id,
                accepted_credential_types=entity.accepted_credential_types,
                required_claims=claims_data,
                holder_binding=entity.holder_binding.to_dict(),
                trust_profile_id=entity.trust_profile_id,
                allowed_issuers=entity.allowed_issuers,
                issuer_constraints=entity.issuer_constraints,
                freshness_requirements=freshness_data,
                prefer_predicates=entity.prefer_predicates,
                single_presentation=entity.single_presentation,
                derived_attribute_preferences=entity.derived_attribute_preferences,
                fallback_policy=entity.fallback_policy.value,
                supported_circuits=entity.supported_circuits,
                credential_ranking_strategy=entity.credential_ranking_strategy.value,
                credential_ranking_weights=entity.credential_ranking_weights,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> PresentationPolicy | None:
        """Get a Presentation Policy by ID."""
        model = await self._session.get(PresentationPolicyModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def get_by_name(self, name: str) -> PresentationPolicy | None:
        """Get a Presentation Policy by name."""
        stmt = select(PresentationPolicyModel).where(PresentationPolicyModel.name == name)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        trust_profile_id: str | None = None,
    ) -> list[PresentationPolicy]:
        """List Presentation Policies with optional filters."""
        stmt = select(PresentationPolicyModel)
        
        if trust_profile_id:
            stmt = stmt.where(PresentationPolicyModel.trust_profile_id == trust_profile_id)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Presentation Policy."""
        stmt = delete(PresentationPolicyModel).where(PresentationPolicyModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Presentation Policy exists."""
        model = await self._session.get(PresentationPolicyModel, entity_id)
        return model is not None
    
    def _to_entity(self, model: PresentationPolicyModel) -> PresentationPolicy:
        """Convert model to entity."""
        return PresentationPolicy(
            id=model.id,
            name=model.name,
            description=model.description,
            purpose=model.purpose,
            organization_id=getattr(model, 'organization_id', '') or '',
            accepted_credential_types=model.accepted_credential_types,
            required_claims=[self._deserialize_required_claim(c) for c in model.required_claims],
            holder_binding=(
                HolderBindingConfig.from_dict(model.holder_binding)
                if isinstance(model.holder_binding, dict)
                else HolderBindingConfig.from_legacy(model.holder_binding)
            ),
            trust_profile_id=model.trust_profile_id,
            allowed_issuers=getattr(model, 'allowed_issuers', []) or [],
            issuer_constraints=getattr(model, 'issuer_constraints', {}) or {},
            freshness_requirements=self._deserialize_freshness(model.freshness_requirements),
            prefer_predicates=model.prefer_predicates,
            single_presentation=model.single_presentation,
            derived_attribute_preferences=getattr(model, 'derived_attribute_preferences', {}) or {},
            fallback_policy=PredicateFallbackPolicy(getattr(model, 'fallback_policy', 'ACCEPT_RAW')),
            supported_circuits=getattr(model, 'supported_circuits', []) or [],
            credential_ranking_strategy=CredentialRankingStrategy(getattr(model, 'credential_ranking_strategy', 'FRESHEST_FIRST')),
            credential_ranking_weights=getattr(model, 'credential_ranking_weights', {}) or {},
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )
    
    def _serialize_required_claim(self, claim: RequiredClaim) -> dict[str, Any]:
        """Serialize required claim to dict."""
        return {
            "claim_name": claim.claim_name,
            "credential_type": claim.credential_type,
            "accept_predicate": claim.accept_predicate,
            "value_constraint": claim.value_constraint,
        }
    
    def _deserialize_required_claim(self, data: dict[str, Any]) -> RequiredClaim:
        """Deserialize required claim from dict."""
        return RequiredClaim(
            claim_name=data["claim_name"],
            credential_type=data["credential_type"],
            accept_predicate=data.get("accept_predicate", True),
            value_constraint=data.get("value_constraint", data.get("required_value")),
        )
    
    def _serialize_freshness(self, req: FreshnessRequirements) -> dict[str, Any]:
        """Serialize freshness requirements to dict."""
        return {
            "max_age_seconds": req.max_age_seconds,
            "require_not_revoked": req.require_not_revoked,
            "revocation_grace_seconds": req.revocation_grace_seconds,
        }
    
    def _deserialize_freshness(self, data: dict[str, Any]) -> FreshnessRequirements:
        """Deserialize freshness requirements from dict."""
        return FreshnessRequirements(
            max_age_seconds=data.get("max_age_seconds", data.get("max_credential_age_seconds")),
            require_not_revoked=data.get("require_not_revoked", data.get("require_live_revocation_check", True)),
            revocation_grace_seconds=data.get("revocation_grace_seconds"),
        )


class DeploymentProfileRepository:
    """
    Repository for Deployment Profile persistence.
    
    Implements DeploymentProfileRepositoryPort interface.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: DeploymentProfile) -> DeploymentProfile:
        """Save a Deployment Profile (create or update)."""
        existing = await self._session.get(DeploymentProfileModel, entity.id)
        
        ux_data = self._serialize_ux_config(entity.ux_config)
        update_data = self._serialize_update_policy(entity.update_policy)
        
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.site_id = entity.site_id
            existing.enabled_flow_ids = entity.enabled_flow_ids
            existing.default_presentation_policy_id = entity.default_presentation_policy_id
            existing.network_mode = entity.network_mode.value
            existing.key_access_mode = entity.key_access_mode.value
            existing.ux_config = ux_data
            existing.update_policy = update_data
            existing.offline_cache_ttl_hours = entity.offline_cache_ttl_hours
            existing.biometric_required = entity.operator_biometric_authentication_required
            existing.audit_all_events = entity.audit_all_events
            existing.organization_id = getattr(entity, 'organization_id', None)
            existing.lanes = self._serialize_lanes(entity.lanes)
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = DeploymentProfileModel(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                site_id=entity.site_id,
                enabled_flow_ids=entity.enabled_flow_ids,
                default_presentation_policy_id=entity.default_presentation_policy_id,
                network_mode=entity.network_mode.value,
                key_access_mode=entity.key_access_mode.value,
                ux_config=ux_data,
                update_policy=update_data,
                offline_cache_ttl_hours=entity.offline_cache_ttl_hours,
                biometric_required=entity.operator_biometric_authentication_required,
                audit_all_events=entity.audit_all_events,
                organization_id=getattr(entity, 'organization_id', None),
                lanes=self._serialize_lanes(entity.lanes),
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> DeploymentProfile | None:
        """Get a Deployment Profile by ID."""
        model = await self._session.get(DeploymentProfileModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def get_by_site(self, site_id: str) -> DeploymentProfile | None:
        """Get a Deployment Profile by site ID."""
        stmt = select(DeploymentProfileModel).where(DeploymentProfileModel.site_id == site_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        network_mode: str | None = None,
    ) -> list[DeploymentProfile]:
        """List Deployment Profiles with optional filters."""
        stmt = select(DeploymentProfileModel)
        
        if network_mode:
            stmt = stmt.where(DeploymentProfileModel.network_mode == network_mode)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Deployment Profile."""
        stmt = delete(DeploymentProfileModel).where(DeploymentProfileModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Deployment Profile exists."""
        model = await self._session.get(DeploymentProfileModel, entity_id)
        return model is not None
    
    def _to_entity(self, model: DeploymentProfileModel) -> DeploymentProfile:
        """Convert model to entity."""
        from digital_identity.domain.entities import Lane
        return DeploymentProfile(
            id=model.id,
            name=model.name,
            description=model.description,
            site_id=model.site_id,
            enabled_flow_ids=model.enabled_flow_ids,
            default_presentation_policy_id=model.default_presentation_policy_id,
            network_mode=NetworkMode(model.network_mode),
            key_access_mode=KeyAccessMode(model.key_access_mode),
            ux_config=self._deserialize_ux_config(model.ux_config),
            update_policy=self._deserialize_update_policy(model.update_policy),
            offline_cache_ttl_hours=model.offline_cache_ttl_hours,
            operator_biometric_authentication_required=model.biometric_required,
            audit_all_events=model.audit_all_events,
            organization_id=getattr(model, 'organization_id', None),
            lanes=self._deserialize_lanes(getattr(model, 'lanes', []) or []),
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )
    
    def _serialize_ux_config(self, config: UXConfig) -> dict[str, Any]:
        """Serialize UX config to dict."""
        return {
            "language": config.language,
            "theme": config.theme,
            "operator_mode": config.operator_mode,
            "accessibility_mode": config.accessibility_mode,
            "signage_text": config.signage_text,
        }
    
    def _deserialize_ux_config(self, data: dict[str, Any]) -> UXConfig:
        """Deserialize UX config from dict."""
        return UXConfig(
            language=data.get("language", "en-US"),
            theme=data.get("theme", "light"),
            operator_mode=data.get("operator_mode", data.get("show_operator_mode", False)),
            accessibility_mode=data.get("accessibility_mode", data.get("accessibility_enabled", False)),
            signage_text=data.get("signage_text"),
        )
    
    def _serialize_update_policy(self, policy: UpdatePolicy) -> dict[str, Any]:
        """Serialize update policy to dict."""
        return {
            "auto_update": policy.auto_update,
            "channel": policy.channel,
            "pinned_version": policy.pinned_version,
        }
    
    def _deserialize_update_policy(self, data: dict[str, Any]) -> UpdatePolicy:
        """Deserialize update policy from dict."""
        return UpdatePolicy(
            auto_update=data.get("auto_update", True),
            channel=data.get("channel", data.get("update_channel", "stable")),
            pinned_version=data.get("pinned_version", data.get("version_pinned")),
        )
    
    def _serialize_lanes(self, lanes: list) -> list[dict[str, Any]]:
        """Serialize Lane entities to list of dicts."""
        return [
            {
                "id": lane.id,
                "name": lane.name,
                "deployment_profile_id": lane.deployment_profile_id,
                "default_policy_id": lane.default_policy_id,
                "device_ids": lane.device_ids,
                "metadata": lane.metadata,
                "created_at": lane.created_at.isoformat() if lane.created_at else None,
                "updated_at": lane.updated_at.isoformat() if lane.updated_at else None,
                "version": lane.version,
            }
            for lane in lanes
        ]
    
    def _deserialize_lanes(self, data: list[dict[str, Any]]) -> list:
        """Deserialize Lane entities from list of dicts."""
        from digital_identity.domain.entities import Lane
        return [
            Lane(
                id=d.get("id", ""),
                name=d.get("name", ""),
                deployment_profile_id=d.get("deployment_profile_id", ""),
                default_policy_id=d.get("default_policy_id"),
                device_ids=d.get("device_ids", []),
                metadata=d.get("metadata", {}),
                created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else datetime.now(timezone.utc),
                updated_at=datetime.fromisoformat(d["updated_at"]) if d.get("updated_at") else datetime.now(timezone.utc),
                version=d.get("version", 1),
            )
            for d in data
        ]


class FlowRepository:
    """
    Repository for Flow persistence.
    
    Implements FlowRepositoryPort interface.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: Flow) -> Flow:
        """Save a Flow (create or update)."""
        existing = await self._session.get(FlowModel, entity.id)
        
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.flow_type = entity.flow_type.value
            existing.trust_profile_id = entity.trust_profile_id
            existing.credential_template_id = entity.credential_template_id
            existing.application_template_id = getattr(entity, 'application_template_id', None)
            existing.presentation_policy_id = entity.presentation_policy_id
            existing.deployment_profile_ids = entity.deployment_profile_ids
            existing.approval_strategy = entity.approval_strategy.value
            existing.enabled = entity.enabled
            existing.status = entity.status
            existing.organization_id = entity.organization_id
            existing.hooks = entity.hooks
            existing.trigger = entity.trigger
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = FlowModel(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                flow_type=entity.flow_type.value,
                trust_profile_id=entity.trust_profile_id,
                credential_template_id=entity.credential_template_id,
                application_template_id=getattr(entity, 'application_template_id', None),
                presentation_policy_id=entity.presentation_policy_id,
                deployment_profile_ids=entity.deployment_profile_ids,
                approval_strategy=entity.approval_strategy.value,
                enabled=entity.enabled,
                status=entity.status,
                organization_id=entity.organization_id,
                hooks=entity.hooks,
                trigger=entity.trigger,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> Flow | None:
        """Get a Flow by ID."""
        model = await self._session.get(FlowModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def get_by_name(self, name: str) -> Flow | None:
        """Get a Flow by name."""
        stmt = select(FlowModel).where(FlowModel.name == name)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        flow_type: FlowType | None = None,
        enabled: bool | None = None,
    ) -> list[Flow]:
        """List Flows with optional filters."""
        stmt = select(FlowModel)
        
        if flow_type:
            stmt = stmt.where(FlowModel.flow_type == flow_type.value)
        if enabled is not None:
            stmt = stmt.where(FlowModel.enabled == enabled)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Flow."""
        stmt = delete(FlowModel).where(FlowModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Flow exists."""
        model = await self._session.get(FlowModel, entity_id)
        return model is not None
    
    def _to_entity(self, model: FlowModel) -> Flow:
        """Convert model to entity."""
        return Flow(
            id=model.id,
            name=model.name,
            description=model.description,
            flow_type=FlowType(model.flow_type),
            trust_profile_id=model.trust_profile_id,
            credential_template_id=model.credential_template_id,
            application_template_id=getattr(model, 'application_template_id', None),
            presentation_policy_id=model.presentation_policy_id,
            deployment_profile_ids=model.deployment_profile_ids,
            approval_strategy=ApprovalStrategy(model.approval_strategy),
            enabled=model.enabled,
            status=getattr(model, 'status', 'DRAFT'),
            organization_id=getattr(model, 'organization_id', ''),
            hooks=model.hooks,
            trigger=getattr(model, 'trigger', None),
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class FlowExecutionRepository:
    """
    Repository for Flow Execution persistence.
    
    Implements FlowExecutionRepositoryPort interface.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: FlowExecution) -> FlowExecution:
        """Save a Flow Execution (create or update)."""
        existing = await self._session.get(FlowExecutionModel, entity.id)
        
        if existing:
            existing.flow_id = entity.flow_id
            existing.flow_type = entity.flow_type
            existing.organization_id = entity.organization_id
            existing.status = entity.status.value
            existing.current_step = entity.current_step
            existing.current_step_index = entity.current_step_index
            existing.step_results = entity.step_results
            existing.context_data = entity.context_data
            existing.issued_credential_id = entity.issued_credential_id
            existing.started_at = entity.started_at
            existing.completed_at = entity.completed_at
            existing.expires_at = entity.expires_at
            existing.error_code = entity.error_code
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = FlowExecutionModel(
                id=entity.id,
                flow_id=entity.flow_id,
                flow_type=entity.flow_type,
                organization_id=entity.organization_id,
                status=entity.status.value,
                current_step=entity.current_step,
                current_step_index=entity.current_step_index,
                step_results=entity.step_results,
                context_data=entity.context_data,
                issued_credential_id=entity.issued_credential_id,
                started_at=entity.started_at,
                completed_at=entity.completed_at,
                expires_at=entity.expires_at,
                error_code=entity.error_code,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> FlowExecution | None:
        """Get a Flow Execution by ID."""
        model = await self._session.get(FlowExecutionModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def list(
        self,
        flow_id: str | None = None,
        status: FlowStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[FlowExecution]:
        """List Flow Executions with optional filters."""
        stmt = select(FlowExecutionModel)
        
        if flow_id:
            stmt = stmt.where(FlowExecutionModel.flow_id == flow_id)
        if status:
            stmt = stmt.where(FlowExecutionModel.status == status.value)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Flow Execution."""
        stmt = delete(FlowExecutionModel).where(FlowExecutionModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def get_pending_approvals(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[FlowExecution]:
        """Get executions awaiting approval."""
        stmt = select(FlowExecutionModel).where(
            FlowExecutionModel.status == FlowStatus.AWAITING_APPROVAL.value
        ).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    def _to_entity(self, model: FlowExecutionModel) -> FlowExecution:
        """Convert model to entity."""
        return FlowExecution(
            id=model.id,
            flow_id=model.flow_id,
            flow_type=getattr(model, 'flow_type', ''),
            organization_id=getattr(model, 'organization_id', ''),
            status=FlowStatus(model.status),
            current_step=model.current_step,
            current_step_index=model.current_step_index,
            step_results=model.step_results,
            context_data=model.context_data,
            issued_credential_id=model.issued_credential_id,
            started_at=model.started_at,
            completed_at=model.completed_at,
            expires_at=getattr(model, 'expires_at', None),
            error_code=getattr(model, 'error_code', None),
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class CustomAnchorRepository:
    """
    Repository for Organization Custom Anchor persistence.
    
    Implements CustomAnchorRepositoryPort interface.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: OrganizationCustomAnchor) -> OrganizationCustomAnchor:
        """Save a custom anchor (create or update)."""
        existing = await self._session.get(OrganizationCustomAnchorModel, entity.id)
        
        if existing:
            # Update
            existing.profile_id = entity.profile_id
            existing.anchor_type = entity.anchor_type
            existing.subject = entity.subject
            existing.issuer = entity.issuer
            existing.certificate_pem = entity.certificate_pem
            existing.certificate_der = entity.certificate_der
            existing.not_before = entity.not_before
            existing.not_after = entity.not_after
            existing.purpose = entity.purpose
            existing.uploaded_by = entity.uploaded_by
            existing.uploaded_at = entity.uploaded_at
        else:
            # Create
            model = OrganizationCustomAnchorModel(
                id=entity.id,
                profile_id=entity.profile_id,
                anchor_type=entity.anchor_type,
                subject=entity.subject,
                issuer=entity.issuer,
                certificate_pem=entity.certificate_pem,
                certificate_der=entity.certificate_der,
                not_before=entity.not_before,
                not_after=entity.not_after,
                purpose=entity.purpose,
                uploaded_by=entity.uploaded_by,
                uploaded_at=entity.uploaded_at,
                created_at=entity.created_at,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> OrganizationCustomAnchor | None:
        """Get a custom anchor by ID."""
        model = await self._session.get(OrganizationCustomAnchorModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def list_by_profile(self, profile_id: str) -> list[OrganizationCustomAnchor]:
        """List all custom anchors for a trust profile."""
        stmt = select(OrganizationCustomAnchorModel).where(
            OrganizationCustomAnchorModel.profile_id == profile_id
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def list_by_organization(self, organization_id: str) -> list[OrganizationCustomAnchor]:
        """List all custom anchors for an organization."""
        # Join with organization_trust_profiles to filter by organization
        from digital_identity.infrastructure.persistence.models import OrganizationTrustProfileModel
        
        stmt = (
            select(OrganizationCustomAnchorModel)
            .join(OrganizationTrustProfileModel, 
                  OrganizationCustomAnchorModel.profile_id == OrganizationTrustProfileModel.id)
            .where(OrganizationTrustProfileModel.organization_id == organization_id)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a custom anchor."""
        stmt = delete(OrganizationCustomAnchorModel).where(
            OrganizationCustomAnchorModel.id == entity_id
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a custom anchor exists."""
        model = await self._session.get(OrganizationCustomAnchorModel, entity_id)
        return model is not None
    
    def _to_entity(self, model: OrganizationCustomAnchorModel) -> OrganizationCustomAnchor:
        """Convert model to entity."""
        return OrganizationCustomAnchor(
            id=model.id,
            profile_id=model.profile_id,
            anchor_type=model.anchor_type,
            subject=model.subject,
            issuer=model.issuer,
            certificate_pem=model.certificate_pem,
            certificate_der=model.certificate_der,
            not_before=model.not_before,
            not_after=model.not_after,
            purpose=model.purpose,
            uploaded_by=model.uploaded_by,
            uploaded_at=model.uploaded_at,
            created_at=model.created_at,
        )


class AuditEventRepository:
    """
    Repository for Audit Event persistence.
    
    Implements AuditEventRepositoryPort interface.
    Audit events are immutable (create-only).
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: Any) -> Any:  # AuditEvent type
        """Save an audit event (create only)."""
        from digital_identity.infrastructure.persistence.models import AuditEventModel
        
        # Create model
        model = AuditEventModel(
            id=entity.id,
            event_type=entity.event_type,
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            actor_id=entity.actor_id,
            action=entity.action,
            payload=entity.payload,
            correlation_id=entity.correlation_id,
            occurred_at=entity.occurred_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            version=entity.version,
        )
        
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        
        return self._to_entity(model)
    
    async def get(self, entity_id: str) -> Any | None:  # AuditEvent type
        """Get an audit event by ID."""
        from digital_identity.infrastructure.persistence.models import AuditEventModel
        
        model = await self._session.get(AuditEventModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def find_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Any]:  # list[AuditEvent]
        """Find all audit events for a specific entity."""
        from digital_identity.infrastructure.persistence.models import AuditEventModel
        
        stmt = (
            select(AuditEventModel)
            .where(
                AuditEventModel.entity_type == entity_type,
                AuditEventModel.entity_id == entity_id,
            )
            .order_by(AuditEventModel.occurred_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]
    
    async def find_by_correlation_id(
        self,
        correlation_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Any]:  # list[AuditEvent]
        """Find all audit events with a specific correlation ID."""
        from digital_identity.infrastructure.persistence.models import AuditEventModel
        
        stmt = (
            select(AuditEventModel)
            .where(AuditEventModel.correlation_id == correlation_id)
            .order_by(AuditEventModel.occurred_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]
    
    async def list_by_time_range(
        self,
        start_time: Any,  # datetime
        end_time: Any,  # datetime
        event_type: str | None = None,
        entity_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Any]:  # list[AuditEvent]
        """List audit events within a time range with optional filters."""
        from digital_identity.infrastructure.persistence.models import AuditEventModel
        
        stmt = select(AuditEventModel).where(
            AuditEventModel.occurred_at >= start_time,
            AuditEventModel.occurred_at <= end_time,
        )
        
        if event_type:
            stmt = stmt.where(AuditEventModel.event_type == event_type)
        
        if entity_type:
            stmt = stmt.where(AuditEventModel.entity_type == entity_type)
        
        stmt = stmt.order_by(AuditEventModel.occurred_at.desc()).offset(skip).limit(limit)
        
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]
    
    def _to_entity(self, model: Any) -> Any:  # AuditEventModel -> AuditEvent
        """Convert model to entity."""
        from digital_identity.domain.entities import AuditEvent
        
        return AuditEvent(
            id=model.id,
            event_type=model.event_type,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            actor_id=model.actor_id,
            action=model.action,
            payload=model.payload,
            correlation_id=model.correlation_id,
            occurred_at=model.occurred_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class IssuedCredentialRepository:
    """
    Repository for Issued Credential persistence.
    
    Implements IssuedCredentialRepositoryPort interface.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: IssuedCredential) -> IssuedCredential:
        """Save an Issued Credential (create or update)."""
        existing = await self._session.get(IssuedCredentialModel, entity.id)
        
        if existing:
            # Update
            existing.credential_id = entity.credential_id
            existing.credential_type = entity.credential_type
            existing.credential_format = entity.credential_format.value
            existing.flow_execution_id = entity.flow_execution_id
            existing.credential_template_id = entity.credential_template_id
            existing.application_id = entity.application_id
            existing.revocation_profile_id = entity.revocation_profile_id
            existing.organization_id = entity.organization_id
            existing.subject_id = entity.subject_id
            existing.subject_claims_hash = entity.subject_claims_hash
            existing.issued_at = entity.issued_at
            existing.valid_from = entity.valid_from
            existing.valid_until = entity.valid_until
            existing.status = entity.status.value
            existing.status_list_entries = [asdict(e) for e in entity.status_list_entries]
            existing.credential_hash = entity.credential_hash
            existing.revoked_at = entity.revoked_at
            existing.revocation_reason = entity.revocation_reason
            existing.revoked_by = entity.revoked_by
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            # Create
            model = IssuedCredentialModel(
                id=entity.id,
                credential_id=entity.credential_id,
                credential_type=entity.credential_type,
                credential_format=entity.credential_format.value,
                flow_execution_id=entity.flow_execution_id,
                credential_template_id=entity.credential_template_id,
                application_id=entity.application_id,
                revocation_profile_id=entity.revocation_profile_id,
                organization_id=entity.organization_id,
                subject_id=entity.subject_id,
                subject_claims_hash=entity.subject_claims_hash,
                issued_at=entity.issued_at,
                valid_from=entity.valid_from,
                valid_until=entity.valid_until,
                status=entity.status.value,
                status_list_entries=[asdict(e) for e in entity.status_list_entries],
                credential_hash=entity.credential_hash,
                revoked_at=entity.revoked_at,
                revocation_reason=entity.revocation_reason,
                revoked_by=entity.revoked_by,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> IssuedCredential | None:
        """Get an Issued Credential by ID."""
        model = await self._session.get(IssuedCredentialModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def get_by_credential_id(self, credential_id: str) -> IssuedCredential | None:
        """Get an Issued Credential by its credential_id."""
        stmt = select(IssuedCredentialModel).where(
            IssuedCredentialModel.credential_id == credential_id
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None
    
    async def list_by_flow_execution(self, flow_execution_id: str) -> list[IssuedCredential]:
        """List credentials issued by a specific flow execution."""
        stmt = select(IssuedCredentialModel).where(
            IssuedCredentialModel.flow_execution_id == flow_execution_id
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def list_by_subject(
        self,
        subject_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[IssuedCredential]:
        """List credentials for a specific subject/holder."""
        stmt = select(IssuedCredentialModel).where(
            IssuedCredentialModel.subject_id == subject_id
        ).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def list_by_template(
        self,
        credential_template_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[IssuedCredential]:
        """List credentials issued from a specific template."""
        stmt = select(IssuedCredentialModel).where(
            IssuedCredentialModel.credential_template_id == credential_template_id
        ).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete an Issued Credential record."""
        stmt = delete(IssuedCredentialModel).where(IssuedCredentialModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    def _to_entity(self, model: IssuedCredentialModel) -> IssuedCredential:
        """Convert model to entity."""
        return IssuedCredential(
            id=model.id,
            credential_id=model.credential_id,
            credential_type=model.credential_type,
            credential_format=CredentialFormat(model.credential_format),
            flow_execution_id=model.flow_execution_id,
            credential_template_id=model.credential_template_id,
            application_id=model.application_id,
            revocation_profile_id=getattr(model, 'revocation_profile_id', None),
            organization_id=getattr(model, 'organization_id', None),
            subject_id=model.subject_id,
            subject_claims_hash=model.subject_claims_hash,
            issued_at=model.issued_at,
            valid_from=model.valid_from,
            valid_until=model.valid_until,
            status=CredentialStatus(model.status),
            status_list_entries=[
                StatusListEntryRef(**entry) for entry in model.status_list_entries
            ],
            credential_hash=model.credential_hash,
            revoked_at=model.revoked_at,
            revocation_reason=model.revocation_reason,
            revoked_by=model.revoked_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class RevocationBatchRepository:
    """
    Repository for Revocation Batch persistence.
    
    Tracks batch revocation operations for privacy-preserving credential lifecycle management.
    """
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity) -> Any:
        """Save a Revocation Batch (create or update)."""
        from ..persistence.models import RevocationBatchModel
        from ...domain.entities import RevocationBatch
        
        existing = await self._session.get(RevocationBatchModel, entity.id)
        
        if existing:
            existing.organization_id = entity.organization_id
            existing.credential_template_id = entity.credential_template_id
            existing.credential_format = entity.credential_format
            existing.batch_interval = entity.batch_interval
            existing.pending_credential_ids = entity.pending_credential_ids
            existing.published_credential_count = entity.published_credential_count
            existing.status_list_uri = entity.status_list_uri
            existing.status = entity.status
            existing.scheduled_publish_at = entity.scheduled_publish_at
            existing.published_at = entity.published_at
            existing.error_message = entity.error_message
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = RevocationBatchModel(
                id=entity.id,
                organization_id=entity.organization_id,
                credential_template_id=entity.credential_template_id,
                credential_format=entity.credential_format,
                batch_interval=entity.batch_interval,
                pending_credential_ids=entity.pending_credential_ids,
                published_credential_count=entity.published_credential_count,
                status_list_uri=entity.status_list_uri,
                status=entity.status,
                scheduled_publish_at=entity.scheduled_publish_at,
                published_at=entity.published_at,
                error_message=entity.error_message,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, batch_id: str) -> Any | None:
        """Get a Revocation Batch by ID."""
        from ..persistence.models import RevocationBatchModel
        
        model = await self._session.get(RevocationBatchModel, batch_id)
        return self._to_entity(model) if model else None
    
    async def list_by_organization(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Any]:
        """List batches for a specific organization."""
        from ..persistence.models import RevocationBatchModel
        
        stmt = select(RevocationBatchModel).where(
            RevocationBatchModel.organization_id == organization_id
        ).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def list_pending(
        self,
        scheduled_before: datetime | None = None,
    ) -> list[Any]:
        """List pending batches (queued status) scheduled before the given time."""
        from ..persistence.models import RevocationBatchModel
        
        stmt = select(RevocationBatchModel).where(
            RevocationBatchModel.status == "PENDING"
        )
        if scheduled_before:
            stmt = stmt.where(RevocationBatchModel.scheduled_publish_at <= scheduled_before)
        
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def update_status(
        self,
        batch_id: str,
        status: str,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update batch status."""
        from ..persistence.models import RevocationBatchModel
        
        batch = await self._session.get(RevocationBatchModel, batch_id)
        if not batch:
            return False
        
        batch.status = status
        if completed_at:
            batch.completed_at = completed_at
        if error_message:
            batch.error_message = error_message
        batch.updated_at = datetime.now(timezone.utc)
        
        await self._session.commit()
        return True
    
    async def delete(self, batch_id: str) -> bool:
        """Delete a Revocation Batch."""
        from ..persistence.models import RevocationBatchModel
        
        stmt = delete(RevocationBatchModel).where(RevocationBatchModel.id == batch_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    def _to_entity(self, model: Any) -> Any:
        """Convert model to entity."""
        from ...domain.entities import RevocationBatch
        
        return RevocationBatch(
            id=model.id,
            organization_id=model.organization_id,
            credential_template_id=model.credential_template_id,
            credential_format=getattr(model, 'credential_format', ''),
            batch_interval=getattr(model, 'batch_interval', '6h'),
            pending_credential_ids=getattr(model, 'pending_credential_ids', []),
            published_credential_count=getattr(model, 'published_credential_count', 0),
            status_list_uri=getattr(model, 'status_list_uri', None),
            status=model.status,
            scheduled_publish_at=getattr(model, 'scheduled_publish_at', None),
            published_at=getattr(model, 'published_at', None),
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class ApplicationTemplateRepository:
    """Repository for Application Template persistence."""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: ApplicationTemplate) -> ApplicationTemplate:
        """Save an Application Template (create or update)."""
        existing = await self._session.get(ApplicationTemplateModel, entity.id)
        
        evidence_data = [
            {
                "evidence_type": r.evidence_type.value if hasattr(r.evidence_type, 'value') else str(r.evidence_type),
                "required": r.required,
                "provider_config": r.provider_config,
                "description": r.description,
                "auto_validate": r.auto_validate,
            }
            for r in entity.evidence_requirements
        ]
        rules_data = [
            {
                "claim_name": r.claim_name,
                "verification_method": r.verification_method,
                "source_evidence_type": r.source_evidence_type,
                "validation_rules": r.validation_rules,
                "required": r.required,
                "description": r.description,
            }
            for r in entity.claim_verification_rules
        ]
        
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.organization_id = entity.organization_id
            existing.status = entity.status
            existing.evidence_requirements = evidence_data
            existing.claim_verification_rules = rules_data
            existing.form_fields = entity.form_fields
            existing.claim_collection_rules = entity.claim_collection_rules
            existing.approval_strategy = entity.approval_strategy.value if hasattr(entity.approval_strategy, 'value') else str(entity.approval_strategy)
            existing.application_validity_days = entity.application_validity_days
            existing.notifications = entity.notifications
            existing.ui_config = entity.ui_config
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = ApplicationTemplateModel(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                organization_id=entity.organization_id,
                status=entity.status,
                credential_template_id="",  # Set via relationship, not owned here
                compliance_profile_id="",   # Set via relationship, not owned here
                evidence_requirements=evidence_data,
                claim_verification_rules=rules_data,
                form_fields=entity.form_fields,
                claim_collection_rules=entity.claim_collection_rules,
                approval_strategy=entity.approval_strategy.value if hasattr(entity.approval_strategy, 'value') else str(entity.approval_strategy),
                application_validity_days=entity.application_validity_days,
                notifications=entity.notifications,
                ui_config=entity.ui_config,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> ApplicationTemplate | None:
        """Get an Application Template by ID."""
        model = await self._session.get(ApplicationTemplateModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
    ) -> list[ApplicationTemplate]:
        """List Application Templates with optional filters."""
        stmt = select(ApplicationTemplateModel)
        if organization_id:
            stmt = stmt.where(ApplicationTemplateModel.organization_id == organization_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete an Application Template."""
        stmt = delete(ApplicationTemplateModel).where(ApplicationTemplateModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def exists(self, entity_id: str) -> bool:
        """Check if an Application Template exists."""
        model = await self._session.get(ApplicationTemplateModel, entity_id)
        return model is not None
    
    def _to_entity(self, model: ApplicationTemplateModel) -> ApplicationTemplate:
        """Convert model to entity."""
        from digital_identity.domain.value_objects import EvidenceRequirement, EvidenceType, ClaimVerificationRule
        
        evidence_reqs = []
        for r in (model.evidence_requirements or []):
            try:
                ev_type = EvidenceType(r["evidence_type"])
            except (ValueError, KeyError):
                ev_type = EvidenceType.DOCUMENT
            evidence_reqs.append(EvidenceRequirement(
                evidence_type=ev_type,
                required=r.get("required", True),
                provider_config=r.get("provider_config", {}),
                description=r.get("description"),
                auto_validate=r.get("auto_validate", False),
            ))
        
        claim_rules = []
        for r in (model.claim_verification_rules or []):
            claim_rules.append(ClaimVerificationRule(
                claim_name=r["claim_name"],
                verification_method=r["verification_method"],
                source_evidence_type=r.get("source_evidence_type"),
                validation_rules=r.get("validation_rules", {}),
                required=r.get("required", True),
                description=r.get("description"),
            ))
        
        return ApplicationTemplate(
            id=model.id,
            name=model.name,
            description=model.description,
            organization_id=getattr(model, 'organization_id', None),
            status=getattr(model, 'status', 'DRAFT'),
            evidence_requirements=evidence_reqs,
            form_fields=getattr(model, 'form_fields', []) or [],
            claim_collection_rules=getattr(model, 'claim_collection_rules', []) or [],
            approval_strategy=ApprovalStrategy(model.approval_strategy.upper() if model.approval_strategy else "AUTO"),
            application_validity_days=model.application_validity_days,
            notifications=getattr(model, 'notifications', {}) or {},
            ui_config=getattr(model, 'ui_config', {}) or {},
            metadata=model.metadata_,
            claim_verification_rules=claim_rules,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class CascadeRevocationOperationRepository:
    """Repository for Cascade Revocation Operation persistence."""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: CascadeRevocationOperation) -> CascadeRevocationOperation:
        """Save a Cascade Revocation Operation (create or update)."""
        existing = await self._session.get(CascadeRevocationOperationModel, entity.id)
        
        if existing:
            existing.organization_id = entity.organization_id
            existing.operation_type = entity.operation_type
            existing.trigger_entity_type = entity.trigger_entity_type
            existing.trigger_entity_id = entity.trigger_entity_id
            existing.status = entity.status
            existing.affected_credential_count = entity.affected_credential_count
            existing.affected_credential_ids = entity.affected_credential_ids
            existing.requires_confirmation = entity.requires_confirmation
            existing.confirmed_at = entity.confirmed_at
            existing.confirmed_by = entity.confirmed_by
            existing.max_cascade_depth = entity.max_cascade_depth
            existing.current_depth = entity.current_depth
            existing.circuit_breaker_threshold = entity.circuit_breaker_threshold
            existing.circuit_breaker_triggered = entity.circuit_breaker_triggered
            existing.can_rollback = entity.can_rollback
            existing.rollback_snapshot = entity.rollback_snapshot
            existing.rolled_back_at = entity.rolled_back_at
            existing.rolled_back_by = entity.rolled_back_by
            existing.error_message = entity.error_message
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = CascadeRevocationOperationModel(
                id=entity.id,
                organization_id=entity.organization_id,
                operation_type=entity.operation_type,
                trigger_entity_type=entity.trigger_entity_type,
                trigger_entity_id=entity.trigger_entity_id,
                status=entity.status,
                affected_credential_count=entity.affected_credential_count,
                affected_credential_ids=entity.affected_credential_ids,
                requires_confirmation=entity.requires_confirmation,
                confirmed_at=entity.confirmed_at,
                confirmed_by=entity.confirmed_by,
                max_cascade_depth=entity.max_cascade_depth,
                current_depth=entity.current_depth,
                circuit_breaker_threshold=entity.circuit_breaker_threshold,
                circuit_breaker_triggered=entity.circuit_breaker_triggered,
                can_rollback=entity.can_rollback,
                rollback_snapshot=entity.rollback_snapshot,
                rolled_back_at=entity.rolled_back_at,
                rolled_back_by=entity.rolled_back_by,
                error_message=entity.error_message,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> CascadeRevocationOperation | None:
        """Get a Cascade Revocation Operation by ID."""
        model = await self._session.get(CascadeRevocationOperationModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def list_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CascadeRevocationOperation]:
        """List operations by status."""
        stmt = (
            select(CascadeRevocationOperationModel)
            .where(CascadeRevocationOperationModel.status == status)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def list_by_trigger(
        self,
        trigger_entity_id: str,
    ) -> list[CascadeRevocationOperation]:
        """List operations for a specific trigger entity."""
        stmt = select(CascadeRevocationOperationModel).where(
            CascadeRevocationOperationModel.trigger_entity_id == trigger_entity_id
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Cascade Revocation Operation."""
        stmt = delete(CascadeRevocationOperationModel).where(
            CascadeRevocationOperationModel.id == entity_id
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    def _to_entity(self, model: CascadeRevocationOperationModel) -> CascadeRevocationOperation:
        """Convert model to entity."""
        return CascadeRevocationOperation(
            id=model.id,
            organization_id=getattr(model, 'organization_id', None),
            operation_type=model.operation_type,
            trigger_entity_type=model.trigger_entity_type,
            trigger_entity_id=model.trigger_entity_id,
            status=model.status,
            affected_credential_count=model.affected_credential_count,
            affected_credential_ids=model.affected_credential_ids,
            requires_confirmation=model.requires_confirmation,
            confirmed_at=model.confirmed_at,
            confirmed_by=model.confirmed_by,
            max_cascade_depth=model.max_cascade_depth,
            current_depth=model.current_depth,
            circuit_breaker_threshold=model.circuit_breaker_threshold,
            circuit_breaker_triggered=model.circuit_breaker_triggered,
            can_rollback=model.can_rollback,
            rollback_snapshot=model.rollback_snapshot,
            rolled_back_at=model.rolled_back_at,
            rolled_back_by=model.rolled_back_by,
            error_message=model.error_message,
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class RevocationProfileRepository:
    """Repository for Revocation Profile persistence."""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: RevocationProfile) -> RevocationProfile:
        """Save a Revocation Profile (create or update)."""
        existing = await self._session.get(RevocationProfileModel, entity.id)
        
        if existing:
            existing.organization_id = entity.organization_id
            existing.name = entity.name
            existing.revocation_mechanism = entity.revocation_mechanism
            existing.mechanism_priority = entity.mechanism_priority
            existing.check_mode = entity.check_mode.value
            existing.cache_ttl_seconds = entity.cache_ttl_seconds
            existing.offline_grace_seconds = entity.offline_grace_seconds
            existing.issuer_config = entity.issuer_config
            existing.status_list_url = entity.status_list_url
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = RevocationProfileModel(
                id=entity.id,
                organization_id=entity.organization_id,
                name=entity.name,
                revocation_mechanism=entity.revocation_mechanism,
                mechanism_priority=entity.mechanism_priority,
                check_mode=entity.check_mode.value,
                cache_ttl_seconds=entity.cache_ttl_seconds,
                offline_grace_seconds=entity.offline_grace_seconds,
                issuer_config=entity.issuer_config,
                status_list_url=entity.status_list_url,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> RevocationProfile | None:
        """Get a Revocation Profile by ID."""
        model = await self._session.get(RevocationProfileModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
    ) -> list[RevocationProfile]:
        """List Revocation Profiles with optional filters."""
        stmt = select(RevocationProfileModel)
        if organization_id:
            stmt = stmt.where(RevocationProfileModel.organization_id == organization_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Revocation Profile."""
        stmt = delete(RevocationProfileModel).where(RevocationProfileModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Revocation Profile exists."""
        model = await self._session.get(RevocationProfileModel, entity_id)
        return model is not None
    
    def _to_entity(self, model: RevocationProfileModel) -> RevocationProfile:
        """Convert model to entity."""
        return RevocationProfile(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            revocation_mechanism=model.revocation_mechanism or [],
            mechanism_priority=model.mechanism_priority or [],
            check_mode=RevocationTimingMode(model.check_mode),
            cache_ttl_seconds=model.cache_ttl_seconds,
            offline_grace_seconds=model.offline_grace_seconds,
            issuer_config=model.issuer_config or {},
            status_list_url=model.status_list_url,
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class VerificationSessionRepository:
    """Repository for Verification Session persistence."""
    
    def __init__(self, session: AsyncSession):
        self._session = session
    
    async def save(self, entity: VerificationSession) -> VerificationSession:
        """Save a Verification Session (create or update)."""
        existing = await self._session.get(VerificationSessionModel, entity.id)
        
        if existing:
            existing.flow_id = entity.flow_id
            existing.flow_instance_id = entity.flow_instance_id
            existing.presentation_policy_id = entity.presentation_policy_id
            existing.deployment_profile_id = entity.deployment_profile_id
            existing.verifier_nonce = entity.verifier_nonce
            existing.holder_id = entity.holder_id
            existing.status = entity.status
            existing.result = entity.result
            existing.expires_at = entity.expires_at
            existing.completed_at = entity.completed_at
            existing.error = entity.error
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = VerificationSessionModel(
                id=entity.id,
                flow_id=entity.flow_id,
                flow_instance_id=entity.flow_instance_id,
                presentation_policy_id=entity.presentation_policy_id,
                deployment_profile_id=entity.deployment_profile_id,
                verifier_nonce=entity.verifier_nonce,
                holder_id=entity.holder_id,
                status=entity.status,
                result=entity.result,
                expires_at=entity.expires_at,
                completed_at=entity.completed_at,
                error=entity.error,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)
        
        await self._session.commit()
        return entity
    
    async def get(self, entity_id: str) -> VerificationSession | None:
        """Get a Verification Session by ID."""
        model = await self._session.get(VerificationSessionModel, entity_id)
        if model:
            return self._to_entity(model)
        return None
    
    async def list_by_flow(
        self,
        flow_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[VerificationSession]:
        """List sessions for a specific flow."""
        stmt = (
            select(VerificationSessionModel)
            .where(VerificationSessionModel.flow_id == flow_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def list_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[VerificationSession]:
        """List sessions by status."""
        stmt = (
            select(VerificationSessionModel)
            .where(VerificationSessionModel.status == status)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Verification Session."""
        stmt = delete(VerificationSessionModel).where(VerificationSessionModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0
    
    def _to_entity(self, model: VerificationSessionModel) -> VerificationSession:
        """Convert model to entity."""
        return VerificationSession(
            id=model.id,
            flow_id=model.flow_id,
            flow_instance_id=model.flow_instance_id,
            presentation_policy_id=model.presentation_policy_id,
            deployment_profile_id=model.deployment_profile_id,
            verifier_nonce=model.verifier_nonce,
            holder_id=model.holder_id,
            status=model.status,
            result=model.result,
            expires_at=model.expires_at,
            completed_at=model.completed_at,
            error=model.error,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class ComplianceProfileRepository:
    """Repository for Compliance Profile persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: ComplianceProfile) -> ComplianceProfile:
        """Save a Compliance Profile (create or update)."""
        from dataclasses import asdict as _asdict

        def _artifact_to_dict(req) -> dict | None:
            if req is None:
                return None
            return {
                "requires_x509_cert": req.requires_x509_cert,
                "requires_did": req.requires_did,
                "requires_jwk": req.requires_jwk,
                "cert_key_usage": list(req.cert_key_usage),
                "recommended_algorithms": [
                    a.value if hasattr(a, "value") else str(a)
                    for a in req.recommended_algorithms
                ],
            }

        def _rules_to_list(rules) -> list[dict]:
            out = []
            for r in rules:
                out.append({
                    "claim_name": r.claim_name,
                    "verification_method": r.verification_method.value if hasattr(r.verification_method, "value") else str(r.verification_method),
                    "source_evidence_type": r.source_evidence_type.value if r.source_evidence_type and hasattr(r.source_evidence_type, "value") else None,
                    "validation_rules": r.validation_rules,
                    "required": r.required,
                    "description": r.description,
                })
            return out

        artifact_data = _artifact_to_dict(entity.issuer_artifact_requirements)
        rules_data = _rules_to_list(entity.default_verification_rules)

        existing = await self._session.get(ComplianceProfileModel, entity.id)
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.compliance_code = entity.compliance_code
            existing.credential_format = entity.credential_format.value if hasattr(entity.credential_format, "value") else str(entity.credential_format)
            existing.issuance_protocol = entity.issuance_protocol
            existing.issuer_artifact_requirements = artifact_data
            existing.default_verification_rules = rules_data
            existing.trust_profile_constraints = entity.trust_profile_constraints
            existing.is_system = entity.is_system
            existing.organization_id = entity.organization_id
            existing.discoverable = entity.discoverable
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = ComplianceProfileModel(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                compliance_code=entity.compliance_code,
                credential_format=entity.credential_format.value if hasattr(entity.credential_format, "value") else str(entity.credential_format),
                issuance_protocol=entity.issuance_protocol,
                issuer_artifact_requirements=artifact_data,
                default_verification_rules=rules_data,
                trust_profile_constraints=entity.trust_profile_constraints,
                is_system=entity.is_system,
                organization_id=entity.organization_id,
                discoverable=entity.discoverable,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)

        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> ComplianceProfile | None:
        """Get a Compliance Profile by ID."""
        model = await self._session.get(ComplianceProfileModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def get_by_code(self, compliance_code: str) -> ComplianceProfile | None:
        """Get a Compliance Profile by compliance_code."""
        stmt = select(ComplianceProfileModel).where(
            ComplianceProfileModel.compliance_code == compliance_code
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
        is_system: bool | None = None,
        discoverable_only: bool = False,
    ) -> list[ComplianceProfile]:
        """List Compliance Profiles with optional filters."""
        stmt = select(ComplianceProfileModel)
        if organization_id is not None:
            stmt = stmt.where(ComplianceProfileModel.organization_id == organization_id)
        if is_system is not None:
            stmt = stmt.where(ComplianceProfileModel.is_system == is_system)
        if discoverable_only:
            stmt = stmt.where(ComplianceProfileModel.discoverable == True)  # noqa: E712
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete a Compliance Profile."""
        stmt = delete(ComplianceProfileModel).where(ComplianceProfileModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    async def exists(self, entity_id: str) -> bool:
        """Check if a Compliance Profile exists."""
        model = await self._session.get(ComplianceProfileModel, entity_id)
        return model is not None

    def _to_entity(self, model: ComplianceProfileModel) -> ComplianceProfile:
        """Convert model to entity."""
        from digital_identity.domain.value_objects import (
            IssuerArtifactRequirements,
            ClaimVerificationRule,
            ClaimVerificationMethod,
            EvidenceType,
            CryptoAlgorithm,
        )

        artifact_req = None
        if model.issuer_artifact_requirements:
            raw = model.issuer_artifact_requirements
            artifact_req = IssuerArtifactRequirements(
                requires_x509_cert=raw.get("requires_x509_cert", False),
                requires_did=raw.get("requires_did", False),
                requires_jwk=raw.get("requires_jwk", False),
                cert_key_usage=raw.get("cert_key_usage", []),
                recommended_algorithms=[
                    CryptoAlgorithm(a) for a in raw.get("recommended_algorithms", [])
                    if a in CryptoAlgorithm._value2member_map_
                ],
            )

        rules = []
        for r in (model.default_verification_rules or []):
            try:
                method = ClaimVerificationMethod(r.get("verification_method", "DOCUMENT_CHECK"))
            except ValueError:
                method = ClaimVerificationMethod.DOCUMENT_CHECK
            src = None
            if r.get("source_evidence_type"):
                try:
                    src = EvidenceType(r["source_evidence_type"])
                except ValueError:
                    src = None
            rules.append(ClaimVerificationRule(
                claim_name=r.get("claim_name", ""),
                verification_method=method,
                source_evidence_type=src,
                validation_rules=r.get("validation_rules", {}),
                required=r.get("required", True),
                description=r.get("description"),
            ))

        return ComplianceProfile(
            id=model.id,
            name=model.name,
            description=model.description,
            compliance_code=model.compliance_code,
            credential_format=CredentialFormat(model.credential_format),
            issuance_protocol=model.issuance_protocol,
            issuer_artifact_requirements=artifact_req,
            default_verification_rules=rules,
            trust_profile_constraints=model.trust_profile_constraints or {},
            is_system=model.is_system,
            organization_id=model.organization_id,
            discoverable=model.discoverable,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class IssuerRepository:
    """Repository for IssuerEntity persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: IssuerEntity) -> IssuerEntity:
        """Save an IssuerEntity (create or update)."""
        existing = await self._session.get(IssuerEntityModel, entity.id)

        if existing:
            existing.organization_id = entity.organization_id
            existing.issuer_id = entity.issuer_id
            existing.issuer_type = entity.issuer_type
            existing.display_name = entity.display_name
            existing.description = entity.description
            existing.is_system_issuer = entity.is_system_issuer
            existing.compliance_status = entity.compliance_status
            existing.accreditation_body = entity.accreditation_body
            existing.accreditation_date = entity.accreditation_date
            existing.valid_from = entity.valid_from
            existing.valid_until = entity.valid_until
            existing.trust_anchor_id = entity.trust_anchor_id
            existing.revoked_at = entity.revoked_at
            existing.revocation_reason = entity.revocation_reason
            existing.revoked_by = entity.revoked_by
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = IssuerEntityModel(
                id=entity.id,
                organization_id=entity.organization_id,
                issuer_id=entity.issuer_id,
                issuer_type=entity.issuer_type,
                display_name=entity.display_name,
                description=entity.description,
                is_system_issuer=entity.is_system_issuer,
                compliance_status=entity.compliance_status,
                accreditation_body=entity.accreditation_body,
                accreditation_date=entity.accreditation_date,
                valid_from=entity.valid_from,
                valid_until=entity.valid_until,
                trust_anchor_id=entity.trust_anchor_id,
                revoked_at=entity.revoked_at,
                revocation_reason=entity.revocation_reason,
                revoked_by=entity.revoked_by,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)

        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> IssuerEntity | None:
        """Get an IssuerEntity by ID."""
        model = await self._session.get(IssuerEntityModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def find_by_trust_anchor(self, trust_anchor_id: str) -> list[IssuerEntity]:
        """Find all issuers linked to a trust anchor."""
        stmt = select(IssuerEntityModel).where(
            IssuerEntityModel.trust_anchor_id == trust_anchor_id
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
    ) -> list[IssuerEntity]:
        """List issuers with optional organization filter."""
        stmt = select(IssuerEntityModel)
        if organization_id is not None:
            stmt = stmt.where(IssuerEntityModel.organization_id == organization_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete an IssuerEntity."""
        stmt = delete(IssuerEntityModel).where(IssuerEntityModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    async def exists(self, entity_id: str) -> bool:
        """Check if an IssuerEntity exists."""
        model = await self._session.get(IssuerEntityModel, entity_id)
        return model is not None

    def _to_entity(self, model: IssuerEntityModel) -> IssuerEntity:
        """Convert model to entity."""
        return IssuerEntity(
            id=model.id,
            organization_id=model.organization_id,
            issuer_id=model.issuer_id,
            issuer_type=model.issuer_type,
            display_name=model.display_name,
            description=model.description,
            is_system_issuer=model.is_system_issuer,
            compliance_status=model.compliance_status,
            accreditation_body=model.accreditation_body,
            accreditation_date=model.accreditation_date,
            valid_from=model.valid_from,
            valid_until=model.valid_until,
            trust_anchor_id=model.trust_anchor_id,
            revoked_at=model.revoked_at,
            revocation_reason=model.revocation_reason,
            revoked_by=model.revoked_by,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class TrustProfileIssuerRepository:
    """Repository for TrustProfileIssuer relationship persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: TrustProfileIssuer) -> TrustProfileIssuer:
        """Save a TrustProfileIssuer (create or update)."""
        existing = await self._session.get(TrustProfileIssuerModel, entity.id)

        if existing:
            existing.trust_profile_id = entity.trust_profile_id
            existing.issuer_id = entity.issuer_id
            existing.trust_level = entity.trust_level
            existing.relationship_status = entity.relationship_status
            existing.cascade_revocation_policy = entity.cascade_revocation_policy
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = TrustProfileIssuerModel(
                id=entity.id,
                trust_profile_id=entity.trust_profile_id,
                issuer_id=entity.issuer_id,
                trust_level=entity.trust_level,
                relationship_status=entity.relationship_status,
                cascade_revocation_policy=entity.cascade_revocation_policy,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)

        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> TrustProfileIssuer | None:
        """Get a TrustProfileIssuer by ID."""
        model = await self._session.get(TrustProfileIssuerModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def get_by_profile_and_issuer(
        self,
        trust_profile_id: str,
        issuer_id: str,
    ) -> TrustProfileIssuer | None:
        """Get relationship by trust_profile_id + issuer_id composite key."""
        stmt = select(TrustProfileIssuerModel).where(
            TrustProfileIssuerModel.trust_profile_id == trust_profile_id,
            TrustProfileIssuerModel.issuer_id == issuer_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None

    async def find_by_issuer(self, issuer_id: str) -> list[TrustProfileIssuer]:
        """Find all trust profile relationships for an issuer."""
        stmt = select(TrustProfileIssuerModel).where(
            TrustProfileIssuerModel.issuer_id == issuer_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def find_by_profile(self, trust_profile_id: str) -> list[TrustProfileIssuer]:
        """Find all issuer relationships for a trust profile."""
        stmt = select(TrustProfileIssuerModel).where(
            TrustProfileIssuerModel.trust_profile_id == trust_profile_id,
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete a TrustProfileIssuer."""
        stmt = delete(TrustProfileIssuerModel).where(
            TrustProfileIssuerModel.id == entity_id
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: TrustProfileIssuerModel) -> TrustProfileIssuer:
        """Convert model to entity."""
        return TrustProfileIssuer(
            id=model.id,
            trust_profile_id=model.trust_profile_id,
            issuer_id=model.issuer_id,
            trust_level=model.trust_level,
            relationship_status=model.relationship_status,
            cascade_revocation_policy=model.cascade_revocation_policy,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=getattr(model, 'version', 1),
        )


class TrustFrameworkRepository:
    """Repository for Trust Framework persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: TrustFramework) -> TrustFramework:
        """Save a Trust Framework (create or update)."""
        existing = await self._session.get(TrustFrameworkModel, entity.id)

        if existing:
            existing.code = entity.code
            existing.display_name = entity.display_name
            existing.description = entity.description
            existing.pkd_endpoints = entity.pkd_endpoints
            existing.default_algorithms = [a.value for a in entity.default_algorithms]
            existing.default_formats = [f.value for f in entity.default_formats]
            existing.validation_ruleset = entity.validation_ruleset
            existing.sync_config = entity.sync_config
            existing.is_system = entity.is_system
            existing.updated_at = entity.updated_at
        else:
            model = TrustFrameworkModel(
                id=entity.id,
                code=entity.code,
                display_name=entity.display_name,
                description=entity.description,
                pkd_endpoints=entity.pkd_endpoints,
                default_algorithms=[a.value for a in entity.default_algorithms],
                default_formats=[f.value for f in entity.default_formats],
                validation_ruleset=entity.validation_ruleset,
                sync_config=entity.sync_config,
                is_system=entity.is_system,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            self._session.add(model)

        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> TrustFramework | None:
        """Get a Trust Framework by ID."""
        model = await self._session.get(TrustFrameworkModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def get_by_code(self, code: str) -> TrustFramework | None:
        """Get a Trust Framework by unique code."""
        stmt = select(TrustFrameworkModel).where(TrustFrameworkModel.code == code)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[TrustFramework]:
        """List Trust Frameworks."""
        stmt = select(TrustFrameworkModel).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete a Trust Framework."""
        stmt = delete(TrustFrameworkModel).where(TrustFrameworkModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    async def exists(self, entity_id: str) -> bool:
        """Check if a Trust Framework exists."""
        model = await self._session.get(TrustFrameworkModel, entity_id)
        return model is not None

    def _to_entity(self, model: TrustFrameworkModel) -> TrustFramework:
        """Convert model to entity."""
        return TrustFramework(
            id=model.id,
            code=model.code,
            display_name=model.display_name,
            description=model.description,
            pkd_endpoints=model.pkd_endpoints or {},
            default_algorithms=[CryptoAlgorithm(a) for a in (model.default_algorithms or [])],
            default_formats=[CredentialFormat(f) for f in (model.default_formats or [])],
            validation_ruleset=model.validation_ruleset or {},
            sync_config=model.sync_config or {},
            is_system=model.is_system,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class OrganizationTrustProfileRepository:
    """Repository for Organization Trust Profile persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: OrganizationTrustProfile) -> OrganizationTrustProfile:
        """Save an Organization Trust Profile (create or update)."""
        existing = await self._session.get(OrganizationTrustProfileModel, entity.id)

        if existing:
            existing.organization_id = entity.organization_id
            existing.framework_id = entity.framework_id
            existing.name = entity.name
            existing.display_name = entity.display_name
            existing.description = entity.description
            existing.enabled = entity.enabled
            existing.use_case_tags = entity.use_case_tags
            existing.compliance_status = entity.compliance_status
            existing.auto_generated = entity.auto_generated
            existing.revocation_policy = asdict(entity.revocation_policy) if entity.revocation_policy else None
            existing.time_policy = asdict(entity.time_policy) if entity.time_policy else None
            existing.allowed_algorithms = [a.value for a in entity.allowed_algorithms] if entity.allowed_algorithms is not None else None
            existing.allowed_formats = [f.value for f in entity.allowed_formats] if entity.allowed_formats is not None else None
            existing.allowed_issuers = entity.allowed_issuers
            existing.denied_issuers = entity.denied_issuers
            existing.jurisdiction_filter = entity.jurisdiction_filter
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = OrganizationTrustProfileModel(
                id=entity.id,
                organization_id=entity.organization_id,
                framework_id=entity.framework_id,
                name=entity.name,
                display_name=entity.display_name,
                description=entity.description,
                enabled=entity.enabled,
                use_case_tags=entity.use_case_tags,
                compliance_status=entity.compliance_status,
                auto_generated=entity.auto_generated,
                revocation_policy=asdict(entity.revocation_policy) if entity.revocation_policy else None,
                time_policy=asdict(entity.time_policy) if entity.time_policy else None,
                allowed_algorithms=[a.value for a in entity.allowed_algorithms] if entity.allowed_algorithms is not None else None,
                allowed_formats=[f.value for f in entity.allowed_formats] if entity.allowed_formats is not None else None,
                allowed_issuers=entity.allowed_issuers,
                denied_issuers=entity.denied_issuers,
                jurisdiction_filter=entity.jurisdiction_filter,
                metadata_=entity.metadata,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                version=entity.version,
            )
            self._session.add(model)

        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> OrganizationTrustProfile | None:
        """Get an Organization Trust Profile by ID."""
        model = await self._session.get(OrganizationTrustProfileModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
        framework_id: str | None = None,
    ) -> list[OrganizationTrustProfile]:
        """List Organization Trust Profiles with optional filters."""
        stmt = select(OrganizationTrustProfileModel)
        if organization_id:
            stmt = stmt.where(OrganizationTrustProfileModel.organization_id == organization_id)
        if framework_id:
            stmt = stmt.where(OrganizationTrustProfileModel.framework_id == framework_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete an Organization Trust Profile."""
        stmt = delete(OrganizationTrustProfileModel).where(OrganizationTrustProfileModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    async def exists(self, entity_id: str) -> bool:
        """Check if an Organization Trust Profile exists."""
        model = await self._session.get(OrganizationTrustProfileModel, entity_id)
        return model is not None

    def _to_entity(self, model: OrganizationTrustProfileModel) -> OrganizationTrustProfile:
        """Convert model to entity."""
        revocation_policy = None
        if model.revocation_policy:
            revocation_policy = RevocationPolicy(**model.revocation_policy)

        time_policy = None
        if model.time_policy:
            time_policy = TimePolicy(**model.time_policy)

        return OrganizationTrustProfile(
            id=model.id,
            organization_id=model.organization_id,
            framework_id=model.framework_id,
            name=model.name,
            display_name=model.display_name,
            description=model.description,
            enabled=model.enabled,
            use_case_tags=model.use_case_tags or [],
            compliance_status=model.compliance_status,
            auto_generated=model.auto_generated,
            revocation_policy=revocation_policy,
            time_policy=time_policy,
            allowed_algorithms=[CryptoAlgorithm(a) for a in model.allowed_algorithms] if model.allowed_algorithms is not None else None,
            allowed_formats=[CredentialFormat(f) for f in model.allowed_formats] if model.allowed_formats is not None else None,
            allowed_issuers=model.allowed_issuers,
            denied_issuers=model.denied_issuers,
            jurisdiction_filter=model.jurisdiction_filter,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )


class OrganizationRepository:
    """Repository for Organization persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: Organization) -> Organization:
        """Save an Organization (create or update)."""
        existing = await self._session.get(OrganizationModel, entity.id)

        if existing:
            existing.name = entity.name
            existing.display_name = entity.display_name
            existing.description = entity.description
            existing.visibility = entity.visibility
            existing.owner_id = entity.owner_id
            existing.join_code = entity.join_code
            existing.status = entity.status
            existing.updated_at = entity.updated_at
        else:
            model = OrganizationModel(
                id=entity.id,
                name=entity.name,
                display_name=entity.display_name,
                description=entity.description,
                visibility=entity.visibility,
                owner_id=entity.owner_id,
                join_code=entity.join_code,
                status=entity.status,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            self._session.add(model)

        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> Organization | None:
        """Get an Organization by ID."""
        model = await self._session.get(OrganizationModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def get_by_name(self, name: str) -> Organization | None:
        """Get an Organization by unique slug name."""
        stmt = select(OrganizationModel).where(OrganizationModel.name == name)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        visibility: str | None = None,
    ) -> list[Organization]:
        """List Organizations with optional filters."""
        stmt = select(OrganizationModel)
        if status:
            stmt = stmt.where(OrganizationModel.status == status)
        if visibility:
            stmt = stmt.where(OrganizationModel.visibility == visibility)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete an Organization."""
        stmt = delete(OrganizationModel).where(OrganizationModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    async def exists(self, entity_id: str) -> bool:
        """Check if an Organization exists."""
        model = await self._session.get(OrganizationModel, entity_id)
        return model is not None

    def _to_entity(self, model: OrganizationModel) -> Organization:
        """Convert model to entity."""
        return Organization(
            id=model.id,
            name=model.name,
            display_name=model.display_name,
            description=model.description,
            visibility=model.visibility,
            owner_id=model.owner_id,
            join_code=model.join_code,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class WebhookRepository:
    """Repository for Webhook persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: Webhook) -> Webhook:
        """Save a Webhook (insert or update)."""
        existing = await self._session.get(WebhookModel, entity.id)
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.endpoint_url = entity.endpoint_url
            existing.events = entity.events
            existing.signing_secret_hash = entity.signing_secret_hash
            existing.signing_secret_masked = entity.signing_secret_masked
            existing.enabled = entity.enabled
            existing.api_version = entity.api_version
            existing.filter = entity.filter
            existing.delivery_config = entity.delivery_config
            existing.status = entity.status
            existing.failure_count = entity.failure_count
            existing.last_triggered_at = entity.last_triggered_at
            existing.last_success_at = entity.last_success_at
            existing.updated_at = entity.updated_at
        else:
            model = WebhookModel(
                id=entity.id,
                organization_id=entity.organization_id,
                name=entity.name,
                description=entity.description,
                endpoint_url=entity.endpoint_url,
                events=entity.events,
                signing_secret_hash=entity.signing_secret_hash,
                signing_secret_masked=entity.signing_secret_masked,
                enabled=entity.enabled,
                api_version=entity.api_version,
                filter=entity.filter,
                delivery_config=entity.delivery_config,
                status=entity.status,
                failure_count=entity.failure_count,
                last_triggered_at=entity.last_triggered_at,
                last_success_at=entity.last_success_at,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> Webhook | None:
        """Get a Webhook by ID."""
        model = await self._session.get(WebhookModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def list(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        enabled: bool | None = None,
    ) -> list[Webhook]:
        """List Webhooks for an organization."""
        stmt = select(WebhookModel).where(WebhookModel.organization_id == organization_id)
        if enabled is not None:
            stmt = stmt.where(WebhookModel.enabled == enabled)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete a Webhook."""
        stmt = delete(WebhookModel).where(WebhookModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: WebhookModel) -> Webhook:
        """Convert model to entity."""
        return Webhook(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            description=model.description,
            endpoint_url=model.endpoint_url,
            events=model.events or [],
            signing_secret_hash=model.signing_secret_hash,
            signing_secret_masked=model.signing_secret_masked,
            enabled=model.enabled,
            api_version=model.api_version,
            filter=model.filter or {},
            delivery_config=model.delivery_config or {},
            status=model.status,
            failure_count=model.failure_count,
            last_triggered_at=model.last_triggered_at,
            last_success_at=model.last_success_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SubscriptionRepository:
    """Repository for Subscription persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: Subscription) -> Subscription:
        """Save a Subscription (insert or update)."""
        existing = await self._session.get(SubscriptionModel, entity.id)
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.event_types = entity.event_types
            existing.delivery = entity.delivery
            existing.filter = entity.filter
            existing.enabled = entity.enabled
            existing.retry_policy = entity.retry_policy
            existing.updated_at = entity.updated_at
        else:
            model = SubscriptionModel(
                id=entity.id,
                organization_id=entity.organization_id,
                name=entity.name,
                description=entity.description,
                event_types=entity.event_types,
                delivery=entity.delivery,
                filter=entity.filter,
                enabled=entity.enabled,
                retry_policy=entity.retry_policy,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> Subscription | None:
        """Get a Subscription by ID."""
        model = await self._session.get(SubscriptionModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def list(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        enabled: bool | None = None,
    ) -> list[Subscription]:
        """List Subscriptions for an organization."""
        stmt = select(SubscriptionModel).where(SubscriptionModel.organization_id == organization_id)
        if enabled is not None:
            stmt = stmt.where(SubscriptionModel.enabled == enabled)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete a Subscription."""
        stmt = delete(SubscriptionModel).where(SubscriptionModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: SubscriptionModel) -> Subscription:
        """Convert model to entity."""
        return Subscription(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            description=model.description,
            event_types=model.event_types or [],
            delivery=model.delivery or {},
            filter=model.filter or {},
            enabled=model.enabled,
            retry_policy=model.retry_policy or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class ApiKeyRepository:
    """Repository for API Key persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: ApiKey) -> ApiKey:
        """Save an ApiKey (insert or update)."""
        existing = await self._session.get(ApiKeyModel, entity.id)
        if existing:
            existing.name = entity.name
            existing.description = entity.description
            existing.key_prefix = entity.key_prefix
            existing.key_hash = entity.key_hash
            existing.scope_type = entity.scope_type
            existing.deployment_profile_id = entity.deployment_profile_id
            existing.scopes = entity.scopes
            existing.enabled = entity.enabled
            existing.expires_at = entity.expires_at
            existing.last_used_at = entity.last_used_at
            existing.updated_at = entity.updated_at
        else:
            model = ApiKeyModel(
                id=entity.id,
                organization_id=entity.organization_id,
                name=entity.name,
                description=entity.description,
                key_prefix=entity.key_prefix,
                key_hash=entity.key_hash,
                scope_type=entity.scope_type,
                deployment_profile_id=entity.deployment_profile_id,
                scopes=entity.scopes,
                enabled=entity.enabled,
                expires_at=entity.expires_at,
                last_used_at=entity.last_used_at,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> ApiKey | None:
        """Get an ApiKey by ID."""
        model = await self._session.get(ApiKeyModel, entity_id)
        if model:
            return self._to_entity(model)
        return None

    async def get_by_prefix(self, key_prefix: str) -> ApiKey | None:
        """Look up an ApiKey by its prefix."""
        stmt = select(ApiKeyModel).where(ApiKeyModel.key_prefix == key_prefix)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            return self._to_entity(model)
        return None

    async def list(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        enabled: bool | None = None,
        scope_type: str | None = None,
    ) -> list[ApiKey]:
        """List ApiKeys for an organization."""
        stmt = select(ApiKeyModel).where(ApiKeyModel.organization_id == organization_id)
        if enabled is not None:
            stmt = stmt.where(ApiKeyModel.enabled == enabled)
        if scope_type:
            stmt = stmt.where(ApiKeyModel.scope_type == scope_type)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        """Delete an ApiKey."""
        stmt = delete(ApiKeyModel).where(ApiKeyModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: ApiKeyModel) -> ApiKey:
        """Convert model to entity."""
        return ApiKey(
            id=model.id,
            organization_id=model.organization_id,
            name=model.name,
            description=model.description,
            key_prefix=model.key_prefix,
            key_hash=model.key_hash,
            scope_type=model.scope_type,
            deployment_profile_id=model.deployment_profile_id,
            scopes=model.scopes or [],
            enabled=model.enabled,
            expires_at=model.expires_at,
            last_used_at=model.last_used_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class IssuanceRecordRepository:
    """Repository for IssuanceRecord persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: IssuanceRecord) -> IssuanceRecord:
        existing = await self._session.get(IssuanceRecordModel, entity.id)
        if existing:
            for attr in ("flow_execution_id", "application_id", "credential_id",
                         "credential_format", "offer_uri", "offer_expires_at",
                         "status", "revocation_index", "valid_from", "valid_until",
                         "claimed_at", "updated_at"):
                setattr(existing, attr, getattr(entity, attr))
        else:
            model = IssuanceRecordModel(
                id=entity.id, flow_id=entity.flow_id,
                flow_execution_id=entity.flow_execution_id,
                application_id=entity.application_id,
                credential_template_id=entity.credential_template_id,
                holder_id=entity.holder_id, credential_id=entity.credential_id,
                credential_format=entity.credential_format,
                offer_uri=entity.offer_uri,
                offer_expires_at=entity.offer_expires_at,
                status=entity.status, revocation_index=entity.revocation_index,
                valid_from=entity.valid_from, valid_until=entity.valid_until,
                claimed_at=entity.claimed_at,
                created_at=entity.created_at, updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> IssuanceRecord | None:
        model = await self._session.get(IssuanceRecordModel, entity_id)
        return self._to_entity(model) if model else None

    async def list(self, flow_id: str | None = None, holder_id: str | None = None,
                   status: str | None = None, skip: int = 0, limit: int = 100) -> list[IssuanceRecord]:
        stmt = select(IssuanceRecordModel)
        if flow_id:
            stmt = stmt.where(IssuanceRecordModel.flow_id == flow_id)
        if holder_id:
            stmt = stmt.where(IssuanceRecordModel.holder_id == holder_id)
        if status:
            stmt = stmt.where(IssuanceRecordModel.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(IssuanceRecordModel).where(IssuanceRecordModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: IssuanceRecordModel) -> IssuanceRecord:
        return IssuanceRecord(
            id=model.id, flow_id=model.flow_id,
            flow_execution_id=model.flow_execution_id,
            application_id=model.application_id,
            credential_template_id=model.credential_template_id,
            holder_id=model.holder_id, credential_id=model.credential_id,
            credential_format=model.credential_format,
            offer_uri=model.offer_uri, offer_expires_at=model.offer_expires_at,
            status=model.status, revocation_index=model.revocation_index,
            valid_from=model.valid_from, valid_until=model.valid_until,
            claimed_at=model.claimed_at,
            created_at=model.created_at, updated_at=model.updated_at,
        )


class PolicySetRepository:
    """Repository for PolicySet persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: PolicySet) -> PolicySet:
        existing = await self._session.get(PolicySetModel, entity.id)
        if existing:
            for attr in ("name", "description", "policy_type", "cedar_policies",
                         "cedar_schema_version", "status", "updated_at"):
                setattr(existing, attr, getattr(entity, attr))
        else:
            model = PolicySetModel(
                id=entity.id, organization_id=entity.organization_id,
                name=entity.name, description=entity.description,
                policy_type=entity.policy_type,
                cedar_policies=entity.cedar_policies,
                cedar_schema_version=entity.cedar_schema_version,
                status=entity.status,
                created_at=entity.created_at, updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> PolicySet | None:
        model = await self._session.get(PolicySetModel, entity_id)
        return self._to_entity(model) if model else None

    async def list(self, organization_id: str, policy_type: str | None = None,
                   status: str | None = None, skip: int = 0, limit: int = 100) -> list[PolicySet]:
        stmt = select(PolicySetModel).where(PolicySetModel.organization_id == organization_id)
        if policy_type:
            stmt = stmt.where(PolicySetModel.policy_type == policy_type)
        if status:
            stmt = stmt.where(PolicySetModel.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(PolicySetModel).where(PolicySetModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: PolicySetModel) -> PolicySet:
        return PolicySet(
            id=model.id, organization_id=model.organization_id,
            name=model.name, description=model.description,
            policy_type=model.policy_type,
            cedar_policies=model.cedar_policies or [],
            cedar_schema_version=model.cedar_schema_version,
            status=model.status,
            created_at=model.created_at, updated_at=model.updated_at,
        )


class WalletProfileRepository:
    """Repository for WalletProfile persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: WalletProfile) -> WalletProfile:
        existing = await self._session.get(WalletProfileModel, entity.id)
        if existing:
            for attr in ("name", "description", "is_override", "override_precedence",
                         "credential_format", "issuance_protocol",
                         "compliance_profile_code", "wallet_apps", "merge_strategy",
                         "specifications", "supported_platforms", "deep_link_pattern",
                         "updated_at"):
                setattr(existing, attr, getattr(entity, attr))
        else:
            model = WalletProfileModel(
                id=entity.id, organization_id=entity.organization_id,
                is_override=entity.is_override,
                override_precedence=entity.override_precedence,
                name=entity.name, description=entity.description,
                credential_format=entity.credential_format,
                issuance_protocol=entity.issuance_protocol,
                compliance_profile_code=entity.compliance_profile_code,
                wallet_apps=entity.wallet_apps,
                merge_strategy=entity.merge_strategy,
                specifications=entity.specifications,
                supported_platforms=entity.supported_platforms,
                deep_link_pattern=entity.deep_link_pattern,
                created_at=entity.created_at, updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> WalletProfile | None:
        model = await self._session.get(WalletProfileModel, entity_id)
        return self._to_entity(model) if model else None

    async def list(self, organization_id: str | None = None, credential_format: str | None = None,
                   skip: int = 0, limit: int = 100) -> list[WalletProfile]:
        stmt = select(WalletProfileModel)
        if organization_id:
            stmt = stmt.where(WalletProfileModel.organization_id == organization_id)
        if credential_format:
            stmt = stmt.where(WalletProfileModel.credential_format == credential_format)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(WalletProfileModel).where(WalletProfileModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: WalletProfileModel) -> WalletProfile:
        return WalletProfile(
            id=model.id, organization_id=model.organization_id,
            is_override=model.is_override,
            override_precedence=model.override_precedence,
            name=model.name, description=model.description,
            credential_format=model.credential_format,
            issuance_protocol=model.issuance_protocol,
            compliance_profile_code=model.compliance_profile_code,
            wallet_apps=model.wallet_apps or [],
            merge_strategy=model.merge_strategy,
            specifications=model.specifications or [],
            supported_platforms=model.supported_platforms or [],
            deep_link_pattern=model.deep_link_pattern,
            created_at=model.created_at, updated_at=model.updated_at,
        )


class DeviceRegistrationRepository:
    """Repository for DeviceRegistration persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: DeviceRegistration) -> DeviceRegistration:
        existing = await self._session.get(DeviceRegistrationModel, entity.id)
        if existing:
            for attr in ("device_id", "platform", "fcm_token", "app_version",
                         "os_version", "device_model", "preferences",
                         "public_key_der", "public_key_kid", "key_valid_from",
                         "key_valid_until", "is_active", "last_seen_at", "updated_at"):
                setattr(existing, attr, getattr(entity, attr))
        else:
            model = DeviceRegistrationModel(
                id=entity.id, user_id=entity.user_id,
                organization_id=entity.organization_id,
                device_id=entity.device_id, platform=entity.platform,
                fcm_token=entity.fcm_token, app_version=entity.app_version,
                os_version=entity.os_version, device_model=entity.device_model,
                preferences=entity.preferences,
                public_key_der=entity.public_key_der,
                public_key_kid=entity.public_key_kid,
                key_valid_from=entity.key_valid_from,
                key_valid_until=entity.key_valid_until,
                is_active=entity.is_active, last_seen_at=entity.last_seen_at,
                created_at=entity.created_at, updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> DeviceRegistration | None:
        model = await self._session.get(DeviceRegistrationModel, entity_id)
        return self._to_entity(model) if model else None

    async def get_by_device_id(self, user_id: str, device_id: str) -> DeviceRegistration | None:
        stmt = select(DeviceRegistrationModel).where(
            DeviceRegistrationModel.user_id == user_id,
            DeviceRegistrationModel.device_id == device_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list(self, user_id: str | None = None, is_active: bool | None = None,
                   skip: int = 0, limit: int = 100) -> list[DeviceRegistration]:
        stmt = select(DeviceRegistrationModel)
        if user_id:
            stmt = stmt.where(DeviceRegistrationModel.user_id == user_id)
        if is_active is not None:
            stmt = stmt.where(DeviceRegistrationModel.is_active == is_active)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(DeviceRegistrationModel).where(DeviceRegistrationModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: DeviceRegistrationModel) -> DeviceRegistration:
        return DeviceRegistration(
            id=model.id, user_id=model.user_id,
            organization_id=model.organization_id,
            device_id=model.device_id, platform=model.platform,
            fcm_token=model.fcm_token, app_version=model.app_version,
            os_version=model.os_version, device_model=model.device_model,
            preferences=model.preferences or {},
            public_key_der=model.public_key_der,
            public_key_kid=model.public_key_kid,
            key_valid_from=model.key_valid_from,
            key_valid_until=model.key_valid_until,
            is_active=model.is_active, last_seen_at=model.last_seen_at,
            created_at=model.created_at, updated_at=model.updated_at,
        )


class ApplicantRepository:
    """Repository for Applicant persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: Applicant) -> Applicant:
        existing = await self._session.get(ApplicantModel, entity.id)
        if existing:
            for attr in ("credential_template_id", "user_id", "external_id",
                         "given_name", "family_name", "email", "phone", "status",
                         "reviewer_id", "reviewer_lock_expires_at", "submitted_at",
                         "reviewed_at", "approved_at", "credentialed_at",
                         "rejection_reason", "rejection_code", "application_data",
                         "vetting_checks", "issued_credential_id",
                         "updated_at"):
                setattr(existing, attr, getattr(entity, attr))
            existing.extra_metadata = entity.metadata
        else:
            model = ApplicantModel(
                id=entity.id, organization_id=entity.organization_id,
                flow_id=entity.flow_id,
                credential_template_id=entity.credential_template_id,
                user_id=entity.user_id, external_id=entity.external_id,
                given_name=entity.given_name, family_name=entity.family_name,
                email=entity.email, phone=entity.phone, status=entity.status,
                reviewer_id=entity.reviewer_id,
                reviewer_lock_expires_at=entity.reviewer_lock_expires_at,
                submitted_at=entity.submitted_at,
                reviewed_at=entity.reviewed_at,
                approved_at=entity.approved_at,
                credentialed_at=entity.credentialed_at,
                rejection_reason=entity.rejection_reason,
                rejection_code=entity.rejection_code,
                application_data=entity.application_data,
                vetting_checks=entity.vetting_checks,
                issued_credential_id=entity.issued_credential_id,
                extra_metadata=entity.metadata,
                created_at=entity.created_at, updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> Applicant | None:
        model = await self._session.get(ApplicantModel, entity_id)
        return self._to_entity(model) if model else None

    async def list(self, organization_id: str, flow_id: str | None = None,
                   status: str | None = None, skip: int = 0, limit: int = 100) -> list[Applicant]:
        stmt = select(ApplicantModel).where(ApplicantModel.organization_id == organization_id)
        if flow_id:
            stmt = stmt.where(ApplicantModel.flow_id == flow_id)
        if status:
            stmt = stmt.where(ApplicantModel.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(ApplicantModel).where(ApplicantModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: ApplicantModel) -> Applicant:
        return Applicant(
            id=model.id, organization_id=model.organization_id,
            flow_id=model.flow_id,
            credential_template_id=model.credential_template_id,
            user_id=model.user_id, external_id=model.external_id,
            given_name=model.given_name, family_name=model.family_name,
            email=model.email, phone=model.phone, status=model.status,
            reviewer_id=model.reviewer_id,
            reviewer_lock_expires_at=model.reviewer_lock_expires_at,
            submitted_at=model.submitted_at, reviewed_at=model.reviewed_at,
            approved_at=model.approved_at,
            credentialed_at=model.credentialed_at,
            rejection_reason=model.rejection_reason,
            rejection_code=model.rejection_code,
            application_data=model.application_data or {},
            vetting_checks=model.vetting_checks or [],
            issued_credential_id=model.issued_credential_id,
            metadata=model.extra_metadata or {},
            created_at=model.created_at, updated_at=model.updated_at,
        )


class ReviewerLockRepository:
    """Repository for ReviewerLock persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: ReviewerLock) -> ReviewerLock:
        existing = await self._session.get(ReviewerLockModel, entity.id)
        if existing:
            for attr in ("status", "released_at"):
                setattr(existing, attr, getattr(entity, attr))
        else:
            model = ReviewerLockModel(
                id=entity.id, applicant_id=entity.applicant_id,
                organization_id=entity.organization_id,
                holder_user_id=entity.holder_user_id,
                ttl_seconds=entity.ttl_seconds,
                expires_at=entity.expires_at,
                released_at=entity.released_at,
                status=entity.status,
                created_at=entity.created_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> ReviewerLock | None:
        model = await self._session.get(ReviewerLockModel, entity_id)
        return self._to_entity(model) if model else None

    async def get_active_for_applicant(self, applicant_id: str) -> ReviewerLock | None:
        stmt = select(ReviewerLockModel).where(
            ReviewerLockModel.applicant_id == applicant_id,
            ReviewerLockModel.status == "ACTIVE",
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(ReviewerLockModel).where(ReviewerLockModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: ReviewerLockModel) -> ReviewerLock:
        return ReviewerLock(
            id=model.id, applicant_id=model.applicant_id,
            organization_id=model.organization_id,
            holder_user_id=model.holder_user_id,
            ttl_seconds=model.ttl_seconds,
            expires_at=model.expires_at,
            released_at=model.released_at,
            status=model.status,
            created_at=model.created_at,
        )


class VettingCheckRepository:
    """Repository for VettingCheck persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: VettingCheck) -> VettingCheck:
        existing = await self._session.get(VettingCheckModel, entity.id)
        if existing:
            for attr in ("status", "score", "threshold", "failure_reason",
                         "evidence_refs", "performed_by", "started_at",
                         "completed_at", "expires_at", "raw_result", "updated_at"):
                setattr(existing, attr, getattr(entity, attr))
        else:
            model = VettingCheckModel(
                id=entity.id, applicant_id=entity.applicant_id,
                organization_id=entity.organization_id,
                check_type=entity.check_type,
                provider=entity.provider,
                provider_reference_id=entity.provider_reference_id,
                status=entity.status, score=entity.score,
                threshold=entity.threshold,
                failure_reason=entity.failure_reason,
                evidence_refs=entity.evidence_refs,
                performed_by=entity.performed_by,
                started_at=entity.started_at,
                completed_at=entity.completed_at,
                expires_at=entity.expires_at,
                raw_result=entity.raw_result,
                created_at=entity.created_at, updated_at=entity.updated_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> VettingCheck | None:
        model = await self._session.get(VettingCheckModel, entity_id)
        return self._to_entity(model) if model else None

    async def list(self, applicant_id: str, status: str | None = None,
                   skip: int = 0, limit: int = 100) -> list[VettingCheck]:
        stmt = select(VettingCheckModel).where(VettingCheckModel.applicant_id == applicant_id)
        if status:
            stmt = stmt.where(VettingCheckModel.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(VettingCheckModel).where(VettingCheckModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: VettingCheckModel) -> VettingCheck:
        return VettingCheck(
            id=model.id, applicant_id=model.applicant_id,
            organization_id=model.organization_id,
            check_type=model.check_type,
            provider=model.provider,
            provider_reference_id=model.provider_reference_id,
            status=model.status, score=model.score,
            threshold=model.threshold,
            failure_reason=model.failure_reason,
            evidence_refs=model.evidence_refs or [],
            performed_by=model.performed_by,
            started_at=model.started_at,
            completed_at=model.completed_at,
            expires_at=model.expires_at,
            raw_result=model.raw_result,
            created_at=model.created_at, updated_at=model.updated_at,
        )


class BiometricEnrollmentRepository:
    """Repository for BiometricEnrollment persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: BiometricEnrollment) -> BiometricEnrollment:
        existing = await self._session.get(BiometricEnrollmentModel, entity.id)
        if existing:
            for attr in ("status", "revoked_at", "revocation_reason"):
                setattr(existing, attr, getattr(entity, attr))
        else:
            model = BiometricEnrollmentModel(
                id=entity.id, applicant_id=entity.applicant_id,
                organization_id=entity.organization_id,
                modality=entity.modality,
                template_hash=entity.template_hash,
                hash_algorithm=entity.hash_algorithm,
                provider=entity.provider,
                capture_device=entity.capture_device,
                quality_score=entity.quality_score,
                liveness_verified=entity.liveness_verified,
                status=entity.status,
                revoked_at=entity.revoked_at,
                revocation_reason=entity.revocation_reason,
                created_at=entity.created_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> BiometricEnrollment | None:
        model = await self._session.get(BiometricEnrollmentModel, entity_id)
        return self._to_entity(model) if model else None

    async def list(self, applicant_id: str, skip: int = 0, limit: int = 100) -> list[BiometricEnrollment]:
        stmt = select(BiometricEnrollmentModel).where(
            BiometricEnrollmentModel.applicant_id == applicant_id
        ).offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(BiometricEnrollmentModel).where(BiometricEnrollmentModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: BiometricEnrollmentModel) -> BiometricEnrollment:
        return BiometricEnrollment(
            id=model.id, applicant_id=model.applicant_id,
            organization_id=model.organization_id,
            modality=model.modality,
            template_hash=model.template_hash,
            hash_algorithm=model.hash_algorithm,
            provider=model.provider,
            capture_device=model.capture_device,
            quality_score=model.quality_score,
            liveness_verified=model.liveness_verified,
            status=model.status,
            revoked_at=model.revoked_at,
            revocation_reason=model.revocation_reason,
            created_at=model.created_at,
        )


class NotificationPayloadRepository:
    """Repository for NotificationPayload persistence."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, entity: NotificationPayload) -> NotificationPayload:
        existing = await self._session.get(NotificationPayloadModel, entity.id)
        if existing:
            for attr in ("title", "body", "data", "event_type", "priority",
                         "target", "ttl_seconds", "collapse_key", "correlation_id"):
                setattr(existing, attr, getattr(entity, attr))
        else:
            model = NotificationPayloadModel(
                id=entity.id, title=entity.title, body=entity.body,
                data=entity.data, event_type=entity.event_type,
                priority=entity.priority, target=entity.target,
                ttl_seconds=entity.ttl_seconds,
                collapse_key=entity.collapse_key,
                correlation_id=entity.correlation_id,
                created_at=entity.created_at,
            )
            self._session.add(model)
        await self._session.commit()
        return entity

    async def get(self, entity_id: str) -> NotificationPayload | None:
        model = await self._session.get(NotificationPayloadModel, entity_id)
        return self._to_entity(model) if model else None

    async def list(self, event_type: str | None = None,
                   skip: int = 0, limit: int = 100) -> list[NotificationPayload]:
        stmt = select(NotificationPayloadModel)
        if event_type:
            stmt = stmt.where(NotificationPayloadModel.event_type == event_type)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def delete(self, entity_id: str) -> bool:
        stmt = delete(NotificationPayloadModel).where(NotificationPayloadModel.id == entity_id)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount > 0

    def _to_entity(self, model: NotificationPayloadModel) -> NotificationPayload:
        return NotificationPayload(
            id=model.id, title=model.title, body=model.body,
            data=model.data or {}, event_type=model.event_type,
            priority=model.priority, target=model.target or {},
            ttl_seconds=model.ttl_seconds,
            collapse_key=model.collapse_key,
            correlation_id=model.correlation_id,
            created_at=model.created_at,
        )
