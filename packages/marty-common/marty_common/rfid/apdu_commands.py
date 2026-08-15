"""Compatibility models for native ISO/IEC 7816-4 APDU processing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from marty_common.native_backends import load_native_backend

logger = logging.getLogger(__name__)


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "apdu_build_read_binary_commands",
            "apdu_encode",
            "apdu_parse_command",
            "apdu_parse_response",
            "passport_data_group_file_id",
        ),
    )


def _native_call(operation, *args):
    try:
        return operation(*args)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc


class APDUClass(Enum):
    ISO7816 = 0x00
    GLOBAL_PLATFORM = 0x80
    PROPRIETARY = 0xFF


class APDUInstruction(Enum):
    SELECT = 0xA4
    READ_BINARY = 0xB0
    READ_RECORD = 0xB2
    GET_CHALLENGE = 0x84
    EXTERNAL_AUTHENTICATE = 0x82
    INTERNAL_AUTHENTICATE = 0x88
    GET_DATA = 0xCA
    GENERAL_AUTHENTICATE = 0x86
    VERIFY = 0x20


@dataclass
class APDUCommand:
    """Stable Python command model serialized and validated by Rust."""

    cla: int
    ins: int
    p1: int
    p2: int
    data: bytes | None = None
    le: int | None = None

    def __post_init__(self) -> None:
        self.to_bytes()

    def to_bytes(self) -> bytes:
        return bytes(
            _native_call(
                _native().apdu_encode,
                self.cla,
                self.ins,
                self.p1,
                self.p2,
                self.data,
                self.le,
            )
        )

    @classmethod
    def _from_encoded(cls, encoded: bytes) -> APDUCommand:
        parsed = _native_call(_native().apdu_parse_command, encoded)
        return cls(
            cla=int(parsed["cla"]),
            ins=int(parsed["ins"]),
            p1=int(parsed["p1"]),
            p2=int(parsed["p2"]),
            data=bytes(parsed["data"]) if parsed["data"] is not None else None,
            le=int(parsed["le"]) if parsed["le"] is not None else None,
        )

    @classmethod
    def select_file(cls, file_id: bytes | int, select_type: int = 0x00) -> APDUCommand:
        if isinstance(file_id, int):
            if not 0 <= file_id <= 0xFFFF:
                raise ValueError("File identifier must be an unsigned 16-bit integer")
            file_id = file_id.to_bytes(2, "big")
        return cls(0, APDUInstruction.SELECT.value, select_type, 0x0C, file_id)

    @classmethod
    def read_binary(cls, offset: int, length: int) -> APDUCommand:
        if not 0 <= offset <= 0xFFFF:
            raise ValueError("READ BINARY offset must be an unsigned 16-bit integer")
        return cls(
            0,
            APDUInstruction.READ_BINARY.value,
            (offset >> 8) & 0xFF,
            offset & 0xFF,
            le=length,
        )

    @classmethod
    def get_challenge(cls, length: int = 8) -> APDUCommand:
        return cls(0, APDUInstruction.GET_CHALLENGE.value, 0, 0, le=length)

    @classmethod
    def mutual_authenticate(cls, payload: bytes) -> APDUCommand:
        return cls(0, APDUInstruction.EXTERNAL_AUTHENTICATE.value, 0, 0, payload)

    @classmethod
    def general_authenticate(
        cls, payload: bytes, p1: int = 0x00, p2: int = 0x00
    ) -> APDUCommand:
        return cls(0, APDUInstruction.GENERAL_AUTHENTICATE.value, p1, p2, payload)


@dataclass
class APDUResponse:
    """Stable response model parsed and classified by Rust."""

    data: bytes
    sw1: int
    sw2: int

    def _classification(self) -> dict:
        return _native_call(
            _native().apdu_parse_response, self.data + bytes((self.sw1, self.sw2))
        )

    @property
    def sw(self) -> int:
        return int(self._classification()["sw"])

    @property
    def is_success(self) -> bool:
        return bool(self._classification()["is_success"])

    @property
    def is_warning(self) -> bool:
        return bool(self._classification()["is_warning"])

    @property
    def is_error(self) -> bool:
        return bool(self._classification()["is_error"])

    @property
    def status_description(self) -> str:
        return str(self._classification()["status_description"])

    @classmethod
    def from_bytes(cls, response: bytes) -> APDUResponse:
        parsed = _native_call(_native().apdu_parse_response, response)
        return cls(bytes(parsed["data"]), int(parsed["sw1"]), int(parsed["sw2"]))


class APDUProcessor:
    """High-level command construction and response logging adapter."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def build_select_application(self, aid: bytes) -> APDUCommand:
        return APDUCommand(0, APDUInstruction.SELECT.value, 0x04, 0x0C, aid)

    def build_select_ef(self, ef_id: int) -> APDUCommand:
        return APDUCommand.select_file(ef_id, select_type=0x02)

    def build_read_ef(self, length: int, offset: int = 0) -> list[APDUCommand]:
        commands = _native_call(
            _native().apdu_build_read_binary_commands, length, offset
        )
        return [APDUCommand._from_encoded(bytes(command)) for command in commands]

    def validate_response(self, response: APDUResponse) -> bool:
        if response.is_success:
            return True
        if response.is_warning:
            self.logger.warning("APDU warning: %s", response.status_description)
            return True
        self.logger.error("APDU error: %s", response.status_description)
        return False


class PassportAPDU(APDUProcessor):
    """Common electronic-passport commands and file identifiers."""

    PASSPORT_AID = bytes.fromhex("A0000002471001")
    EF_COM = 0x011E
    EF_SOD = 0x011D
    EF_DG1 = 0x0101
    EF_DG2 = 0x0102
    EF_DG3 = 0x0103
    EF_DG4 = 0x0104
    EF_DG14 = 0x010E
    EF_DG15 = 0x010F

    @classmethod
    def select_passport_application(cls) -> APDUCommand:
        return APDUCommand(0, APDUInstruction.SELECT.value, 0x04, 0x0C, cls.PASSPORT_AID)

    @classmethod
    def select_data_group(cls, dg_number: int) -> APDUCommand:
        file_id = _native_call(_native().passport_data_group_file_id, dg_number)
        return APDUCommand.select_file(int(file_id), select_type=0x02)
