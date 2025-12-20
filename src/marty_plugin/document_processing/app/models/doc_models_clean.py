"""Clean Pydantic models for the Document Processing API.

Temporary file to bypass corrupted legacy `document_models.py`.
All consuming code should import from this module instead of `document_models`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CheckResult(int, Enum):
    NEGATIVE = 0
    POSITIVE = 1
    NOT_PERFORMED = 2


class ProcessingStatus(int, Enum):
    NOT_FINISHED = 0
    FINISHED = 1
    TIMEOUT = 2


class RfidLocation(int, Enum):
    NO_CHIP = 0
    DATA_PAGE = 1
    BACK_PAGE = 2


class ContainerType(str, Enum):
    MRZ_CONTAINER = "MrzContainer"
    IMAGE_QUALITY_CONTAINER = "ImageQualityContainer"
    LOG_CONTAINER = "LogContainer"


class Light(int, Enum):
    OFF = 0
    VISIBLE = 1
    UV = 2
    IR = 6


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str = "ready"
    version: str
    uptimeSec: int
    license: dict[str, Any] | None = None


class LicenseInfo(BaseModel):
    valid: bool
    expiresAt: str


class TransactionInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    # Accept either camelCase or alias names on input; always expose camelCase attributes
    requestId: str = Field(..., alias="TransactionID")
    createdAt: str = Field(..., alias="DateTime")
    coreVersion: str
    computerName: str | None = Field(None, alias="ComputerName")
    userName: str | None = Field(None, alias="UserName")


class ImageQualityThresholds(BaseModel):
    minFocus: int | None = Field(None, ge=0, le=100)
    maxGlare: int | None = Field(None, ge=0, le=100)
    minDpi: int | None = Field(None, ge=72)
    maxAngle: int | None = Field(None, ge=0, le=90)
    brightnessThreshold: int | None = None
    dpiThreshold: int | None = None
    angleThreshold: int | None = None
    focusCheck: bool | None = None
    glaresCheck: bool | None = None
    colornessCheck: bool | None = None
    moireCheck: bool | None = None
    documentPositionIndent: int | None = None
    expectedPass: list[str] | None = None


class ImageQualityReport(BaseModel):
    focus: int
    glare: int
    dpi: int
    angle: int
    passed: bool
    failedReasons: list[str] | None = None


class ProcessParam(BaseModel):
    scenario: str
    resultTypeOutput: list[str] | None = None
    mrzFormatsFilter: list[str] | None = None
    strictImageQuality: bool | None = False
    imageQa: ImageQualityThresholds | None = None
    forceReadMrzBeforeLocate: bool | None = False
    dateFormat: str | None = "MM/dd/yyyy"
    log: bool | None = True
    logLevel: str | None = "FatalError"
    generateNumericCodes: bool | None = True
    generateAlpha2Codes: bool | None = True


class ProcessRequestImage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ImageData: str | None = None
    ImageUri: str | None = None
    pageIdx: int | None = Field(None, alias="page_idx")
    light: Light | None = Light.VISIBLE


class ProcessRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    processParam: ProcessParam
    images: list[ProcessRequestImage] = Field(..., alias="List", min_length=1)
    tag: str | None = None

    # Backwards compatibility accessor
    @property
    def List(self) -> list[ProcessRequestImage]:
        return self.images


class MRZField(BaseModel):
    name: str
    value: str
    confidence: float | None = None
    line: int | None = None
    start: int | None = None
    length: int | None = None
    checksumValid: bool | None = None
    warnings: list[str] | None = None


class MRZResult(BaseModel):
    docType: str | None = None
    issuingState: str | None = None
    nationality: str | None = None
    documentNumber: str | None = None
    documentNumberChecksumValid: bool | None = None
    optionalData: str | None = None
    givenNames: str | None = None
    surname: str | None = None
    dateOfBirth: str | None = None
    dateOfBirthChecksumValid: bool | None = None
    sex: str | None = None
    dateOfExpiry: str | None = None
    dateOfExpiryChecksumValid: bool | None = None
    mrzLines: list[str] | None = None
    overallValid: bool | None = None
    fields: list[MRZField] | None = None


class Status(BaseModel):
    overallStatus: CheckResult
    optical: CheckResult
    portrait: CheckResult
    rfid: CheckResult
    stopList: CheckResult


class Container(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    type: ContainerType
    buf_length: int | None = None
    light: int | None = None
    list_idx: int | None = None
    page_idx: int | None = None
    result_type: int | None = None
    # Use snake_case internally but keep legacy 'Status' alias for compatibility
    status: Status | None = Field(None, alias="Status")
    mrzResult: MRZResult | None = None
    imageQuality: ImageQualityReport | None = None
    logs: list[str] | None = None


class ContainerList(BaseModel):
    Count: int
    List: list[Container]


class ProcessResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    transactionInfo: TransactionInfo | None = Field(None, alias="TransactionInfo")
    elapsedTime: int
    containerList: ContainerList | None = Field(None, alias="ContainerList")
    ChipPage: RfidLocation = RfidLocation.NO_CHIP
    CoreLibResultCode: int = 0
    ProcessingFinished: ProcessingStatus = ProcessingStatus.FINISHED
    log: str | None = None
    passBackObject: dict[str, Any] | None = None
    morePagesAvailable: int = 0
    metadata: dict[str, Any] | None = None


ImageQualityThresholds.model_rebuild()
ImageQualityReport.model_rebuild()
ProcessParam.model_rebuild()
ProcessRequestImage.model_rebuild()
ProcessRequest.model_rebuild()
MRZField.model_rebuild()
MRZResult.model_rebuild()
Status.model_rebuild()
Container.model_rebuild()
ContainerList.model_rebuild()
TransactionInfo.model_rebuild()
ProcessResponse.model_rebuild()

__all__ = [
    "CheckResult",
    "Container",
    "ContainerList",
    "ContainerType",
    "ErrorResponse",
    "HealthResponse",
    "ImageQualityReport",
    "ImageQualityThresholds",
    "LicenseInfo",
    "Light",
    "MRZField",
    "MRZResult",
    "ProcessParam",
    "ProcessRequest",
    "ProcessRequestImage",
    "ProcessResponse",
    "ProcessingStatus",
    "RfidLocation",
    "Status",
    "TransactionInfo",
]
