"""
Repository Implementations for Digital Identity

PostgreSQL repositories using SQLAlchemy async patterns.
Implements the repository port interfaces from the application layer.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import timedelta
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
    NetworkMode,
    KeyAccessMode,
    UXConfig,
    UpdatePolicy,
    FlowType,
    FlowStatus,
    ApprovalStrategy,
    StatusListEntryRef,
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
            existing.profile_type = entity.profile_type.value
            existing.enabled = entity.enabled
            existing.trust_sources = entity.trust_sources
            existing.allowed_algorithms = [a.value for a in entity.allowed_algorithms]
            existing.allowed_formats = [f.value for f in entity.allowed_formats]
            existing.revocation_policy = self._serialize_revocation_policy(entity.revocation_policy)
            existing.time_policy = self._serialize_time_policy(entity.time_policy)
            existing.allowed_issuers = entity.allowed_issuers
            existing.denied_issuers = entity.denied_issuers
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
                profile_type=entity.profile_type.value,
                enabled=entity.enabled,
                trust_sources=entity.trust_sources,
                allowed_algorithms=[a.value for a in entity.allowed_algorithms],
                allowed_formats=[f.value for f in entity.allowed_formats],
                revocation_policy=self._serialize_revocation_policy(entity.revocation_policy),
                time_policy=self._serialize_time_policy(entity.time_policy),
                allowed_issuers=entity.allowed_issuers,
                denied_issuers=entity.denied_issuers,
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
            profile_type=TrustProfileType(model.profile_type),
            enabled=model.enabled,
            trust_sources=model.trust_sources,
            allowed_algorithms=[CryptoAlgorithm(a) for a in model.allowed_algorithms],
            allowed_formats=[CredentialFormat(f) for f in model.allowed_formats],
            revocation_policy=self._deserialize_revocation_policy(model.revocation_policy),
            time_policy=self._deserialize_time_policy(model.time_policy),
            allowed_issuers=model.allowed_issuers,
            denied_issuers=model.denied_issuers,
            metadata=model.metadata_,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )
    
    def _serialize_revocation_policy(self, policy: RevocationPolicy) -> dict[str, Any]:
        """Serialize revocation policy to dict."""
        return {
            "mode": policy.mode.value,
            "check_ocsp": policy.check_ocsp,
            "check_crl": policy.check_crl,
            "check_status_list": policy.check_status_list,
            "offline_grace_period_seconds": policy.offline_grace_period.total_seconds(),
            "cache_ttl_seconds": policy.cache_ttl.total_seconds(),
        }
    
    def _deserialize_revocation_policy(self, data: dict[str, Any]) -> RevocationPolicy:
        """Deserialize revocation policy from dict."""
        from digital_identity.domain.value_objects import RevocationCheckMode
        return RevocationPolicy(
            mode=RevocationCheckMode(data.get("mode", "hard_fail")),
            check_ocsp=data.get("check_ocsp", True),
            check_crl=data.get("check_crl", True),
            check_status_list=data.get("check_status_list", True),
            offline_grace_period=timedelta(seconds=data.get("offline_grace_period_seconds", 86400)),
            cache_ttl=timedelta(seconds=data.get("cache_ttl_seconds", 3600)),
        )
    
    def _serialize_time_policy(self, policy: TimePolicy) -> dict[str, Any]:
        """Serialize time policy to dict."""
        return {
            "clock_skew_tolerance_seconds": policy.clock_skew_tolerance.total_seconds(),
            "max_credential_age_seconds": policy.max_credential_age.total_seconds() if policy.max_credential_age else None,
            "require_not_before": policy.require_not_before,
            "require_not_after": policy.require_not_after,
        }
    
    def _deserialize_time_policy(self, data: dict[str, Any]) -> TimePolicy:
        """Deserialize time policy from dict."""
        max_age = data.get("max_credential_age_seconds")
        return TimePolicy(
            clock_skew_tolerance=timedelta(seconds=data.get("clock_skew_tolerance_seconds", 300)),
            max_credential_age=timedelta(seconds=max_age) if max_age else None,
            require_not_before=data.get("require_not_before", True),
            require_not_after=data.get("require_not_after", True),
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
            existing.trust_profile_id = entity.trust_profile_id
            existing.format = entity.format.value
            existing.namespace = entity.namespace
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
                trust_profile_id=entity.trust_profile_id,
                format=entity.format.value,
                namespace=entity.namespace,
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
            claims=[self._deserialize_claim(c) for c in model.claims],
            validity_rules=self._deserialize_validity_rules(model.validity_rules),
            issuer_key_ids=model.issuer_key_ids,
            trust_profile_id=model.trust_profile_id,
            format=CredentialFormat(model.format),
            namespace=model.namespace,
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
            "data_type": claim.data_type,
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
            display_name=data["display_name"],
            data_type=data["data_type"],
            required=data.get("required", True),
            selectively_disclosable=data.get("selectively_disclosable", True),
            derived_from=data.get("derived_from"),
            predicate_type=data.get("predicate_type"),
            predicate_value=data.get("predicate_value"),
            validation_regex=data.get("validation_regex"),
            description=data.get("description"),
        )
    
    def _serialize_validity_rules(self, rules: ValidityRules) -> dict[str, Any]:
        """Serialize validity rules to dict."""
        return {
            "default_ttl_seconds": rules.default_ttl.total_seconds(),
            "max_ttl_seconds": rules.max_ttl.total_seconds() if rules.max_ttl else None,
            "min_ttl_seconds": rules.min_ttl.total_seconds(),
            "allow_reissue": rules.allow_reissue,
            "reissue_before_expiry_seconds": rules.reissue_before_expiry.total_seconds(),
        }
    
    def _deserialize_validity_rules(self, data: dict[str, Any]) -> ValidityRules:
        """Deserialize validity rules from dict."""
        max_ttl = data.get("max_ttl_seconds")
        return ValidityRules(
            default_ttl=timedelta(seconds=data.get("default_ttl_seconds", 31536000)),
            max_ttl=timedelta(seconds=max_ttl) if max_ttl else None,
            min_ttl=timedelta(seconds=data.get("min_ttl_seconds", 3600)),
            allow_reissue=data.get("allow_reissue", True),
            reissue_before_expiry=timedelta(seconds=data.get("reissue_before_expiry_seconds", 2592000)),
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
            existing.accepted_credential_types = entity.accepted_credential_types
            existing.required_claims = claims_data
            existing.holder_binding = entity.holder_binding.value
            existing.trust_profile_id = entity.trust_profile_id
            existing.freshness_requirements = freshness_data
            existing.prefer_predicates = entity.prefer_predicates
            existing.single_presentation = entity.single_presentation
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = PresentationPolicyModel(
                id=entity.id,
                name=entity.name,
                description=entity.description,
                purpose=entity.purpose,
                accepted_credential_types=entity.accepted_credential_types,
                required_claims=claims_data,
                holder_binding=entity.holder_binding.value,
                trust_profile_id=entity.trust_profile_id,
                freshness_requirements=freshness_data,
                prefer_predicates=entity.prefer_predicates,
                single_presentation=entity.single_presentation,
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
            accepted_credential_types=model.accepted_credential_types,
            required_claims=[self._deserialize_required_claim(c) for c in model.required_claims],
            holder_binding=HolderBindingMethod(model.holder_binding),
            trust_profile_id=model.trust_profile_id,
            freshness_requirements=self._deserialize_freshness(model.freshness_requirements),
            prefer_predicates=model.prefer_predicates,
            single_presentation=model.single_presentation,
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
            "required_value": claim.required_value,
        }
    
    def _deserialize_required_claim(self, data: dict[str, Any]) -> RequiredClaim:
        """Deserialize required claim from dict."""
        return RequiredClaim(
            claim_name=data["claim_name"],
            credential_type=data["credential_type"],
            accept_predicate=data.get("accept_predicate", True),
            required_value=data.get("required_value"),
        )
    
    def _serialize_freshness(self, req: FreshnessRequirements) -> dict[str, Any]:
        """Serialize freshness requirements to dict."""
        return {
            "max_credential_age_seconds": req.max_credential_age.total_seconds() if req.max_credential_age else None,
            "max_proof_age_seconds": req.max_proof_age.total_seconds(),
            "require_live_revocation_check": req.require_live_revocation_check,
        }
    
    def _deserialize_freshness(self, data: dict[str, Any]) -> FreshnessRequirements:
        """Deserialize freshness requirements from dict."""
        max_age = data.get("max_credential_age_seconds")
        return FreshnessRequirements(
            max_credential_age=timedelta(seconds=max_age) if max_age else None,
            max_proof_age=timedelta(seconds=data.get("max_proof_age_seconds", 300)),
            require_live_revocation_check=data.get("require_live_revocation_check", True),
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
            existing.biometric_required = entity.biometric_required
            existing.audit_all_events = entity.audit_all_events
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
                biometric_required=entity.biometric_required,
                audit_all_events=entity.audit_all_events,
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
            biometric_required=model.biometric_required,
            audit_all_events=model.audit_all_events,
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
            "show_operator_mode": config.show_operator_mode,
            "accessibility_enabled": config.accessibility_enabled,
            "custom_branding": config.custom_branding,
        }
    
    def _deserialize_ux_config(self, data: dict[str, Any]) -> UXConfig:
        """Deserialize UX config from dict."""
        return UXConfig(
            language=data.get("language", "en"),
            theme=data.get("theme", "default"),
            show_operator_mode=data.get("show_operator_mode", False),
            accessibility_enabled=data.get("accessibility_enabled", True),
            custom_branding=data.get("custom_branding", {}),
        )
    
    def _serialize_update_policy(self, policy: UpdatePolicy) -> dict[str, Any]:
        """Serialize update policy to dict."""
        return {
            "auto_update": policy.auto_update,
            "update_channel": policy.update_channel,
            "rollout_percentage": policy.rollout_percentage,
            "version_pinned": policy.version_pinned,
        }
    
    def _deserialize_update_policy(self, data: dict[str, Any]) -> UpdatePolicy:
        """Deserialize update policy from dict."""
        return UpdatePolicy(
            auto_update=data.get("auto_update", True),
            update_channel=data.get("update_channel", "stable"),
            rollout_percentage=data.get("rollout_percentage", 100),
            version_pinned=data.get("version_pinned"),
        )


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
            existing.presentation_policy_id = entity.presentation_policy_id
            existing.deployment_profile_ids = entity.deployment_profile_ids
            existing.approval_strategy = entity.approval_strategy.value
            existing.enabled = entity.enabled
            existing.hooks = entity.hooks
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
                presentation_policy_id=entity.presentation_policy_id,
                deployment_profile_ids=entity.deployment_profile_ids,
                approval_strategy=entity.approval_strategy.value,
                enabled=entity.enabled,
                hooks=entity.hooks,
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
            presentation_policy_id=model.presentation_policy_id,
            deployment_profile_ids=model.deployment_profile_ids,
            approval_strategy=ApprovalStrategy(model.approval_strategy),
            enabled=model.enabled,
            hooks=model.hooks,
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
            existing.status = entity.status.value
            existing.current_step = entity.current_step
            existing.current_step_index = entity.current_step_index
            existing.step_results = entity.step_results
            existing.context_data = entity.context_data
            existing.issued_credential_id = entity.issued_credential_id
            existing.started_at = entity.started_at
            existing.completed_at = entity.completed_at
            existing.error = entity.error
            existing.metadata_ = entity.metadata
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = FlowExecutionModel(
                id=entity.id,
                flow_id=entity.flow_id,
                status=entity.status.value,
                current_step=entity.current_step,
                current_step_index=entity.current_step_index,
                step_results=entity.step_results,
                context_data=entity.context_data,
                issued_credential_id=entity.issued_credential_id,
                started_at=entity.started_at,
                completed_at=entity.completed_at,
                error=entity.error,
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
            status=FlowStatus(model.status),
            current_step=model.current_step,
            current_step_index=model.current_step_index,
            step_results=model.step_results,
            context_data=model.context_data,
            issued_credential_id=model.issued_credential_id,
            started_at=model.started_at,
            completed_at=model.completed_at,
            error=model.error,
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
            existing.credential_count = entity.credential_count
            existing.credential_ids = entity.credential_ids
            existing.status = entity.status
            existing.scheduled_for = entity.scheduled_for
            existing.completed_at = entity.completed_at
            existing.revocation_interval = entity.revocation_interval
            existing.error_message = entity.error_message
            existing.updated_at = entity.updated_at
            existing.version = entity.version
        else:
            model = RevocationBatchModel(
                id=entity.id,
                organization_id=entity.organization_id,
                credential_template_id=entity.credential_template_id,
                credential_count=entity.credential_count,
                credential_ids=entity.credential_ids,
                status=entity.status,
                scheduled_for=entity.scheduled_for,
                completed_at=entity.completed_at,
                revocation_interval=entity.revocation_interval,
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
            RevocationBatchModel.status == "queued"
        )
        if scheduled_before:
            stmt = stmt.where(RevocationBatchModel.scheduled_for <= scheduled_before)
        
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
            credential_count=model.credential_count,
            credential_ids=model.credential_ids,
            status=model.status,
            scheduled_for=model.scheduled_for,
            completed_at=model.completed_at,
            revocation_interval=model.revocation_interval,
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )
