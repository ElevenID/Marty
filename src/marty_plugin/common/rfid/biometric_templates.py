"""Biometric Template Processing for ICAO Passport Data.

Processes ISO/IEC 19794 biometric templates from passport chips.
Supports facial images, fingerprint templates, and iris data.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BiometricType(Enum):
    """ISO/IEC 19794 biometric types."""

    FACIAL_IMAGE = 0x02
    FINGERPRINT = 0x08
    IRIS = 0x10
    VOICE = 0x04
    DNA = 0x20


class ImageFormat(Enum):
    """Supported image formats in biometric templates."""

    JPEG = 0x00
    JPEG2000 = 0x01
    PNG = 0x02
    BMP = 0x03
    WSQ = 0x04  # Wavelet Scalar Quantization (fingerprint)


@dataclass
class BiometricHeader:
    """Common biometric template header."""

    format_owner: int
    format_type: int
    biometric_type: BiometricType
    biometric_subtype: int
    creation_date: str | None
    validity_period: tuple[str, str] | None
    creator: str | None


@dataclass
class FacialImageTemplate:
    """ISO/IEC 19794-5 Facial Image Template."""

    header: BiometricHeader
    image_format: ImageFormat
    image_width: int
    image_height: int
    image_color_space: int
    source_type: int  # 0=unknown, 1=static, 2=video
    device_type: int  # 0=unknown, 1=basic, 2=enhanced
    quality: int  # 0-100
    image_data: bytes
    feature_points: list[tuple[int, int]] | None = None


@dataclass
class FingerprintTemplate:
    """ISO/IEC 19794-2 Fingerprint Template."""

    header: BiometricHeader
    impression_type: int  # 0=live-scan plain, 1=live-scan rolled, etc.
    finger_quality: int  # 0-100
    finger_position: int  # 1=right thumb, 2=right index, etc.
    image_width: int
    image_height: int
    resolution_x: int  # pixels per cm
    resolution_y: int
    compression: int  # 0=uncompressed, 1=WSQ, 2=JPEG
    minutiae: list[dict[str, Any]]  # Minutiae points
    image_data: bytes | None = None


@dataclass
class IrisTemplate:
    """ISO/IEC 19794-6 Iris Template."""

    header: BiometricHeader
    eye_position: int  # 1=right, 2=left
    image_format: ImageFormat
    image_width: int
    image_height: int
    image_depth: int  # bits per pixel
    range_: int  # capture distance in mm
    roll_angle: int  # degrees
    iris_center_x: int
    iris_center_y: int
    iris_radius: int
    image_data: bytes


class BiometricTemplateProcessor:
    """Processes biometric templates from passport data."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def parse_biometric_template(self, data: bytes, biometric_type: BiometricType) -> Any:
        """Parse biometric template based on type."""
        try:
            if biometric_type == BiometricType.FACIAL_IMAGE:
                return self.parse_facial_image_template(data)
            if biometric_type == BiometricType.FINGERPRINT:
                return self.parse_fingerprint_template(data)
            if biometric_type == BiometricType.IRIS:
                return self.parse_iris_template(data)
            msg = f"Unsupported biometric type: {biometric_type}"
            raise ValueError(msg)

        except Exception:
            self.logger.exception("Failed to parse biometric template")
            raise

    def parse_facial_image_template(self, data: bytes) -> FacialImageTemplate:
        """Parse ISO/IEC 19794-5 facial image template."""
        if len(data) < 20:
            msg = "Facial image template too short"
            raise ValueError(msg)

        offset = 0

        # Parse common header
        header = self._parse_common_header(data, offset)
        offset += 14  # Common header size

        # Parse facial image specific fields
        if offset + 16 > len(data):
            msg = "Invalid facial image template format"
            raise ValueError(msg)

        # Extract facial image fields
        fields = struct.unpack(">HHHHHHBB", data[offset : offset + 16])
        offset += 16

        image_width = fields[0]
        image_height = fields[1]
        image_color_space = fields[2]
        source_type = fields[3]
        device_type = fields[4]
        quality = fields[5]
        image_format = ImageFormat(fields[6])

        # Extract image data
        image_data = data[offset:]

        return FacialImageTemplate(
            header=header,
            image_format=image_format,
            image_width=image_width,
            image_height=image_height,
            image_color_space=image_color_space,
            source_type=source_type,
            device_type=device_type,
            quality=quality,
            image_data=image_data,
        )

    def parse_fingerprint_template(self, data: bytes) -> FingerprintTemplate:
        """Parse ISO/IEC 19794-2 fingerprint template."""
        if len(data) < 26:
            msg = "Fingerprint template too short"
            raise ValueError(msg)

        offset = 0

        # Parse common header
        header = self._parse_common_header(data, offset)
        offset += 14

        # Parse fingerprint specific fields
        fields = struct.unpack(">BBBBHHHHBB", data[offset : offset + 12])
        offset += 12

        impression_type = fields[0]
        finger_quality = fields[1]
        finger_position = fields[2]
        image_width = fields[4]
        image_height = fields[5]
        resolution_x = fields[6]
        resolution_y = fields[7]
        compression = fields[8]

        # Parse minutiae data (simplified)
        minutiae = []
        # Full minutiae parsing would be more complex

        # Extract remaining data as image if present
        image_data = data[offset:] if offset < len(data) else None

        return FingerprintTemplate(
            header=header,
            impression_type=impression_type,
            finger_quality=finger_quality,
            finger_position=finger_position,
            image_width=image_width,
            image_height=image_height,
            resolution_x=resolution_x,
            resolution_y=resolution_y,
            compression=compression,
            minutiae=minutiae,
            image_data=image_data,
        )

    def parse_iris_template(self, data: bytes) -> IrisTemplate:
        """Parse ISO/IEC 19794-6 iris template."""
        if len(data) < 25:
            msg = "Iris template too short"
            raise ValueError(msg)

        offset = 0

        # Parse common header
        header = self._parse_common_header(data, offset)
        offset += 14

        # Parse iris specific fields
        fields = struct.unpack(">BBHHBHHHH", data[offset : offset + 15])
        offset += 15

        eye_position = fields[0]
        image_format = ImageFormat(fields[1])
        image_width = fields[2]
        image_height = fields[3]
        image_depth = fields[4]
        range_ = fields[5]
        roll_angle = fields[6]
        iris_center_x = fields[7]
        iris_center_y = fields[8]
        iris_radius = fields[9]

        # Extract iris image data
        image_data = data[offset:]

        return IrisTemplate(
            header=header,
            eye_position=eye_position,
            image_format=image_format,
            image_width=image_width,
            image_height=image_height,
            image_depth=image_depth,
            range_=range_,
            roll_angle=roll_angle,
            iris_center_x=iris_center_x,
            iris_center_y=iris_center_y,
            iris_radius=iris_radius,
            image_data=image_data,
        )

    def _parse_common_header(self, data: bytes, offset: int) -> BiometricHeader:
        """Parse common biometric template header."""
        if len(data) < offset + 14:
            msg = "Header data too short"
            raise ValueError(msg)

        # Basic header parsing (simplified)
        fields = struct.unpack(">HHBBBBB", data[offset : offset + 9])

        format_owner = fields[0]
        format_type = fields[1]
        biometric_type = BiometricType(fields[2])
        biometric_subtype = fields[3]

        return BiometricHeader(
            format_owner=format_owner,
            format_type=format_type,
            biometric_type=biometric_type,
            biometric_subtype=biometric_subtype,
            creation_date=None,  # Would parse from remaining fields
            validity_period=None,
            creator=None,
        )

    def extract_image_data(self, template: FacialImageTemplate | IrisTemplate) -> bytes:
        """Extract raw image data from biometric template."""
        return template.image_data

    def validate_template_quality(self, template: Any) -> dict[str, Any]:
        """Validate biometric template quality."""
        quality_report = {"overall_quality": 0.0, "issues": [], "recommendations": []}

        if isinstance(template, FacialImageTemplate):
            quality_report.update(self._validate_facial_quality(template))
        elif isinstance(template, FingerprintTemplate):
            quality_report.update(self._validate_fingerprint_quality(template))
        elif isinstance(template, IrisTemplate):
            quality_report.update(self._validate_iris_quality(template))

        return quality_report

    def _validate_facial_quality(self, template: FacialImageTemplate) -> dict[str, Any]:
        """Validate facial image template quality."""
        issues = []
        recommendations = []
        quality_score = template.quality / 100.0

        # Check image dimensions
        if template.image_width < 240 or template.image_height < 320:
            issues.append("Image resolution below ICAO recommendations")
            recommendations.append("Use higher resolution image (min 240x320)")
            quality_score *= 0.8

        # Check image format
        if template.image_format not in [ImageFormat.JPEG, ImageFormat.JPEG2000]:
            issues.append("Non-standard image format")
            recommendations.append("Use JPEG or JPEG2000 format")

        return {
            "overall_quality": quality_score,
            "issues": issues,
            "recommendations": recommendations,
        }

    def _validate_fingerprint_quality(self, template: FingerprintTemplate) -> dict[str, Any]:
        """Validate fingerprint template quality."""
        issues = []
        recommendations = []
        quality_score = template.finger_quality / 100.0

        # Check resolution
        if template.resolution_x < 500 or template.resolution_y < 500:
            issues.append("Resolution below FBI standards (500 ppi)")
            recommendations.append("Use 500+ ppi resolution for fingerprints")
            quality_score *= 0.7

        # Check minutiae count
        if len(template.minutiae) < 12:
            issues.append("Insufficient minutiae points for reliable matching")
            recommendations.append("Capture more minutiae points (minimum 12)")
            quality_score *= 0.6

        return {
            "overall_quality": quality_score,
            "issues": issues,
            "recommendations": recommendations,
        }

    def _validate_iris_quality(self, template: IrisTemplate) -> dict[str, Any]:
        """Validate iris template quality."""
        issues = []
        recommendations = []
        quality_score = 0.8  # Default quality for iris

        # Check image dimensions
        if template.image_width < 640 or template.image_height < 480:
            issues.append("Iris image resolution below recommended standards")
            recommendations.append("Use higher resolution for iris capture")
            quality_score *= 0.8

        # Check iris radius
        if template.iris_radius < 50:
            issues.append("Iris appears too small in image")
            recommendations.append("Move closer to capture device")
            quality_score *= 0.7

        return {
            "overall_quality": quality_score,
            "issues": issues,
            "recommendations": recommendations,
        }
