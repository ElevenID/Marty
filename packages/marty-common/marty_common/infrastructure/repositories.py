"""Database repositories used by services."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from .models import (
    CertificateRecord,
    CredentialEventLog,
    CredentialLedgerEntry,
    DigitalTravelCredentialRecord,
    MobileDrivingLicenseRecord,
    Oidc4VciSessionRecord,
    PassportRecord,
    SdJwtCredentialRecord,
    TrustEntity,
)


class TrustEntityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, entity_id: str) -> TrustEntity | None:
        stmt = select(TrustEntity).where(TrustEntity.entity_id == entity_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def upsert(
        self, entity_id: str, trusted: bool, attributes: dict[str, Any] | None = None
    ) -> TrustEntity:
        record = await self.get(entity_id)
        if record is None:
            record = TrustEntity(
                entity_id=entity_id, trusted=trusted, attributes=attributes or {}, version=1
            )
            self._session.add(record)
        else:
            record.trusted = trusted
            record.attributes = attributes or record.attributes
            record.version += 1
        return record

    async def list_trusted(self) -> list[TrustEntity]:
        stmt = select(TrustEntity).where(TrustEntity.trusted.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class CertificateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        cert_id: str,
        cert_type: str,
        pem: str,
        issuer: str | None = None,
        subject: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> CertificateRecord:
        stmt = select(CertificateRecord).where(CertificateRecord.certificate_id == cert_id)
        result = await self._session.execute(stmt)
        record = result.scalars().first()
        if record is None:
            record = CertificateRecord(
                certificate_id=cert_id,
                certificate_type=cert_type,
                issuer=issuer,
                subject=subject,
                pem=pem,
                details=details,
            )
            self._session.add(record)
        else:
            record.pem = pem
            record.issuer = issuer  # type: ignore[assignment]
            record.subject = subject  # type: ignore[assignment]
            record.details = details or record.details
            record.updated_at = datetime.now(timezone.utc)
        return record

    async def get(self, cert_id: str) -> CertificateRecord | None:
        stmt = select(CertificateRecord).where(CertificateRecord.certificate_id == cert_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_all(self) -> list[CertificateRecord]:
        result = await self._session.execute(select(CertificateRecord))
        return list(result.scalars().all())

    async def mark_revoked(self, cert_id: str, reason: str | None, revoked_at: datetime) -> None:
        current_details: dict[str, Any] | None = None
        existing = await self.get(cert_id)
        if existing is not None:
            current_details = existing.details or {}
        if current_details is None:
            current_details = {}
        current_details.update(
            {
                "revocation_reason": reason,
                "revocation_date": revoked_at.isoformat(),
            }
        )
        stmt = (
            update(CertificateRecord)
            .where(CertificateRecord.certificate_id == cert_id)
            .values(revoked=True, updated_at=revoked_at, details=current_details)
        )
        await self._session.execute(stmt)

    async def list_by_type(self, cert_type: str) -> list[CertificateRecord]:
        stmt = select(CertificateRecord).where(CertificateRecord.certificate_type == cert_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class DigitalTravelCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        dtc_id: str,
        passport_number: str,
        dtc_type: str,
        access_control: str,
        details: dict[str, Any],
        payload_location: str,
        signature: bytes | None,
    ) -> DigitalTravelCredentialRecord:
        record = DigitalTravelCredentialRecord(
            dtc_id=dtc_id,
            passport_number=passport_number,
            dtc_type=dtc_type,
            access_control=access_control,
            details=details,
            payload_location=payload_location,
            signature=signature,
        )
        self._session.add(record)
        return record

    async def get(self, dtc_id: str) -> DigitalTravelCredentialRecord | None:
        stmt = select(DigitalTravelCredentialRecord).where(
            DigitalTravelCredentialRecord.dtc_id == dtc_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def mark_revoked(self, dtc_id: str, reason: str | None = None) -> None:
        stmt = (
            update(DigitalTravelCredentialRecord)
            .where(DigitalTravelCredentialRecord.dtc_id == dtc_id)
            .values(
                status="REVOKED", revoked_at=datetime.now(timezone.utc), revocation_reason=reason
            )
        )
        await self._session.execute(stmt)


class PassportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        passport_number: str,
        payload_location: str,
        status: str,
        details: dict[str, Any] | None,
        signature: bytes | None,
    ) -> PassportRecord:
        record = await self.get(passport_number)
        if record is None:
            record = PassportRecord(
                passport_number=passport_number,
                payload_location=payload_location,
                status=status,
                details=details,
                signature=signature,
            )
            self._session.add(record)
            return record

        record.payload_location = payload_location
        record.status = status
        record.signature = signature
        if details is not None:
            record.details = details
            flag_modified(record, "details")
        record.updated_at = datetime.now(timezone.utc)
        return record

    async def get(self, passport_number: str) -> PassportRecord | None:
        stmt = select(PassportRecord).where(PassportRecord.passport_number == passport_number)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def update_status(self, passport_number: str, status: str) -> None:
        stmt = (
            update(PassportRecord)
            .where(PassportRecord.passport_number == passport_number)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        await self._session.execute(stmt)

    async def update_signature(
        self,
        passport_number: str,
        signature: bytes,
        signature_info: dict[str, Any] | None = None,
    ) -> None:
        record = await self.get(passport_number)
        if record is None:
            return
        record.signature = signature
        if signature_info is not None:
            details = record.details or {}
            info = details.get("signature_info", {})
            info.update(signature_info)
            details["signature_info"] = info
            record.details = details
            flag_modified(record, "details")
        record.updated_at = datetime.now(timezone.utc)


class MobileDrivingLicenseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        mdl_id: str,
        license_number: str,
        user_id: str,
        status: str,
        details: dict[str, Any],
        payload_location: str,
        disclosure_policies: dict[str, Any] | None,
    ) -> MobileDrivingLicenseRecord:
        record = MobileDrivingLicenseRecord(
            mdl_id=mdl_id,
            license_number=license_number,
            user_id=user_id,
            status=status,
            details=details,
            payload_location=payload_location,
            disclosure_policies=disclosure_policies,
        )
        self._session.add(record)
        return record

    async def get(self, mdl_id: str) -> MobileDrivingLicenseRecord | None:
        stmt = select(MobileDrivingLicenseRecord).where(MobileDrivingLicenseRecord.mdl_id == mdl_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_license(self, license_number: str) -> MobileDrivingLicenseRecord | None:
        stmt = select(MobileDrivingLicenseRecord).where(
            MobileDrivingLicenseRecord.license_number == license_number
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def update_status(self, mdl_id: str, status: str) -> None:
        stmt = (
            update(MobileDrivingLicenseRecord)
            .where(MobileDrivingLicenseRecord.mdl_id == mdl_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        await self._session.execute(stmt)


class CredentialLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, mdl_id: str) -> MobileDrivingLicenseRecord | None:
        """Get MDL record by ID."""
        stmt = select(MobileDrivingLicenseRecord).where(MobileDrivingLicenseRecord.mdl_id == mdl_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def record_event(
        self,
        *,
        topic: str,
        payload: dict[str, Any],
        key: str | None,
        partition: int | None,
        offset: int | None,
    ) -> CredentialEventLog:
        event = CredentialEventLog(
            topic=topic,
            key=key,
            payload=payload,
            partition=partition,
            offset=offset,
        )
        self._session.add(event)
        return event

    async def upsert_entry(
        self,
        *,
        credential_id: str,
        credential_type: str,
        status: str,
        metadata: dict[str, Any] | None,
        topic: str,
        offset: int | None,
    ) -> CredentialLedgerEntry:
        stmt = select(CredentialLedgerEntry).where(
            CredentialLedgerEntry.credential_id == credential_id
        )
        result = await self._session.execute(stmt)
        entry = result.scalars().first()
        now = datetime.now(timezone.utc)
        if entry is None:
            entry = CredentialLedgerEntry(
                credential_id=credential_id,
                credential_type=credential_type,
                status=status,
                event_metadata=metadata or {},
                last_event_topic=topic,
                last_event_offset=offset,
                updated_at=now,
            )
            self._session.add(entry)
            return entry

        entry.credential_type = credential_type or entry.credential_type
        entry.status = status
        if metadata:
            current = entry.event_metadata or {}
            current.update(metadata)
            entry.event_metadata = current
            flag_modified(entry, "event_metadata")
        entry.last_event_topic = topic
        entry.last_event_offset = offset
        entry.updated_at = now
        return entry

    async def update_status(
        self,
        credential_id: str,
        status: str,
        metadata: dict[str, Any] | None,
        topic: str,
        offset: int | None,
    ) -> CredentialLedgerEntry:
        return await self.upsert_entry(
            credential_id=credential_id,
            credential_type="",
            status=status,
            metadata=metadata,
            topic=topic,
            offset=offset,
        )

    async def update_signature(
        self,
        mdl_id: str,
        signature: bytes,
        signature_info: dict[str, Any],
    ) -> None:
        record = await self.get(mdl_id)
        if record is None:
            return
        record.signature = signature
        details = record.details or {}
        details["signature_info"] = signature_info
        record.details = details
        flag_modified(record, "details")
        record.updated_at = datetime.now(timezone.utc)

    async def set_disclosure_policies(
        self, mdl_id: str, disclosure_policies: dict[str, Any] | None
    ) -> None:
        record = await self.get(mdl_id)
        if record is None:
            return
        record.disclosure_policies = disclosure_policies
        flag_modified(record, "disclosure_policies")
        record.updated_at = datetime.now(timezone.utc)

    async def mark_revoked(self, mdl_id: str, reason: str | None = None) -> None:
        stmt = (
            update(MobileDrivingLicenseRecord)
            .where(MobileDrivingLicenseRecord.mdl_id == mdl_id)
            .values(
                status="REVOKED",
                revoked_at=datetime.now(timezone.utc),
                revocation_reason=reason,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)


def _token_digest(value: str) -> str:
    """Return a stable SHA-256 hexadecimal digest for sensitive tokens."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SdJwtCredentialRepository:
    """Persistence helpers for SD-JWT verifiable credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        credential_id: str,
        subject_id: str,
        credential_type: str,
        issuer: str,
        audience: str | None,
        sd_jwt_location: str,
        disclosures_location: str,
        expires_at: datetime | None,
        metadata: dict[str, Any] | None,
        wallet_attestation: dict[str, Any] | None,
    ) -> SdJwtCredentialRecord:
        record = SdJwtCredentialRecord(
            credential_id=credential_id,
            subject_id=subject_id,
            credential_type=credential_type,
            issuer=issuer,
            audience=audience,
            sd_jwt_location=sd_jwt_location,
            disclosures_location=disclosures_location,
            expires_at=expires_at,
            metadata=metadata,
            wallet_attestation=wallet_attestation,
        )
        self._session.add(record)
        return record

    async def get(self, credential_id: str) -> SdJwtCredentialRecord | None:
        stmt = select(SdJwtCredentialRecord).where(
            SdJwtCredentialRecord.credential_id == credential_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def update_status(
        self,
        credential_id: str,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        stmt = (
            update(SdJwtCredentialRecord)
            .where(SdJwtCredentialRecord.credential_id == credential_id)
            .values(
                status=status,
                metadata=metadata,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)


class OidcSessionRepository:
    """State store for OIDC4VCI issuance sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_offer(
        self,
        *,
        offer_id: str,
        subject_id: str,
        credential_type: str,
        base_claims: dict[str, Any],
        selective_disclosures: dict[str, Any],
        offer_payload: dict[str, Any],
        pre_authorized_code: str,
        expires_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> Oidc4VciSessionRecord:
        metadata_payload = dict(metadata or {})
        internal_details = dict(metadata_payload.get("_internal", {}))
        internal_details["pre_authorized_code"] = pre_authorized_code
        metadata_payload["_internal"] = internal_details

        record = Oidc4VciSessionRecord(
            offer_id=offer_id,
            subject_id=subject_id,
            credential_type=credential_type,
            base_claims=base_claims,
            selective_disclosures=selective_disclosures,
            offer_payload=offer_payload,
            pre_authorized_code_hash=_token_digest(pre_authorized_code),
            pre_authorized_code_expires_at=expires_at,
            metadata=metadata_payload,
        )
        self._session.add(record)
        return record

    async def get_by_offer_id(self, offer_id: str) -> Oidc4VciSessionRecord | None:
        stmt = select(Oidc4VciSessionRecord).where(Oidc4VciSessionRecord.offer_id == offer_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_pre_authorized_code(
        self, pre_authorized_code: str
    ) -> Oidc4VciSessionRecord | None:
        digest = _token_digest(pre_authorized_code)
        stmt = select(Oidc4VciSessionRecord).where(
            Oidc4VciSessionRecord.pre_authorized_code_hash == digest
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def attach_access_token(
        self,
        session_record: Oidc4VciSessionRecord,
        *,
        access_token: str,
        expires_at: datetime,
        nonce: str,
        wallet_attestation: dict[str, Any] | None,
    ) -> None:
        session_record.access_token_hash = _token_digest(access_token)
        session_record.access_token_expires_at = expires_at
        session_record.nonce = nonce
        session_record.wallet_attestation = wallet_attestation
        session_record.status = "TOKEN_ISSUED"
        if session_record.extra_metadata is not None:
            metadata_payload = dict(session_record.extra_metadata)
            internal_details = dict(metadata_payload.get("_internal", {}))
            if internal_details.pop("pre_authorized_code", None) is not None:
                metadata_payload["_internal"] = internal_details
                session_record.extra_metadata = metadata_payload
                flag_modified(session_record, "extra_metadata")
        session_record.updated_at = datetime.now(timezone.utc)

    async def get_by_access_token(self, access_token: str) -> Oidc4VciSessionRecord | None:
        digest = _token_digest(access_token)
        stmt = select(Oidc4VciSessionRecord).where(
            Oidc4VciSessionRecord.access_token_hash == digest
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def mark_issued(self, session_record: Oidc4VciSessionRecord) -> None:
        session_record.status = "VC_ISSUED"
        session_record.updated_at = datetime.now(timezone.utc)
