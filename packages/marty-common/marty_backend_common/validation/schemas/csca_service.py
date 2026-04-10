"""Pydantic request schemas for the CSCA Service RPC surface."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateCertificateRequestSchema(BaseModel):
    """Validation schema for CreateCertificate RPC."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    subject_name: str = Field(alias="subject_name")
    validity_days: int = Field(alias="validity_days", ge=1, le=3650)  # 1 day to 10 years
    key_algorithm: str = Field(alias="key_algorithm")
    key_size: int = Field(alias="key_size")
    extensions: dict[str, str] = Field(alias="extensions", default_factory=dict)

    @field_validator("subject_name")
    @classmethod
    def _validate_subject_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            msg = "subject_name is required"
            raise ValueError(msg)
        if len(value) > 255:
            msg = "subject_name must be 255 characters or less"
            raise ValueError(msg)
        return value

    @field_validator("key_algorithm")
    @classmethod
    def _validate_key_algorithm(cls, value: str) -> str:
        allowed_algorithms = {"RSA", "ECDSA"}
        if value.upper() not in allowed_algorithms:
            msg = f"key_algorithm must be one of: {', '.join(allowed_algorithms)}"
            raise ValueError(msg)
        return value.upper()

    @field_validator("key_size")
    @classmethod
    def _validate_key_size(cls, value: int, info) -> int:
        algorithm = info.data.get("key_algorithm")
        if algorithm == "RSA":
            allowed_sizes = {2048, 3072, 4096}
        elif algorithm == "ECDSA":
            allowed_sizes = {256, 384, 521}
        else:
            # Allow any size if algorithm not yet validated
            return value

        if value not in allowed_sizes:
            msg = f"key_size {value} not allowed for {algorithm}"
            raise ValueError(msg)
        return value


class RenewCertificateRequestSchema(BaseModel):
    """Validation schema for RenewCertificate RPC."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    certificate_id: str = Field(alias="certificate_id")
    validity_days: int = Field(alias="validity_days", ge=1, le=3650)
    reuse_key: bool = Field(alias="reuse_key", default=False)

    @field_validator("certificate_id")
    @classmethod
    def _validate_certificate_id(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            msg = "certificate_id is required"
            raise ValueError(msg)
        return value


class RevokeCertificateRequestSchema(BaseModel):
    """Validation schema for RevokeCertificate RPC."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    certificate_id: str = Field(alias="certificate_id")
    reason: str = Field(alias="reason", default="UNSPECIFIED")

    @field_validator("certificate_id")
    @classmethod
    def _validate_certificate_id(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            msg = "certificate_id is required"
            raise ValueError(msg)
        return value

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        allowed_reasons = {
            "UNSPECIFIED",
            "KEY_COMPROMISE",
            "CA_COMPROMISE",
            "AFFILIATION_CHANGED",
            "SUPERSEDED",
            "CESSATION_OF_OPERATION",
            "CERTIFICATE_HOLD",
            "REMOVE_FROM_CRL",
            "PRIVILEGE_WITHDRAWN",
            "AA_COMPROMISE",
        }
        if value.upper() not in allowed_reasons:
            msg = f"reason must be one of: {', '.join(allowed_reasons)}"
            raise ValueError(msg)
        return value.upper()


class CertificateStatusRequestSchema(BaseModel):
    """Validation schema for GetCertificateStatus RPC."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    certificate_id: str = Field(alias="certificate_id")

    @field_validator("certificate_id")
    @classmethod
    def _validate_certificate_id(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            msg = "certificate_id is required"
            raise ValueError(msg)
        return value


class ListCertificatesRequestSchema(BaseModel):
    """Validation schema for ListCertificates RPC."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    status_filter: str | None = Field(alias="status_filter", default=None)
    subject_filter: str | None = Field(alias="subject_filter", default=None)

    @field_validator("status_filter")
    @classmethod
    def _validate_status_filter(cls, value: str | None) -> str | None:
        if value is None:
            return value
        allowed_statuses = {"VALID", "EXPIRED", "REVOKED"}
        if value.upper() not in allowed_statuses:
            msg = f"status_filter must be one of: {', '.join(allowed_statuses)}"
            raise ValueError(msg)
        return value.upper()


class CheckExpiringCertificatesRequestSchema(BaseModel):
    """Validation schema for CheckExpiringCertificates RPC."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    days_threshold: int = Field(alias="days_threshold", ge=1, le=365)

    @field_validator("days_threshold")
    @classmethod
    def _validate_days_threshold(cls, value: int) -> int:
        if value < 1 or value > 365:
            msg = "days_threshold must be between 1 and 365 days"
            raise ValueError(msg)
        return value
