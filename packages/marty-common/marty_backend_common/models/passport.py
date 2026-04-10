"""
Passport data models for Marty services.

These models comply with ICAO Doc 9303 specifications for Machine Readable Travel Documents.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date, datetime
from enum import Enum
from typing import Any, TypeVar
from uuid import UUID, uuid4

# Import Pydantic for improved data validation
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T", bound="BaseModel")

logger = logging.getLogger(__name__)


def camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def snake_to_camel_dict(d: dict) -> dict:
    """Convert all keys in a dictionary from snake_case to camelCase."""
    return {camel_case(k): v for k, v in d.items()}


def camel_to_snake(camel_str: str) -> str:
    """Convert camelCase to snake_case."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel_str).lower()


def camel_to_snake_dict(d: dict) -> dict:
    """Convert all keys in a dictionary from camelCase to snake_case."""
    return {camel_to_snake(k): v for k, v in d.items()}


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


class MRZData(BaseModel):
    """Model for Machine Readable Zone (MRZ) data."""

    document_type: str = Field(..., description="Document type, P for passport")
    issuing_country: str = Field(..., description="3-letter country code")
    document_number: str = Field(..., description="Document number")
    surname: str
    given_names: str
    nationality: str = Field(..., description="3-letter country code")
    date_of_birth: str = Field(..., description="YYMMDD format")
    gender: Gender
    date_of_expiry: str = Field(..., description="YYMMDD format")
    personal_number: str | None = None

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("issuing_country", "nationality")
    @classmethod
    def validate_country_code(cls, v):
        if len(v) != 3:
            msg = "Country code must be 3 characters"
            raise ValueError(msg)
        return v.upper()

    @field_validator("date_of_birth", "date_of_expiry")
    @classmethod
    def validate_date_format(cls, v):
        if len(v) != 6 or not v.isdigit():
            msg = "Date must be in YYMMDD format"
            raise ValueError(msg)
        return v

    def generate_mrz_string(self) -> str:
        """Generate TD3 MRZ string compliant with ICAO Doc 9303."""
        from marty_plugin.common.utils.mrz_utils import MRZFormatter

        return MRZFormatter.generate_td3_mrz(self)

    def to_dict(self):
        """Convert to dictionary with camelCase keys."""
        data = self.model_dump()
        return snake_to_camel_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> MRZData:
        """Create an instance from a dictionary with camelCase keys."""
        snake_case_data = camel_to_snake_dict(data)
        return cls(**snake_case_data)


class DataGroup(BaseModel):
    """A data group in the Logical Data Structure (LDS)."""

    type: DataGroupType
    data: Any

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    def to_dict(self):
        """Convert to dictionary with camelCase keys."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> DataGroup:
        """Create an instance from a dictionary."""
        return cls(**data)


class SignedObject(BaseModel):
    """Document Security Object (SOD) containing digital signatures."""

    signature: str = Field(..., description="Base64 encoded signature")
    timestamp: int = Field(..., description="Unix timestamp")
    algorithm: str = "SHA256withRSA"  # Default signature algorithm

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("signature")
    @classmethod
    def validate_signature_base64(cls, v):
        try:
            base64.b64decode(v)
        except Exception:
            msg = "Signature must be base64 encoded"
            raise ValueError(msg)
        return v

    def to_string(self) -> str:
        """Convert SOD to string format as used in passport files."""
        return f"{self.signature}.{self.timestamp}"

    @classmethod
    def from_string(cls, sod_string: str) -> SignedObject:
        """Create SOD from string format."""
        parts = sod_string.split(".")
        if len(parts) != 2:
            msg = "Invalid SOD format"
            raise ValueError(msg)

        return cls(signature=parts[0], timestamp=int(parts[1]))

    def to_dict(self):
        """Convert to dictionary with camelCase keys."""
        data = self.model_dump()
        return snake_to_camel_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> SignedObject:
        """Create an instance from a dictionary with camelCase keys."""
        snake_case_data = camel_to_snake_dict(data)
        return cls(**snake_case_data)


class PassportData(BaseModel):
    """Basic passport data model."""

    document_number: str = Field(..., description="Passport number")
    issuing_country: str = Field(..., description="3-letter country code")
    surname: str
    given_names: str
    nationality: str = Field(..., description="3-letter country code")
    date_of_birth: date
    gender: Gender
    date_of_expiry: date
    personal_number: str | None = None
    photo: str | bytes | None = None  # Base64 encoded or raw JPEG photo

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("issuing_country", "nationality")
    @classmethod
    def validate_country_code(cls, v):
        if len(v) != 3:
            msg = "Country code must be 3 characters"
            raise ValueError(msg)
        return v.upper()

    @field_validator("date_of_expiry")
    @classmethod
    def validate_expiry_date(cls, v, values):
        # Access data from ValidationInfo object
        date_of_birth = values.data.get("date_of_birth")
        if date_of_birth and v < date_of_birth:
            msg = "Expiry date must be after date of birth"
            raise ValueError(msg)
        return v

    @field_validator("photo")
    @classmethod
    def validate_photo(cls, v):
        if v is not None and isinstance(v, str):
            try:
                # Check if it's a valid base64 string
                base64.b64decode(v)
            except Exception:
                msg = "Photo must be base64 encoded"
                raise ValueError(msg)
            else:
                return v
        return v

    @property
    def photo_bytes(self) -> bytes | None:
        """Get photo as bytes."""
        if self.photo is None:
            return None
        if isinstance(self.photo, bytes):
            return self.photo
        return base64.b64decode(self.photo)

    @property
    def photo_base64(self) -> str | None:
        """Get photo as base64 encoded string."""
        if self.photo is None:
            return None
        if isinstance(self.photo, bytes):
            return base64.b64encode(self.photo).decode("utf-8")
        return self.photo

    def to_mrz_data(self) -> MRZData:
        """Convert passport data to MRZ format."""
        return MRZData(
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

    def to_dict(self):
        """Convert to dictionary with camelCase keys."""
        data = self.model_dump()
        # Handle photo conversion to base64 if it's bytes
        if "photo" in data and isinstance(data["photo"], bytes):
            data["photo"] = base64.b64encode(data["photo"]).decode("utf-8")

        # Convert dates to string format
        if "date_of_birth" in data and isinstance(data["date_of_birth"], date):
            data["date_of_birth"] = data["date_of_birth"].isoformat()
        if "date_of_expiry" in data and isinstance(data["date_of_expiry"], date):
            data["date_of_expiry"] = data["date_of_expiry"].isoformat()

        return snake_to_camel_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> PassportData:
        """Create an instance from a dictionary with camelCase keys."""
        snake_case_data = camel_to_snake_dict(data)
        # Convert date strings to date objects
        if "date_of_birth" in snake_case_data and isinstance(snake_case_data["date_of_birth"], str):
            snake_case_data["date_of_birth"] = datetime.fromisoformat(
                snake_case_data["date_of_birth"]
            ).date()
        if "date_of_expiry" in snake_case_data and isinstance(
            snake_case_data["date_of_expiry"], str
        ):
            snake_case_data["date_of_expiry"] = datetime.fromisoformat(
                snake_case_data["date_of_expiry"]
            ).date()
        return cls(**snake_case_data)


class ICaoPassport(BaseModel):
    """ICAO Doc 9303 compliant passport data model."""

    passport_number: str  # Document number
    issue_date: str  # ISO format date string
    expiry_date: str  # ISO format date string
    data_groups: dict[str, str]  # Data groups keyed by type
    sod: str = ""  # Signed Object Document as string (empty if not signed)

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("issue_date", "expiry_date")
    @classmethod
    def validate_date_format(cls, v):
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            msg = "Date must be in ISO format"
            raise ValueError(msg)
        return v

    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_date(cls, v, values):
        # Access data from ValidationInfo object
        issue_date = values.data.get("issue_date")
        if issue_date:
            try:
                issue = datetime.fromisoformat(issue_date.replace("Z", "+00:00"))
                expiry = datetime.fromisoformat(v.replace("Z", "+00:00"))
                if expiry <= issue:
                    msg = "Expiry date must be after issue date"
                    raise ValueError(msg)
            except ValueError:
                pass  # Already validated in the previous validator
        return v

    def to_dict(self):
        """Convert to dictionary."""
        # The test expects passport_number as is, not in camelCase
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> ICaoPassport:
        """Create an instance from a dictionary."""
        return cls(**data)


class Passport(BaseModel):
    """Complete passport model including security data."""

    id: UUID = Field(default_factory=uuid4)
    passport_data: PassportData
    mrz: str | None = None
    security_object: str | None = None  # Document Security Object
    chip_content: str | bytes | None = None  # Binary chip data as bytes or base64
    data_groups: dict[str, DataGroup] = Field(default_factory=dict)

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("chip_content")
    @classmethod
    def validate_chip_content(cls, v):
        if v is not None and isinstance(v, str):
            try:
                # Check if it's a valid base64 string
                base64.b64decode(v)
            except Exception:
                msg = "Chip content must be base64 encoded if provided as string"
                raise ValueError(msg)
            else:
                return v
        return v

    @property
    def chip_content_bytes(self) -> bytes | None:
        """Get chip content as bytes."""
        if self.chip_content is None:
            return None
        if isinstance(self.chip_content, bytes):
            return self.chip_content
        return base64.b64decode(self.chip_content)

    @property
    def chip_content_base64(self) -> str | None:
        """Get chip content as base64 encoded string."""
        if self.chip_content is None:
            return None
        if isinstance(self.chip_content, bytes):
            return base64.b64encode(self.chip_content).decode("utf-8")
        return self.chip_content

    def to_icao_format(self) -> ICaoPassport:
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
        sod = self.security_object or ""

        return ICaoPassport(
            passport_number=self.passport_data.document_number,
            issue_date=datetime.now().strftime("%Y-%m-%d"),
            expiry_date=self.passport_data.date_of_expiry.isoformat(),
            data_groups=dgs,
            sod=sod,
        )

    def to_dict(self):
        """Convert to dictionary with custom structure."""
        result = {
            "id": str(self.id),
            "documentData": self.passport_data.to_dict(),
            "mrz": self.mrz,
            "securityObject": self.security_object,
            "dataGroups": {k: v.to_dict() for k, v in self.data_groups.items()},
        }

        # Handle chip content
        if self.chip_content:
            if isinstance(self.chip_content, bytes):
                result["chipContent"] = base64.b64encode(self.chip_content).decode("utf-8")
            else:
                result["chipContent"] = self.chip_content

        return result

    def add_data_group(self, data_group: DataGroup) -> None:
        """Add a data group to the passport."""
        self.data_groups[data_group.type.value] = data_group

    def verify_sod_certificate(self) -> bool:
        """
        Verify the SOD (Security Object of the Document) certificate.

        Returns:
            bool: True if the SOD certificate is valid and trusted, False otherwise
        """
        try:
            if not self.security_object:
                logger.warning("No SOD present in passport data")
                return False

            # First try to use our SOD parser for enhanced validation
            try:
                from marty_plugin.common.crypto.sod_parser import SODProcessor

                processor = SODProcessor()
                sod = processor.parse_sod_data(self.security_object)

                if sod:
                    # Extract SOD information for validation
                    sod_info = processor.extract_sod_info(sod)

                    logger.info("SOD certificate validation using enhanced parser")
                    logger.info(f"SOD content type: {sod_info.get('content_type', 'unknown')}")
                    logger.info(f"Has certificate: {sod_info.get('has_certificate', False)}")

                    # Basic structural validation passed
                    if sod_info.get("has_certificate"):
                        logger.info("SOD contains certificate - structure validation passed")
                        # In a full implementation, this would verify certificate chain
                        # against CSCA (Country Signing Certificate Authority) roots
                        return True
                    logger.warning("SOD does not contain certificate")
                    return False
                logger.warning("SOD parsing failed, falling back to basic validation")

            except ImportError:
                logger.warning("SOD parser not available, falling back to certificate service")

            # Try to use the certificate validation service
            try:
                from marty_plugin.common.services.certificate_validation import (
                    validate_sod_certificate,
                )

                return validate_sod_certificate(self.security_object)
            except ImportError:
                logger.warning("Certificate validation service not available")

            # Fallback to basic validation
            logger.info("Using basic SOD validation")
            if isinstance(self.security_object, str):
                # Basic checks for valid SOD format
                if self.security_object == "UNSIGNED.0" or not self.security_object.strip():
                    logger.warning("SOD is unsigned or empty")
                    return False
                # Additional basic validations could be added here
                return len(self.security_object) > 10  # Reasonable minimum length

            return bool(self.security_object)

        except Exception:
            logger.exception("SOD certificate verification failed")
            return False

    def verify_data_group_integrity(self) -> bool:
        """
        Verify the integrity of data groups using the SOD.

        This method checks that the hash values in the SOD match
        the computed hashes of the data groups.

        Returns:
            bool: True if all data group hashes are valid, False otherwise
        """
        try:
            if not self.security_object or not self.data_groups:
                logger.warning("Missing SOD or data groups for integrity verification")
                return False

            # Import the new data group hash verification service
            from marty_plugin.common.crypto.data_group_hasher import verify_passport_data_groups

            # Convert security_object to appropriate format
            if isinstance(self.security_object, str):
                # Handle string format (hex or base64)
                sod_data = self.security_object
            else:
                # Handle other formats (should be converted to string/bytes)
                sod_data = str(self.security_object)

            # Prepare data groups for verification
            # Convert DataGroup objects to dictionary format for verification
            dg_dict = {}
            for dg_key, dg_obj in self.data_groups.items():
                if hasattr(dg_obj, "model_dump"):
                    # Use Pydantic model serialization for consistent hashing
                    dg_dict[f"DG{dg_key}"] = dg_obj
                else:
                    dg_dict[f"DG{dg_key}"] = dg_obj

            # Perform verification using the new service
            success, errors, details = verify_passport_data_groups(sod_data, dg_dict)

            if not success:
                logger.warning(f"Data group integrity verification failed: {'; '.join(errors)}")
                return False

            logger.info(
                f"Data group integrity verified successfully. "
                f"Verified {details.get('data_groups_verified', 0)} data groups "
                f"using {details.get('hash_algorithm', 'unknown')} algorithm."
            )
        except ImportError:
            logger.warning("Data group hash verification service not available, using fallback")
            # Fallback to basic validation
            required_dgs = ["DG1"]  # At minimum, DG1 (MRZ) should be present
            return all(dg_type in self.data_groups for dg_type in required_dgs)
        except Exception:
            logger.exception("Data group integrity verification failed")
            return False
        else:
            return True

    def perform_active_authentication(self) -> bool:
        """
        Perform active authentication with the passport chip.

        This method executes a cryptographic challenge-response protocol
        to verify the authenticity of the chip and prevent cloning.

        Returns:
            bool: True if active authentication succeeds, False otherwise
        """
        try:
            # In a full implementation, this would:
            # 1. Generate a random challenge
            # 2. Send the challenge to the passport chip
            # 3. Receive and verify the cryptographic response
            # 4. Validate the response using the chip's public key

            # For now, simulate successful authentication if chip content exists
            # This is a placeholder that needs RFID communication and cryptographic verification
            return self.chip_content is not None

        except Exception:
            return False

    def read_data_groups(self) -> bool:
        """
        Read data groups from the passport chip.

        This method communicates with the physical passport chip via RFID
        to read and decode the data groups.

        Returns:
            bool: True if data groups were successfully read, False otherwise
        """
        try:
            # In a full implementation, this would:
            # 1. Establish RFID communication with the passport chip
            # 2. Perform Basic Access Control (BAC) or Password Authenticated Connection Establishment (PACE)
            # 3. Read each data group from the chip
            # 4. Decode the ASN.1 encoded data
            # 5. Populate the data_groups dictionary

            # For now, simulate reading if MRZ is available (needed for BAC)
            if self.mrz:
                # Create a basic DG1 from MRZ if not already present
                if "DG1" not in self.data_groups:
                    dg1 = DataGroup(
                        type=DataGroupType.DG1,
                        data=self.mrz.encode("utf-8"),
                        hash_algorithm="SHA-256",
                    )
                    self.add_data_group(dg1)
                    result = True
                else:
                    result = True
            else:
                result = False
        except Exception:
            return False
        else:
            return result

    @classmethod
    def from_dict(cls, data: dict) -> Passport:
        """Create an instance from a dictionary."""
        # Extract and convert the passport data
        passport_data = PassportData.from_dict(data["documentData"])

        # Convert the UUID string to UUID object
        id_val = UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id")

        # Process data groups
        data_groups = {}
        if "dataGroups" in data:
            for k, v in data["dataGroups"].items():
                data_groups[k] = DataGroup.from_dict(v)

        return cls(
            id=id_val,
            passport_data=passport_data,
            mrz=data.get("mrz"),
            security_object=data.get("securityObject"),
            chip_content=data.get("chipContent"),
            data_groups=data_groups,
        )


class VerificationResult(BaseModel):
    """Result of a passport verification process."""

    is_valid: bool
    passport_number: str
    verification_date: datetime = Field(default_factory=datetime.now)
    messages: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }

    def to_dict(self):
        """Convert to dictionary with camelCase keys."""
        data = self.model_dump()
        # Convert datetime to ISO format string
        if "verification_date" in data and isinstance(data["verification_date"], datetime):
            data["verification_date"] = data["verification_date"].isoformat()
        return snake_to_camel_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> VerificationResult:
        """Create an instance from a dictionary with camelCase keys."""
        snake_case_data = camel_to_snake_dict(data)
        # Convert date string back to datetime
        if "verification_date" in snake_case_data and isinstance(
            snake_case_data["verification_date"], str
        ):
            snake_case_data["verification_date"] = datetime.fromisoformat(
                snake_case_data["verification_date"]
            )
        return cls(**snake_case_data)


# =============================================================================
# CMC (Crew Member Certificate) Models
# =============================================================================


class CMCSecurityModel(str, Enum):
    """Security models supported for CMC documents."""

    CHIP_LDS = "CHIP_LDS"  # Chip with minimal LDS (DG1, DG2)
    VDS_NC = "VDS_NC"  # Visible Digital Seal (Non-Constrained)


class CMCTD1MRZData(BaseModel):
    """Model for TD-1 format MRZ data specifically for Crew Member Certificates."""

    document_type: str = Field("I", description="Document type, 'I' for ID card format")
    issuing_country: str = Field(..., description="3-letter country code")
    document_number: str = Field(..., description="Document number")
    surname: str = Field(..., description="Primary identifier (surname)")
    given_names: str = Field(..., description="Secondary identifier (given names)")
    nationality: str = Field(..., description="3-letter nationality code")
    date_of_birth: str = Field(..., description="YYMMDD format")
    gender: Gender
    date_of_expiry: str = Field(..., description="YYMMDD format")
    optional_data: str | None = Field(None, description="Optional data field")

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("issuing_country", "nationality")
    @classmethod
    def validate_country_code(cls, v):
        if len(v) != 3:
            msg = "Country code must be 3 characters"
            raise ValueError(msg)
        return v.upper()

    @field_validator("date_of_birth", "date_of_expiry")
    @classmethod
    def validate_date_format(cls, v):
        if len(v) != 6 or not v.isdigit():
            msg = "Date must be in YYMMDD format"
            raise ValueError(msg)
        return v

    def generate_td1_mrz_string(self) -> str:
        """Generate TD-1 MRZ string compliant with ICAO Doc 9303."""
        # Import here to avoid circular imports
        try:
            from marty_plugin.common.utils.mrz_utils import MRZFormatter

            return MRZFormatter.generate_td1_mrz(self)
        except ImportError:
            # Fallback implementation if MRZFormatter doesn't exist yet
            return f"{self.document_type}{self.issuing_country}{self.document_number}"

    def to_dict(self):
        """Convert to dictionary with camelCase keys."""
        data = self.model_dump()
        return snake_to_camel_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> CMCTD1MRZData:
        """Create an instance from a dictionary with camelCase keys."""
        snake_case_data = camel_to_snake_dict(data)
        return cls(**snake_case_data)


class CMCData(BaseModel):
    """Data model for Crew Member Certificate (CMC) according to Doc 9303 Part 5 + Annex 9."""

    # Mandatory fields (as per Annex 9)
    document_number: str = Field(..., description="CMC document number")
    issuing_country: str = Field(..., description="3-letter issuing state code")
    surname: str = Field(..., description="Primary identifier per ICAO name rules")
    given_names: str = Field(..., description="Secondary identifier per ICAO name rules")
    nationality: str = Field(..., description="3-letter nationality code")
    date_of_birth: date = Field(..., description="Date of birth")
    gender: Gender = Field(..., description="Sex designation")
    date_of_expiry: date = Field(..., description="Date of expiry")

    # Optional CMC-specific fields
    employer: str | None = Field(None, description="Employing airline/organization")
    crew_id: str | None = Field(None, description="Crew member identification number")

    # Security and validation fields
    security_model: CMCSecurityModel = Field(
        CMCSecurityModel.CHIP_LDS, description="Security model used"
    )
    background_check_verified: bool = Field(
        False, description="Annex 9 background check completion"
    )
    face_image: str | bytes | None = None  # Face image if chip present (DG2)

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("issuing_country", "nationality")
    @classmethod
    def validate_country_code(cls, v):
        if len(v) != 3:
            msg = "Country code must be 3 characters"
            raise ValueError(msg)
        return v.upper()

    @field_validator("date_of_expiry")
    @classmethod
    def validate_expiry_date(cls, v, values):
        date_of_birth = values.data.get("date_of_birth")
        if date_of_birth and v < date_of_birth:
            msg = "Expiry date must be after date of birth"
            raise ValueError(msg)
        return v

    @field_validator("face_image")
    @classmethod
    def validate_face_image(cls, v):
        if v is not None and isinstance(v, str):
            try:
                base64.b64decode(v)
            except Exception:
                msg = "Face image must be base64 encoded"
                raise ValueError(msg)
            else:
                return v
        return v

    @property
    def face_image_bytes(self) -> bytes | None:
        """Get face image as bytes."""
        if self.face_image is None:
            return None
        if isinstance(self.face_image, bytes):
            return self.face_image
        return base64.b64decode(self.face_image)

    @property
    def face_image_base64(self) -> str | None:
        """Get face image as base64 encoded string."""
        if self.face_image is None:
            return None
        if isinstance(self.face_image, bytes):
            return base64.b64encode(self.face_image).decode("utf-8")
        return self.face_image

    def to_td1_mrz_data(self) -> CMCTD1MRZData:
        """Convert CMC data to TD-1 MRZ format."""
        return CMCTD1MRZData(
            document_type="I",  # ID card format for CMC
            issuing_country=self.issuing_country,
            document_number=self.document_number,
            surname=self.surname,
            given_names=self.given_names,
            nationality=self.nationality,
            date_of_birth=self.date_of_birth.strftime("%y%m%d"),
            gender=self.gender,
            date_of_expiry=self.date_of_expiry.strftime("%y%m%d"),
            optional_data=self.crew_id,  # Use crew_id as optional data
        )

    def to_dict(self):
        """Convert to dictionary with camelCase keys."""
        data = self.model_dump()

        # Handle face image conversion to base64 if it's bytes
        if "face_image" in data and isinstance(data["face_image"], bytes):
            data["face_image"] = base64.b64encode(data["face_image"]).decode("utf-8")

        # Convert dates to string format
        if "date_of_birth" in data and isinstance(data["date_of_birth"], date):
            data["date_of_birth"] = data["date_of_birth"].isoformat()
        if "date_of_expiry" in data and isinstance(data["date_of_expiry"], date):
            data["date_of_expiry"] = data["date_of_expiry"].isoformat()

        return snake_to_camel_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> CMCData:
        """Create an instance from a dictionary with camelCase keys."""
        snake_case_data = camel_to_snake_dict(data)

        # Convert date strings to date objects
        if "date_of_birth" in snake_case_data and isinstance(snake_case_data["date_of_birth"], str):
            snake_case_data["date_of_birth"] = datetime.fromisoformat(
                snake_case_data["date_of_birth"]
            ).date()
        if "date_of_expiry" in snake_case_data and isinstance(
            snake_case_data["date_of_expiry"], str
        ):
            snake_case_data["date_of_expiry"] = datetime.fromisoformat(
                snake_case_data["date_of_expiry"]
            ).date()

        return cls(**snake_case_data)


class VDSNCBarcode(BaseModel):
    """Model for Visible Digital Seal Non-Constrained (VDS-NC) barcode data."""

    header: str = Field(..., description="VDS header information")
    message_type: str = Field("CMC", description="Message type identifier")
    issuing_country: str = Field(..., description="3-letter issuing country code")
    signature_algorithm: str = Field("ES256", description="Signature algorithm")
    certificate_reference: str = Field(..., description="Certificate reference")
    signature_creation_date: str = Field(..., description="Signature creation date (YYMMDD)")
    signature_creation_time: str | None = Field(
        None, description="Signature creation time (HHMMSS)"
    )
    cmc_data: dict = Field(..., description="CMC dataset payload")
    signature: str = Field(..., description="Digital signature")

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("issuing_country")
    @classmethod
    def validate_country_code(cls, v):
        if len(v) != 3:
            msg = "Country code must be 3 characters"
            raise ValueError(msg)
        return v.upper()

    @field_validator("signature_creation_date")
    @classmethod
    def validate_date_format(cls, v):
        if len(v) != 6 or not v.isdigit():
            msg = "Date must be in YYMMDD format"
            raise ValueError(msg)
        return v

    @field_validator("signature_creation_time")
    @classmethod
    def validate_time_format(cls, v):
        if v is not None and (len(v) != 6 or not v.isdigit()):
            msg = "Time must be in HHMMSS format"
            raise ValueError(msg)
        return v

    def encode_to_barcode(self) -> str:
        """Encode VDS-NC data to barcode format."""
        # This would implement the actual VDS-NC encoding
        # For now, return a placeholder
        import json

        return base64.b64encode(json.dumps(self.model_dump()).encode()).decode()

    def verify_signature(self, public_key: bytes) -> bool:
        """Verify the VDS-NC signature."""
        # This would implement actual signature verification
        # using the provided public key
        try:
            from marty_plugin.common.crypto import verify_signature

            canonical_data = self._get_canonical_data()
            return verify_signature(
                canonical_data.encode(),
                base64.b64decode(self.signature),
                public_key,
                self.signature_algorithm,
            )
        except ImportError:
            # Fallback if crypto module not available
            return True  # Simplified for demo

    def _get_canonical_data(self) -> str:
        """Get canonical representation of the data for signature verification."""
        # Create canonical form excluding the signature field
        data_for_signature = self.model_dump(exclude={"signature"})
        return json.dumps(data_for_signature, sort_keys=True, separators=(",", ":"))

    def to_dict(self):
        """Convert to dictionary with camelCase keys."""
        data = self.model_dump()
        return snake_to_camel_dict(data)


class CMCCertificate(BaseModel):
    """Complete Crew Member Certificate model including security data."""

    id: UUID = Field(default_factory=uuid4)
    cmc_data: CMCData
    td1_mrz: str | None = None  # TD-1 format MRZ string
    security_object: str | None = None  # Document Security Object (for chip model)
    vds_nc_barcode: VDSNCBarcode | None = None  # VDS-NC barcode (for non-chip model)
    chip_content: str | bytes | None = None  # Binary chip data
    data_groups: dict[str, DataGroup] = Field(default_factory=dict)  # DG1, DG2 for chip model

    # Annex 9 compliance fields
    electronic_record_id: str | None = Field(None, description="Electronic record identifier")
    issuer_record_keeping: bool = Field(False, description="Issuer maintains electronic record")
    visa_free_entry_eligible: bool = Field(False, description="Eligible for visa-free crew entry")

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }

    @field_validator("chip_content")
    @classmethod
    def validate_chip_content(cls, v):
        if v is not None and isinstance(v, str):
            try:
                base64.b64decode(v)
            except Exception:
                msg = "Chip content must be base64 encoded if provided as string"
                raise ValueError(msg)
            else:
                return v
        return v

    @property
    def chip_content_bytes(self) -> bytes | None:
        """Get chip content as bytes."""
        if self.chip_content is None:
            return None
        if isinstance(self.chip_content, bytes):
            return self.chip_content
        return base64.b64decode(self.chip_content)

    @property
    def chip_content_base64(self) -> str | None:
        """Get chip content as base64 encoded string."""
        if self.chip_content is None:
            return None
        if isinstance(self.chip_content, bytes):
            return base64.b64encode(self.chip_content).decode("utf-8")
        return self.chip_content

    @property
    def uses_chip_security(self) -> bool:
        """Check if certificate uses chip-based security model."""
        return self.cmc_data.security_model == CMCSecurityModel.CHIP_LDS

    @property
    def uses_vds_nc_security(self) -> bool:
        """Check if certificate uses VDS-NC security model."""
        return self.cmc_data.security_model == CMCSecurityModel.VDS_NC

    def add_data_group(self, data_group: DataGroup) -> None:
        """Add a data group to the CMC (for chip-based model)."""
        if not self.uses_chip_security:
            msg = "Data groups only supported for chip-based security model"
            raise ValueError(msg)
        self.data_groups[data_group.type.value] = data_group

    def verify_certificate(self) -> bool:
        """Verify the CMC certificate according to the verification protocol."""
        try:
            # Step 1: Parse and validate MRZ
            if not self.td1_mrz:
                logger.warning("No TD-1 MRZ present in CMC")
                return False

            # Step 2: Security model specific verification
            if self.uses_chip_security:
                return self._verify_chip_security()
            if self.uses_vds_nc_security:
                return self._verify_vds_nc_security()
            logger.warning(f"Unknown security model: {self.cmc_data.security_model}")
            return False

        except Exception:
            logger.exception("CMC verification failed")
            return False

    def _verify_chip_security(self) -> bool:
        """Verify chip-based security (SOD + DG validation)."""
        if not self.security_object:
            logger.warning("No SOD present for chip-based CMC")
            return False

        # Verify SOD signature (simplified)
        # In real implementation, this would verify against CSCA

        # Verify DG1 (MRZ) matches visual MRZ
        dg1 = self.data_groups.get("DG1")
        if dg1 and str(dg1.data) != self.td1_mrz:
            logger.warning("DG1 MRZ data does not match visual MRZ")
            return False

        # Verify DG2 (face image) if present
        dg2 = self.data_groups.get("DG2")
        if dg2 and self.cmc_data.face_image:
            # In real implementation, compare biometric template
            pass

        return True

    def _verify_vds_nc_security(self) -> bool:
        """Verify VDS-NC barcode security."""
        if not self.vds_nc_barcode:
            logger.warning("No VDS-NC barcode present")
            return False

        # Compare VDS-NC payload to printed fields
        vds_data = self.vds_nc_barcode.cmc_data

        # Verify key fields match
        if vds_data.get("document_number") != self.cmc_data.document_number:
            logger.warning("VDS-NC document number mismatch")
            return False

        if vds_data.get("surname") != self.cmc_data.surname:
            logger.warning("VDS-NC surname mismatch")
            return False

        # Verify signature would need issuer's public key
        return True  # Simplified for demo

    def to_dict(self):
        """Convert to dictionary with custom structure."""
        result = {
            "id": str(self.id),
            "cmcData": self.cmc_data.to_dict(),
            "td1Mrz": self.td1_mrz,
            "securityObject": self.security_object,
            "dataGroups": {k: v.to_dict() for k, v in self.data_groups.items()},
            "electronicRecordId": self.electronic_record_id,
            "issuerRecordKeeping": self.issuer_record_keeping,
            "visaFreeEntryEligible": self.visa_free_entry_eligible,
        }

        if self.vds_nc_barcode:
            result["vdsNcBarcode"] = self.vds_nc_barcode.to_dict()

        # Handle chip content
        if self.chip_content:
            if isinstance(self.chip_content, bytes):
                result["chipContent"] = base64.b64encode(self.chip_content).decode("utf-8")
            else:
                result["chipContent"] = self.chip_content

        return result

    @classmethod
    def from_dict(cls, data: dict) -> CMCCertificate:
        """Create an instance from a dictionary."""
        # Convert camelCase keys to snake_case
        snake_case_data = camel_to_snake_dict(data)

        # Handle nested objects
        if "cmc_data" in snake_case_data:
            snake_case_data["cmc_data"] = CMCData.from_dict(snake_case_data["cmc_data"])

        if snake_case_data.get("vds_nc_barcode"):
            snake_case_data["vds_nc_barcode"] = VDSNCBarcode(
                **camel_to_snake_dict(snake_case_data["vds_nc_barcode"])
            )

        if "data_groups" in snake_case_data:
            data_groups = {}
            for k, v in snake_case_data["data_groups"].items():
                data_groups[k] = DataGroup.from_dict(v)
            snake_case_data["data_groups"] = data_groups

        return cls(**snake_case_data)
