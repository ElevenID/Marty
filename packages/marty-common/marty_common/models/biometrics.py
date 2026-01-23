"""
Biometric data models for e-passport data.

Models for biometric data formats used in e-passports:
- Facial Images (ISO/IEC 19794-5)
- Fingerprints (ISO/IEC 19794-4)
- Iris Images (ISO/IEC 19794-6)

These models comply with the ICAO Doc 9303 and ISO/IEC standards for biometrics.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any


class BiometricType(IntEnum):
    """Biometric type codes as defined in ICAO Doc 9303."""

    FACIAL = 1
    FINGER = 2
    IRIS = 3
    SIGNATURE = 7
    RESERVED = 8


class CompressionType(str, Enum):
    """Image compression types."""

    JPEG = "JPEG"
    JPEG2000 = "JPEG2000"
    PNG = "PNG"
    WSQ = "WSQ"  # Wavelet Scalar Quantization (for fingerprints)
    UNCOMPRESSED = "UNCOMPRESSED"


class FaceImageType(IntEnum):
    """Face image types as per ISO/IEC 19794-5."""

    BASIC = 0
    FULL_FRONTAL = 1
    TOKEN_FRONTAL = 2


class FacePoseAngle(IntEnum):
    """Face pose angle ranges."""

    UNSPECIFIED = 0
    FRONTAL = 1
    HALF_LEFT = 2
    LEFT = 3
    HALF_RIGHT = 4
    RIGHT = 5


class FaceFeaturePoint(IntEnum):
    """Feature points on the face as defined in ISO/IEC 19794-5."""

    RIGHT_EYE_CENTER = 1
    LEFT_EYE_CENTER = 2
    MOUTH_RIGHT_CORNER = 3
    MOUTH_LEFT_CORNER = 4
    NOSE_TIP = 5
    RIGHT_EAR_TRAGUS = 6
    LEFT_EAR_TRAGUS = 7
    RIGHT_EYE_OUTER_CORNER = 8
    RIGHT_EYE_INNER_CORNER = 9
    LEFT_EYE_INNER_CORNER = 10
    LEFT_EYE_OUTER_CORNER = 11
    NOSE_ROOT = 12


class FingerPosition(IntEnum):
    """Finger position codes as per ISO/IEC 19794-4."""

    UNKNOWN = 0
    RIGHT_THUMB = 1
    RIGHT_INDEX = 2
    RIGHT_MIDDLE = 3
    RIGHT_RING = 4
    RIGHT_LITTLE = 5
    LEFT_THUMB = 6
    LEFT_INDEX = 7
    LEFT_MIDDLE = 8
    LEFT_RING = 9
    LEFT_LITTLE = 10


class FingerImpressionType(IntEnum):
    """Finger impression types as per ISO/IEC 19794-4."""

    LIVE_SCAN_PLAIN = 0
    LIVE_SCAN_ROLLED = 1
    NONLIVE_SCAN_PLAIN = 2
    NONLIVE_SCAN_ROLLED = 3
    LATENT_IMPRESSION = 4
    LATENT_TRACING = 5
    LATENT_PHOTO = 6
    LATENT_LIFT = 7


class IrisImageType(IntEnum):
    """Iris image types as per ISO/IEC 19794-6."""

    UNCROPPED = 1
    VGA = 2
    CROPPED = 3
    CROPPED_AND_MASKED = 7


class IrisEyePosition(IntEnum):
    """Eye position for iris image."""

    UNDEFINED = 0
    RIGHT = 1
    LEFT = 2


@dataclass
class BiometricSubtypeInfo:
    """Information about a biometric subtype."""

    biometric_type: BiometricType
    subtype: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {"biometricType": self.biometric_type, "subtype": self.subtype}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BiometricSubtypeInfo:
        """Create BiometricSubtypeInfo from dictionary."""
        return cls(biometric_type=BiometricType(data["biometricType"]), subtype=data["subtype"])


@dataclass
class FeaturePoint:
    """Feature point for facial recognition."""

    feature_type: FaceFeaturePoint
    x: int  # X coordinate
    y: int  # Y coordinate

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {"featureType": self.feature_type, "x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeaturePoint:
        """Create FeaturePoint from dictionary."""
        return cls(feature_type=FaceFeaturePoint(data["featureType"]), x=data["x"], y=data["y"])


@dataclass
class FacialImageInfo:
    """Facial image information as per ISO/IEC 19794-5."""

    image_type: FaceImageType
    width: int
    height: int
    color_space: str
    source_type: str
    device_type: str
    quality: int | None = None
    pose_angle: FacePoseAngle | None = None
    pose_angle_yaw: int | None = None
    pose_angle_pitch: int | None = None
    pose_angle_roll: int | None = None
    feature_points: list[FeaturePoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "imageType": int(self.image_type),
            "width": self.width,
            "height": self.height,
            "colorSpace": self.color_space,
            "sourceType": self.source_type,
            "deviceType": self.device_type,
        }

        if self.quality is not None:
            result["quality"] = self.quality

        if self.pose_angle is not None:
            result["poseAngle"] = int(self.pose_angle)

        if self.pose_angle_yaw is not None:
            result["poseAngleYaw"] = self.pose_angle_yaw

        if self.pose_angle_pitch is not None:
            result["poseAnglePitch"] = self.pose_angle_pitch

        if self.pose_angle_roll is not None:
            result["poseAngleRoll"] = self.pose_angle_roll

        if self.feature_points:
            result["featurePoints"] = [fp.to_dict() for fp in self.feature_points]

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FacialImageInfo:
        """Create FacialImageInfo from dictionary."""
        info = cls(
            image_type=FaceImageType(data["imageType"]),
            width=data["width"],
            height=data["height"],
            color_space=data["colorSpace"],
            source_type=data["sourceType"],
            device_type=data["deviceType"],
            quality=data.get("quality"),
            pose_angle=FacePoseAngle(data["poseAngle"]) if "poseAngle" in data else None,
            pose_angle_yaw=data.get("poseAngleYaw"),
            pose_angle_pitch=data.get("poseAnglePitch"),
            pose_angle_roll=data.get("poseAngleRoll"),
        )

        if "featurePoints" in data:
            info.feature_points = [FeaturePoint.from_dict(fp) for fp in data["featurePoints"]]

        return info


@dataclass
class FingerImageInfo:
    """Fingerprint image information as per ISO/IEC 19794-4."""

    position: FingerPosition
    width: int
    height: int
    impression_type: FingerImpressionType
    horizontal_resolution: int  # pixels per cm
    vertical_resolution: int  # pixels per cm
    grayscale_depth: int
    quality: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "position": int(self.position),
            "width": self.width,
            "height": self.height,
            "impressionType": int(self.impression_type),
            "horizontalResolution": self.horizontal_resolution,
            "verticalResolution": self.vertical_resolution,
            "grayscaleDepth": self.grayscale_depth,
        }

        if self.quality is not None:
            result["quality"] = self.quality

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FingerImageInfo:
        """Create FingerImageInfo from dictionary."""
        return cls(
            position=FingerPosition(data["position"]),
            width=data["width"],
            height=data["height"],
            impression_type=FingerImpressionType(data["impressionType"]),
            horizontal_resolution=data["horizontalResolution"],
            vertical_resolution=data["verticalResolution"],
            grayscale_depth=data["grayscaleDepth"],
            quality=data.get("quality"),
        )


@dataclass
class IrisImageInfo:
    """Iris image information as per ISO/IEC 19794-6."""

    image_type: IrisImageType
    eye_position: IrisEyePosition
    width: int
    height: int
    device_unique_id: str
    quality: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "imageType": int(self.image_type),
            "eyePosition": int(self.eye_position),
            "width": self.width,
            "height": self.height,
            "deviceUniqueId": self.device_unique_id,
        }

        if self.quality is not None:
            result["quality"] = self.quality

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IrisImageInfo:
        """Create IrisImageInfo from dictionary."""
        return cls(
            image_type=IrisImageType(data["imageType"]),
            eye_position=IrisEyePosition(data["eyePosition"]),
            width=data["width"],
            height=data["height"],
            device_unique_id=data["deviceUniqueId"],
            quality=data.get("quality"),
        )


@dataclass
class BiometricDataBlock:
    """Biometric data block as defined in ICAO Doc 9303."""

    biometric_type: BiometricType
    biometric_subtype: int
    creation_date: datetime
    format_owner: int
    format_type: int
    compression_type: CompressionType
    image_data: bytes
    facial_info: FacialImageInfo | None = None
    finger_info: FingerImageInfo | None = None
    iris_info: IrisImageInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "biometricType": int(self.biometric_type),
            "biometricSubtype": self.biometric_subtype,
            "creationDate": self.creation_date.isoformat(),
            "formatOwner": self.format_owner,
            "formatType": self.format_type,
            "compressionType": self.compression_type.value,
            "imageData": base64.b64encode(self.image_data).decode("ascii"),
        }

        if self.facial_info:
            result["facialInfo"] = self.facial_info.to_dict()

        if self.finger_info:
            result["fingerInfo"] = self.finger_info.to_dict()

        if self.iris_info:
            result["irisInfo"] = self.iris_info.to_dict()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BiometricDataBlock:
        """Create BiometricDataBlock from dictionary."""
        block = cls(
            biometric_type=BiometricType(data["biometricType"]),
            biometric_subtype=data["biometricSubtype"],
            creation_date=datetime.fromisoformat(data["creationDate"]),
            format_owner=data["formatOwner"],
            format_type=data["formatType"],
            compression_type=CompressionType(data["compressionType"]),
            image_data=base64.b64decode(data["imageData"]),
        )

        if "facialInfo" in data:
            block.facial_info = FacialImageInfo.from_dict(data["facialInfo"])

        if "fingerInfo" in data:
            block.finger_info = FingerImageInfo.from_dict(data["fingerInfo"])

        if "irisInfo" in data:
            block.iris_info = IrisImageInfo.from_dict(data["irisInfo"])

        return block

    def get_specific_info(self) -> FacialImageInfo | FingerImageInfo | IrisImageInfo | None:
        """Get the specific biometric info for this block."""
        if self.biometric_type == BiometricType.FACIAL:
            return self.facial_info
        if self.biometric_type == BiometricType.FINGER:
            return self.finger_info
        if self.biometric_type == BiometricType.IRIS:
            return self.iris_info
        return None


@dataclass
class BiometricInfoGroup:
    """Group of biometric information for a specific type."""

    biometric_type: BiometricType
    format_owner: int
    format_type: int
    elements: list[BiometricDataBlock] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "biometricType": int(self.biometric_type),
            "formatOwner": self.format_owner,
            "formatType": self.format_type,
            "elements": [element.to_dict() for element in self.elements],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BiometricInfoGroup:
        """Create BiometricInfoGroup from dictionary."""
        group = cls(
            biometric_type=BiometricType(data["biometricType"]),
            format_owner=data["formatOwner"],
            format_type=data["formatType"],
        )

        if "elements" in data:
            group.elements = [BiometricDataBlock.from_dict(elem) for elem in data["elements"]]

        return group

    def add_element(self, element: BiometricDataBlock) -> None:
        """Add a biometric data block to this group."""
        if element.biometric_type != self.biometric_type:
            msg = f"Biometric type mismatch: {element.biometric_type} vs {self.biometric_type}"
            raise ValueError(msg)
        self.elements.append(element)


@dataclass
class CBEFFContainer:
    """Common Biometric Exchange Formats Framework (CBEFF) container."""

    version: int = 1
    biometric_groups: list[BiometricInfoGroup] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "version": self.version,
            "biometricGroups": [group.to_dict() for group in self.biometric_groups],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CBEFFContainer:
        """Create CBEFFContainer from dictionary."""
        container = cls(version=data.get("version", 1))

        if "biometricGroups" in data:
            container.biometric_groups = [
                BiometricInfoGroup.from_dict(group) for group in data["biometricGroups"]
            ]

        return container

    def get_group_by_type(self, biometric_type: BiometricType) -> BiometricInfoGroup | None:
        """Get a biometric group by its type."""
        for group in self.biometric_groups:
            if group.biometric_type == biometric_type:
                return group
        return None

    def add_group(self, group: BiometricInfoGroup) -> None:
        """Add a biometric group to this container."""
        self.biometric_groups.append(group)

    def to_binary(self) -> bytes:
        """
        Convert to binary CBEFF format (stub implementation).

        In a real implementation, this would encode the CBEFF container
        according to the CBEFF standard.
        """
        # This is a simplified stub that would be replaced with a real implementation
        import json

        return json.dumps(self.to_dict()).encode("utf-8")

    @classmethod
    def from_binary(cls, data: bytes) -> CBEFFContainer:
        """
        Create CBEFFContainer from binary CBEFF data (stub implementation).

        In a real implementation, this would decode the CBEFF container
        according to the CBEFF standard.
        """
        # This is a simplified stub that would be replaced with a real implementation
        import json

        return cls.from_dict(json.loads(data.decode("utf-8")))


@dataclass
class BiometricMatchResult:
    """Result of a biometric match operation."""

    biometric_type: BiometricType
    score: float
    decision: bool
    match_time: datetime = field(default_factory=datetime.now)
    match_details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "biometricType": int(self.biometric_type),
            "score": self.score,
            "decision": self.decision,
            "matchTime": self.match_time.isoformat(),
        }

        if self.match_details:
            result["matchDetails"] = self.match_details

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BiometricMatchResult:
        """Create BiometricMatchResult from dictionary."""
        return cls(
            biometric_type=BiometricType(data["biometricType"]),
            score=data["score"],
            decision=data["decision"],
            match_time=datetime.fromisoformat(data["matchTime"]),
            match_details=data.get("matchDetails"),
        )
