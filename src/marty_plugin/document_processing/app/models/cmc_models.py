"""
CMC (Crew Member Certificate) models for Document Processing API

This module defines Pydantic models for CMC creation, signing, and verification
requests and responses in the FastAPI document processing service.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CMCSecurityModelAPI(str, Enum):
    """Security models for CMC documents in API."""

    CHIP_LDS = "CHIP_LDS"
    VDS_NC = "VDS_NC"


class GenderAPI(str, Enum):
    """Gender enum for API requests."""

    MALE = "M"
    FEMALE = "F"
    UNSPECIFIED = "X"


class CMCCreateRequest(BaseModel):
    """Request model for creating a new Crew Member Certificate."""

    # Mandatory fields
    document_number: str = Field(..., description="CMC document number")
    issuing_country: str = Field(
        ..., description="3-letter issuing country code", min_length=3, max_length=3
    )
    surname: str = Field(..., description="Primary identifier (surname)")
    given_names: str = Field(..., description="Secondary identifier (given names)")
    nationality: str = Field(
        ..., description="3-letter nationality code", min_length=3, max_length=3
    )
    date_of_birth: str = Field(..., description="Date of birth (YYYY-MM-DD)")
    gender: GenderAPI = Field(..., description="Gender designation")
    date_of_expiry: str = Field(..., description="Date of expiry (YYYY-MM-DD)")

    # Optional CMC-specific fields
    employer: str | None = Field(None, description="Employing airline/organization")
    crew_id: str | None = Field(None, description="Crew member identification number")

    # Security model selection
    security_model: CMCSecurityModelAPI = Field(
        CMCSecurityModelAPI.CHIP_LDS, description="Security model to use for the CMC"
    )

    # Face image for chip-based model (DG2)
    face_image: str | None = Field(None, description="Base64 encoded face image for chip model")

    # Annex 9 compliance fields
    background_check_verified: bool = Field(False, description="Background check completion status")

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_number": "CMC123456789",
                "issuing_country": "USA",
                "surname": "SMITH",
                "given_names": "JOHN MICHAEL",
                "nationality": "USA",
                "date_of_birth": "1985-06-15",
                "gender": "M",
                "date_of_expiry": "2030-06-15",
                "employer": "American Airlines",
                "crew_id": "AA12345",
                "security_model": "CHIP_LDS",
                "background_check_verified": True,
            }
        }
    }


class CMCCreateResponse(BaseModel):
    """Response model for CMC creation."""

    success: bool = Field(..., description="Operation success status")
    cmc_id: str | None = Field(None, description="Generated CMC ID")
    td1_mrz: str | None = Field(None, description="Generated TD-1 MRZ string")
    security_model: str | None = Field(None, description="Applied security model")
    error_message: str | None = Field(None, description="Error message if operation failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "cmc_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "td1_mrz": "IUSA1234567890CMC<<<<<<<<<\nSMITH<<JOHN<MICHAEL<<<<<<<\n8506156M3006150USA<<<<<<<<0",
                "security_model": "CHIP_LDS",
            }
        }
    }


class CMCSignRequest(BaseModel):
    """Request model for signing a CMC."""

    cmc_id: str = Field(..., description="CMC ID to sign")
    signer_id: str | None = Field(None, description="Signer identification")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cmc_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "signer_id": "document-signer-001",
            }
        }
    }


class CMCSignResponse(BaseModel):
    """Response model for CMC signing."""

    success: bool = Field(..., description="Signing operation success status")
    signature_info: dict[str, Any | None] = Field(None, description="Signature information")
    error_message: str | None = Field(None, description="Error message if operation failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "signature_info": {
                    "signature_date": "2025-10-01T15:30:00Z",
                    "signer_id": "document-signer-001",
                    "algorithm": "ES256",
                },
            }
        }
    }


class CMCVerificationRequest(BaseModel):
    """Request model for CMC verification."""

    # One of these must be provided
    td1_mrz: str | None = Field(None, description="TD-1 MRZ string for verification")
    barcode_data: str | None = Field(None, description="VDS-NC barcode data")
    cmc_id: str | None = Field(None, description="Direct CMC ID lookup")

    # Verification options
    check_revocation: bool = Field(True, description="Check revocation status")
    validate_background_check: bool = Field(True, description="Validate Annex 9 compliance")

    model_config = {
        "json_schema_extra": {
            "example": {
                "td1_mrz": "IUSA1234567890CMC<<<<<<<<<\nSMITH<<JOHN<MICHAEL<<<<<<<\n8506156M3006150USA<<<<<<<<0",
                "check_revocation": True,
                "validate_background_check": True,
            }
        }
    }


class VerificationResult(BaseModel):
    """Individual verification result."""

    check_name: str = Field(..., description="Name of the verification check")
    passed: bool = Field(..., description="Whether the check passed")
    details: str = Field(..., description="Details about the check result")
    error_code: str | None = Field(None, description="Error code if check failed")


class CMCVerificationResponse(BaseModel):
    """Response model for CMC verification."""

    success: bool = Field(..., description="Verification operation success status")
    is_valid: bool = Field(False, description="Overall validity of the CMC")
    cmc_data: dict[str, Any | None] = Field(None, description="CMC certificate data")
    verification_results: list[VerificationResult] = Field(
        default_factory=list, description="Detailed verification results"
    )
    error_message: str | None = Field(None, description="Error message if operation failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "is_valid": True,
                "cmc_data": {
                    "document_number": "CMC123456789",
                    "surname": "SMITH",
                    "given_names": "JOHN MICHAEL",
                    "nationality": "USA",
                },
                "verification_results": [
                    {
                        "check_name": "TD-1 MRZ Validation",
                        "passed": True,
                        "details": "MRZ format and check digits valid",
                    },
                    {
                        "check_name": "Background Check",
                        "passed": True,
                        "details": "Background verification completed successfully",
                    },
                ],
            }
        }
    }


class CMCBackgroundCheckRequest(BaseModel):
    """Request model for background check operations."""

    cmc_id: str = Field(..., description="CMC ID for background check")
    check_authority: str = Field(..., description="Authority performing the check")
    check_reference: str | None = Field(None, description="Reference number for the check")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cmc_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "check_authority": "DHS-TSA",
                "check_reference": "BGC-2025-001234",
            }
        }
    }


class CMCBackgroundCheckResponse(BaseModel):
    """Response model for background check operations."""

    success: bool = Field(..., description="Operation success status")
    check_passed: bool = Field(False, description="Whether the background check passed")
    check_date: str | None = Field(None, description="Date of the check (ISO format)")
    check_authority: str | None = Field(None, description="Authority that performed the check")
    check_reference: str | None = Field(None, description="Reference number for the check")
    error_message: str | None = Field(None, description="Error message if operation failed")


class CMCVisaFreeStatusRequest(BaseModel):
    """Request model for visa-free status updates."""

    cmc_id: str = Field(..., description="CMC ID for status update")
    visa_free_eligible: bool = Field(..., description="Visa-free entry eligibility")
    authority: str = Field(..., description="Authority granting/revoking status")
    reason: str = Field(..., description="Reason for status change")

    model_config = {
        "json_schema_extra": {
            "example": {
                "cmc_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "visa_free_eligible": True,
                "authority": "DHS-CBP",
                "reason": "Background check completed successfully",
            }
        }
    }


class CMCVisaFreeStatusResponse(BaseModel):
    """Response model for visa-free status updates."""

    success: bool = Field(..., description="Operation success status")
    visa_free_eligible: bool = Field(False, description="Current visa-free eligibility")
    updated_at: str | None = Field(None, description="Update timestamp (ISO format)")
    error_message: str | None = Field(None, description="Error message if operation failed")


class CMCListRequest(BaseModel):
    """Request model for listing CMCs."""

    limit: int = Field(10, description="Maximum number of results", ge=1, le=100)
    offset: int = Field(0, description="Number of results to skip", ge=0)
    issuing_country: str | None = Field(None, description="Filter by issuing country")
    security_model: CMCSecurityModelAPI | None = Field(None, description="Filter by security model")

    model_config = {
        "json_schema_extra": {
            "example": {
                "limit": 20,
                "offset": 0,
                "issuing_country": "USA",
                "security_model": "CHIP_LDS",
            }
        }
    }


class CMCListResponse(BaseModel):
    """Response model for listing CMCs."""

    success: bool = Field(..., description="Operation success status")
    total_count: int = Field(0, description="Total number of CMCs")
    cmcs: list[dict[str, Any]] = Field(default_factory=list, description="List of CMC data")
    error_message: str | None = Field(None, description="Error message if operation failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "total_count": 42,
                "cmcs": [
                    {
                        "cmc_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "document_number": "CMC123456789",
                        "surname": "SMITH",
                        "given_names": "JOHN MICHAEL",
                        "security_model": "CHIP_LDS",
                        "status": "ACTIVE",
                    }
                ],
            }
        }
    }


class CMCStatusResponse(BaseModel):
    """Response model for CMC status information."""

    success: bool = Field(..., description="Operation success status")
    cmc_id: str | None = Field(None, description="CMC ID")
    status: str | None = Field(None, description="Current CMC status")
    created_at: str | None = Field(None, description="Creation timestamp")
    updated_at: str | None = Field(None, description="Last update timestamp")
    security_model: str | None = Field(None, description="Security model used")
    annex9_compliant: bool = Field(False, description="Annex 9 compliance status")
    error_message: str | None = Field(None, description="Error message if operation failed")
