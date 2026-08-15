"""Compatibility DTOs for native ISO/IEC 19794 biometric processing.

Record parsing and quality policy are implemented once in Rust. These Python
types preserve the established application-facing surface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from marty_common.emrtd_native import (
    parse_biometric_template as _native_parse_biometric_template,
)
from marty_common.emrtd_native import (
    validate_biometric_quality as _native_validate_biometric_quality,
)


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
    WSQ = 0x04


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
    source_type: int
    device_type: int
    quality: int
    image_data: bytes
    feature_points: list[tuple[int, int]] | None = None


@dataclass
class FingerprintTemplate:
    """ISO/IEC 19794-2 Fingerprint Template."""

    header: BiometricHeader
    impression_type: int
    finger_quality: int
    finger_position: int
    image_width: int
    image_height: int
    resolution_x: int
    resolution_y: int
    compression: int
    minutiae: list[dict[str, Any]]
    image_data: bytes | None = None


@dataclass
class IrisTemplate:
    """ISO/IEC 19794-6 Iris Template."""

    header: BiometricHeader
    eye_position: int
    image_format: ImageFormat
    image_width: int
    image_height: int
    image_depth: int
    range_: int
    roll_angle: int
    iris_center_x: int
    iris_center_y: int
    iris_radius: int
    image_data: bytes


BiometricTemplate = FacialImageTemplate | FingerprintTemplate | IrisTemplate


def _header(result: dict[str, Any]) -> BiometricHeader:
    validity = result.get("validity_period")
    return BiometricHeader(
        format_owner=int(result["format_owner"]),
        format_type=int(result["format_type"]),
        biometric_type=BiometricType[str(result["biometric_type"]).upper()],
        biometric_subtype=int(result["biometric_subtype"]),
        creation_date=result.get("creation_date"),
        validity_period=((str(validity[0]), str(validity[1])) if validity is not None else None),
        creator=result.get("creator"),
    )


def _template(result: dict[str, Any]) -> BiometricTemplate:
    template_type = result["template_type"]
    header = _header(result["header"])
    if template_type == "facial":
        points = result.get("feature_points")
        return FacialImageTemplate(
            header=header,
            image_format=ImageFormat[str(result["image_format"]).upper()],
            image_width=int(result["image_width"]),
            image_height=int(result["image_height"]),
            image_color_space=int(result["image_color_space"]),
            source_type=int(result["source_type"]),
            device_type=int(result["device_type"]),
            quality=int(result["quality"]),
            image_data=bytes(result["image_data"]),
            feature_points=([(int(point[0]), int(point[1])) for point in points] if points is not None else None),
        )
    if template_type == "fingerprint":
        image_data = result.get("image_data")
        return FingerprintTemplate(
            header=header,
            impression_type=int(result["impression_type"]),
            finger_quality=int(result["finger_quality"]),
            finger_position=int(result["finger_position"]),
            image_width=int(result["image_width"]),
            image_height=int(result["image_height"]),
            resolution_x=int(result["resolution_x"]),
            resolution_y=int(result["resolution_y"]),
            compression=int(result["compression"]),
            minutiae=[dict(value) for value in result["minutiae"]],
            image_data=bytes(image_data) if image_data is not None else None,
        )
    if template_type == "iris":
        return IrisTemplate(
            header=header,
            eye_position=int(result["eye_position"]),
            image_format=ImageFormat[str(result["image_format"]).upper()],
            image_width=int(result["image_width"]),
            image_height=int(result["image_height"]),
            image_depth=int(result["image_depth"]),
            range_=int(result["range"]),
            roll_angle=int(result["roll_angle"]),
            iris_center_x=int(result["iris_center_x"]),
            iris_center_y=int(result["iris_center_y"]),
            iris_radius=int(result["iris_radius"]),
            image_data=bytes(result["image_data"]),
        )
    raise ValueError(f"Unsupported native biometric template type: {template_type}")


def _header_payload(header: BiometricHeader) -> dict[str, Any]:
    return {
        "format_owner": header.format_owner,
        "format_type": header.format_type,
        "biometric_type": header.biometric_type.name.lower(),
        "biometric_subtype": header.biometric_subtype,
        "creation_date": header.creation_date,
        "validity_period": header.validity_period,
        "creator": header.creator,
    }


def _template_payload(template: BiometricTemplate) -> dict[str, Any]:
    common: dict[str, Any] = {"header": _header_payload(template.header)}
    if isinstance(template, FacialImageTemplate):
        return {
            **common,
            "template_type": "facial",
            "image_format": template.image_format.name.lower(),
            "image_width": template.image_width,
            "image_height": template.image_height,
            "image_color_space": template.image_color_space,
            "source_type": template.source_type,
            "device_type": template.device_type,
            "quality": template.quality,
            "image_data": list(template.image_data),
            "feature_points": template.feature_points,
        }
    if isinstance(template, FingerprintTemplate):
        return {
            **common,
            "template_type": "fingerprint",
            "impression_type": template.impression_type,
            "finger_quality": template.finger_quality,
            "finger_position": template.finger_position,
            "image_width": template.image_width,
            "image_height": template.image_height,
            "resolution_x": template.resolution_x,
            "resolution_y": template.resolution_y,
            "compression": template.compression,
            "minutiae": template.minutiae,
            "image_data": list(template.image_data) if template.image_data is not None else None,
        }
    return {
        **common,
        "template_type": "iris",
        "eye_position": template.eye_position,
        "image_format": template.image_format.name.lower(),
        "image_width": template.image_width,
        "image_height": template.image_height,
        "image_depth": template.image_depth,
        "range": template.range_,
        "roll_angle": template.roll_angle,
        "iris_center_x": template.iris_center_x,
        "iris_center_y": template.iris_center_y,
        "iris_radius": template.iris_radius,
        "image_data": list(template.image_data),
    }


class BiometricTemplateProcessor:
    """Stable Python surface over native biometric parsing and quality policy."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def parse_biometric_template(self, data: bytes, biometric_type: BiometricType) -> BiometricTemplate:
        return _template(_native_parse_biometric_template(data, biometric_type.name.lower()))

    def parse_facial_image_template(self, data: bytes) -> FacialImageTemplate:
        result = self.parse_biometric_template(data, BiometricType.FACIAL_IMAGE)
        if not isinstance(result, FacialImageTemplate):
            raise TypeError("Native parser returned a non-facial template")
        return result

    def parse_fingerprint_template(self, data: bytes) -> FingerprintTemplate:
        result = self.parse_biometric_template(data, BiometricType.FINGERPRINT)
        if not isinstance(result, FingerprintTemplate):
            raise TypeError("Native parser returned a non-fingerprint template")
        return result

    def parse_iris_template(self, data: bytes) -> IrisTemplate:
        result = self.parse_biometric_template(data, BiometricType.IRIS)
        if not isinstance(result, IrisTemplate):
            raise TypeError("Native parser returned a non-iris template")
        return result

    def extract_image_data(self, template: FacialImageTemplate | IrisTemplate) -> bytes:
        """Return image bytes from a parsed facial or iris template."""

        return template.image_data

    def validate_template_quality(self, template: BiometricTemplate) -> dict[str, Any]:
        """Evaluate the template with the canonical Rust quality policy."""

        return _native_validate_biometric_quality(_template_payload(template))

    def _validate_facial_quality(self, template: FacialImageTemplate) -> dict[str, Any]:
        return self.validate_template_quality(template)

    def _validate_fingerprint_quality(self, template: FingerprintTemplate) -> dict[str, Any]:
        return self.validate_template_quality(template)

    def _validate_iris_quality(self, template: IrisTemplate) -> dict[str, Any]:
        return self.validate_template_quality(template)


__all__ = [
    "BiometricHeader",
    "BiometricTemplateProcessor",
    "BiometricType",
    "FacialImageTemplate",
    "FingerprintTemplate",
    "ImageFormat",
    "IrisTemplate",
]
