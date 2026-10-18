"""
MRZ Processing Service for Document Processing API
"""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from typing import Any

from app.models.doc_models_clean import (
    MRZField,
    MRZResult,
)
from PIL import Image
from pytesseract import pytesseract  # type: ignore

from marty_plugin.native_backends import NativeOperationError, require_backend

logger = logging.getLogger(__name__)


class MRZException(NativeOperationError):
    """Compatibility exception for callers of the document-processing service."""


class MRZParser:
    """Compatibility adapter over the Rust TD1/TD2/TD3 parser."""

    @staticmethod
    def parse_mrz(mrz: str) -> Any:
        native = require_backend("marty_verification")
        try:
            parsed = native.parse_mrz(mrz.strip().splitlines())
            if getattr(parsed, "check_digits_valid", False) is not True:
                raise MRZException("Rust MRZ checksum validation failed")
            return parsed
        except Exception as exc:
            raise MRZException(f"Rust MRZ parsing failed: {exc}") from exc

    @classmethod
    def parse_td3_mrz(cls, mrz: str) -> Any:
        data = cls.parse_mrz(mrz)
        if data.format != "TD3":
            raise MRZException(f"Expected TD3 MRZ, received {data.format}")
        return data

    @classmethod
    def parse_td2_mrz(cls, mrz: str) -> Any:
        data = cls.parse_mrz(mrz)
        if data.format != "TD2":
            raise MRZException(f"Expected TD2 MRZ, received {data.format}")
        return data

    @classmethod
    def parse_td1_mrz(cls, mrz: str) -> Any:
        data = cls.parse_mrz(mrz)
        if data.format != "TD1":
            raise MRZException(f"Expected TD1 MRZ, received {data.format}")
        return data


class ImageProcessor:
    """Handles image processing and MRZ extraction from images"""

    tess_lang: str | None = None  # Allows injection of language pack name

    @staticmethod
    def decode_base64_image(base64_data: str) -> Image.Image:
        """Decode base64 image data"""
        try:
            # Remove data URL prefix if present
            if "," in base64_data and base64_data.startswith("data:"):
                base64_data = base64_data.split(",", 1)[1]

            # Decode base64
            image_data = base64.b64decode(base64_data)
            image = Image.open(BytesIO(image_data))
        except Exception as e:
            msg = f"Failed to decode image: {e}"
            raise ValueError(msg)
        else:
            return image

    @staticmethod
    def extract_text_from_image(image: Image.Image) -> list[str]:
        """
        Extract actual OCR text; unavailable or empty OCR yields no evidence.
        """
        try:
            # Restrict character set to MRZ allowed chars to improve accuracy
            lang = ImageProcessor.tess_lang or "eng"
            config = (
                "--psm 6 "
                "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789< "
                "-c load_system_dawg=false -c load_freq_dawg=false"
            )
            text = pytesseract.image_to_string(image, config=config, lang=lang)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                logger.info("Extracted text using Tesseract")
                return lines
        except Exception:
            logger.exception("Tesseract OCR failed; no MRZ evidence extracted")

        return []

    @staticmethod
    def extract_text_from_region(region: Image.Image) -> list[str]:
        """Extract actual OCR text from a detected region."""
        return ImageProcessor.extract_text_from_image(region)


class MRZProcessingService:
    """Service for processing MRZ data"""

    def _process_mrz_lines(self, text_lines: list[str]) -> MRZResult | None:
        """Process extracted text lines to create MRZ result"""
        try:
            mrz_text = "\n".join(text_lines)
            mrz_data = self._parse_mrz_by_format(text_lines, mrz_text)

            if mrz_data is None:
                logger.warning(f"Unrecognized MRZ format: {len(text_lines)} lines")
                return None

            return self._build_mrz_result(mrz_data, text_lines)

        except MRZException:
            logger.exception("MRZ parsing error")
            return None
        except (AttributeError, ValueError, TypeError):
            logger.exception("Data conversion error processing MRZ")
            return None

    def _parse_mrz_by_format(self, text_lines: list[str], mrz_text: str) -> Any | None:
        """Attempt to parse MRZ using format-specific parsers."""
        if len(text_lines) == 2:
            return self._try_td3_then_td2(mrz_text)
        if len(text_lines) == 3:
            return self._try_td1(mrz_text)
        return None

    def _try_td3_then_td2(self, mrz_text: str) -> Any | None:
        """Try the native TD-3 and TD-2 parsers."""
        try:
            return MRZParser.parse_td3_mrz(mrz_text)
        except MRZException:
            try:
                return MRZParser.parse_td2_mrz(mrz_text)
            except MRZException:
                return None

    def _try_td1(self, mrz_text: str) -> Any | None:
        """Parse a TD-1 MRZ with the native parser."""
        try:
            return MRZParser.parse_td1_mrz(mrz_text)
        except MRZException:
            return None

    def _build_mrz_result(self, mrz_data: Any, text_lines: list[str]) -> MRZResult:
        """Build MRZResult from parsed MRZ data."""
        valid = getattr(mrz_data, "check_digits_valid", False) is True
        return MRZResult(
            docType=self._safe_str(getattr(mrz_data, "document_type", None)),
            issuingState=self._safe_str(getattr(mrz_data, "issuing_country", None)),
            nationality=self._safe_str(getattr(mrz_data, "nationality", None)),
            documentNumber=self._safe_str(getattr(mrz_data, "document_number", None)),
            documentNumberChecksumValid=True if valid else None,
            optionalData=self._safe_str(getattr(mrz_data, "optional_data", None)) or "",
            givenNames=self._safe_str(getattr(mrz_data, "given_names", None)),
            surname=self._safe_str(getattr(mrz_data, "surname", None)),
            dateOfBirth=self._safe_date(getattr(mrz_data, "date_of_birth", None)),
            dateOfBirthChecksumValid=True if valid else None,
            sex=self._safe_str(getattr(mrz_data, "sex", None)),
            dateOfExpiry=self._safe_date(getattr(mrz_data, "date_of_expiry", None)),
            dateOfExpiryChecksumValid=True if valid else None,
            mrzLines=text_lines,
            overallValid=valid,
            fields=self._create_mrz_fields(mrz_data),
        )

    def _safe_str(self, val: Any) -> str | None:
        """Safely convert value to string, handling enums and None values.

        Accepts that tests may supply Mock attributes.
        """
        if val is None:
            return None
        # Unwrap enums
        if hasattr(val, "value") and isinstance(val.value, str):
            val = val.value
        return str(val) if isinstance(val, str) else None

    def _safe_date(self, val: Any) -> str | None:
        """Retain native MRZ dates without inventing a century for YYMMDD."""
        if isinstance(val, str):
            return val
        try:
            return val.strftime("%Y-%m-%d") if hasattr(val, "strftime") else None
        except (AttributeError, ValueError, TypeError):  # pragma: no cover - defensive
            return None

    def _create_mrz_fields(self, mrz_data: Any) -> list[MRZField]:
        """Create detailed field information for MRZ result"""
        fields = []

        # Document code field
        if mrz_data.document_type:
            fields.append(
                MRZField(
                    name="DocumentCode",
                    value=mrz_data.document_type,
                    checksumValid=None,
                )
            )

        # Issuing state field
        if mrz_data.issuing_country:
            fields.append(
                MRZField(
                    name="IssuingState",
                    value=mrz_data.issuing_country,
                    checksumValid=None,
                )
            )

        # Document number field
        if mrz_data.document_number:
            fields.append(
                MRZField(
                    name="DocumentNumber",
                    value=mrz_data.document_number,
                    checksumValid=True
                    if getattr(mrz_data, "check_digits_valid", False) is True
                    else None,
                )
            )

        # Date of birth field
        if mrz_data.date_of_birth:
            fields.append(
                MRZField(
                    name="DateOfBirth",
                    value=self._safe_date(mrz_data.date_of_birth),
                    checksumValid=True
                    if getattr(mrz_data, "check_digits_valid", False) is True
                    else None,
                )
            )

        return fields
