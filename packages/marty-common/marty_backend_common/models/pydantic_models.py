"""
Pydantic models for Marty services.

These models leverage Pydantic for automatic validation and serialization/deserialization.
They complement the existing dataclass models but provide additional type safety and validation.
"""

from __future__ import annotations

import base64
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class Gender(str, Enum):
    """Passport gender enum according to ICAO standards."""

    MALE = "M"
    FEMALE = "F"
    UNSPECIFIED = "X"


class SecurityFeature(str, Enum):
    """Security feature types available in passports."""

    DIGITAL_SIGNATURE = "DIGITAL_SIGNATURE"
    WATERMARK = "WATERMARK"
    HOLOGRAM = "HOLOGRAM"
    MICRO_TEXT = "MICRO_TEXT"
    UV_FEATURES = "UV_FEATURES"
    IR_FEATURES = "IR_FEATURES"


class DataGroupType(str, Enum):
    """Data Group types as defined in ICAO Doc 9303."""

    DG1 = "DG1"  # Machine Readable Zone (MRZ)
    DG2 = "DG2"  # Encoded Facial Image
    DG3 = "DG3"  # Encoded Fingerprint(s)
    DG4 = "DG4"  # Encoded Iris(es)
    DG5 = "DG5"  # Displayed Portrait
    DG6 = "DG6"  # Reserved for future use
    DG7 = "DG7"  # Displayed Signature
    DG8 = "DG8"  # Data Features
    DG9 = "DG9"  # Structure Features
    DG10 = "DG10"  # Substance Features
    DG11 = "DG11"  # Additional Personal Details
    DG12 = "DG12"  # Additional Document Details
    DG13 = "DG13"  # Optional Details
    DG14 = "DG14"  # Security Options
    DG15 = "DG15"  # Active Authentication Public Key Info
    DG16 = "DG16"  # Person(s) to Notify
    SOD = "SOD"  # Document Security Object


class MRZDataModel(BaseModel):
    """Pydantic model for Machine Readable Zone (MRZ) data."""

    document_type: str = Field(default="P", description="Document type (P for passport)")
    issuing_country: str = Field(description="3-letter country code of issuing country")
    document_number: str = Field(description="Passport document number")
    surname: str = Field(description="Surname/last name")
    given_names: str = Field(description="Given names/first name(s)")
    nationality: str = Field(description="3-letter nationality code")
    date_of_birth: str = Field(pattern=r"^\d{6}$", description="Date of birth in YYMMDD format")
    gender: Gender = Field(description="Gender as per ICAO standards")
    date_of_expiry: str = Field(pattern=r"^\d{6}$", description="Date of expiry in YYMMDD format")
    personal_number: str | None = Field(None, description="Optional personal number")

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("date_of_birth", "date_of_expiry")
    @classmethod
    def validate_date_format(cls, v):
        """Validate YYMMDD date format."""
        if len(v) != 6:
            msg = "Date must be in YYMMDD format"
            raise ValueError(msg)

        try:
            int(v[0:2])
            mm = int(v[2:4])
            dd = int(v[4:6])

            # Basic validation of month and day
            if mm < 1 or mm > 12:
                msg = "Invalid month"
                raise ValueError(msg)

            if dd < 1 or dd > 31:
                msg = "Invalid day"
                raise ValueError(msg)

        except ValueError:
            msg = "Date must contain only digits in YYMMDD format"
            raise ValueError(msg)

        return v

    def generate_mrz_string(self) -> str:
        """Generate TD3 MRZ string compliant with ICAO Doc 9303."""
        from marty_plugin.common.utils.mrz_utils import MRZFormatter

        return MRZFormatter.generate_td3_mrz(self)  # type: ignore[arg-type]


class DataGroupModel(BaseModel):
    """Pydantic model for a data group in the Logical Data Structure (LDS)."""

    type: DataGroupType
    data: Any

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


class SignedObjectModel(BaseModel):
    """Pydantic model for Document Security Object (SOD) containing digital signatures."""

    signature: str = Field(description="Base64 encoded signature")
    timestamp: int = Field(description="Unix timestamp")
    algorithm: str = Field(default="SHA256withRSA", description="Signature algorithm")

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    def to_string(self) -> str:
        """Convert SOD to string format as used in passport files."""
        return f"{self.signature}.{self.timestamp}"

    @classmethod
    def from_string(cls, sod_string: str) -> SignedObjectModel:
        """Create SOD from string format."""
        parts = sod_string.split(".")
        if len(parts) != 2:
            msg = "Invalid SOD format"
            raise ValueError(msg)

        return cls(signature=parts[0], timestamp=int(parts[1]))


class PassportDataModel(BaseModel):
    """Pydantic model for basic passport data."""

    document_number: str = Field(description="Document number")
    issuing_country: str = Field(description="3-letter country code of issuing country")
    surname: str = Field(description="Surname/last name")
    given_names: str = Field(description="Given names/first name(s)")
    nationality: str = Field(description="3-letter nationality code")
    date_of_birth: date = Field(description="Date of birth")
    gender: Gender = Field(description="Gender as per ICAO standards")
    date_of_expiry: date = Field(description="Date of expiry")
    personal_number: str | None = Field(None, description="Optional personal number")
    photo: str | None = Field(None, description="Base64 encoded JPEG photo")

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
        "json_encoders": {
            bytes: lambda v: base64.b64encode(v).decode("utf-8"),
            date: lambda v: v.isoformat(),
        },
    }

    def to_mrz_data(self) -> MRZDataModel:
        """Convert passport data to MRZ format."""
        return MRZDataModel(
            document_type="P",
            issuing_country=self.issuing_country,
            document_number=self.document_number,
            surname=self.surname,
            given_names=self.given_names,
            nationality=self.nationality,
            date_of_birth=self.date_of_birth.strftime("%y%m%d"),
            gender=self.gender,
            date_of_expiry=self.date_of_expiry.strftime("%y%m%d"),
            personal_number=self.personal_number,
        )


class ICaoPassportModel(BaseModel):
    """Pydantic model for ICAO Doc 9303 compliant passport data."""

    passport_number: str = Field(description="Document number")
    issue_date: str = Field(description="ISO format date string")
    expiry_date: str = Field(description="ISO format date string")
    data_groups: dict[str, str] = Field(description="Data groups keyed by type")
    sod: str = Field(description="Signed Object Document as string")

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


class PassportModel(BaseModel):
    """Pydantic model for complete passport including security data."""

    id: UUID = Field(default_factory=uuid4, description="Unique passport identifier")
    passport_data: PassportDataModel = Field(description="Basic passport data")
    mrz: str | None = Field(None, description="Machine Readable Zone data")
    security_object: str | None = Field(None, description="Document Security Object")
    chip_content: str | None = Field(None, description="Base64 encoded binary chip data")
    data_groups: dict[str, DataGroupModel] = Field(
        default_factory=dict, description="Passport data groups"
    )

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    def to_icao_format(self) -> ICaoPassportModel:
        """Convert to ICAO Doc 9303 format passport."""
        # Generate data groups if not already present
        dgs = {}
        if not self.data_groups:
            # Create minimal required data groups
            if self.mrz:
                dgs["DG1"] = self.mrz
            # In a real implementation, you would properly encode each data group
            # according to the ICAO specifications
        else:
            dgs = {k: str(v.data) for k, v in self.data_groups.items()}

        # Generate SOD if not present
        sod = self.security_object or "UNSIGNED.0"

        return ICaoPassportModel(
            passport_number=self.passport_data.document_number,
            issue_date=datetime.now().strftime("%Y-%m-%d"),
            expiry_date=self.passport_data.date_of_expiry.isoformat(),
            data_groups=dgs,
            sod=sod,
        )


class VerificationResultModel(BaseModel):
    """Pydantic model for result of a passport verification process."""

    is_valid: bool = Field(description="Whether the passport is valid")
    passport_number: str = Field(description="Passport document number")
    verification_date: datetime = Field(
        default_factory=datetime.now, description="Date and time of verification"
    )
    messages: list[str] = Field(default_factory=list, description="Verification messages/logs")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional verification details"
    )

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
        "json_encoders": {
            datetime: lambda v: v.isoformat(),
        },
    }
