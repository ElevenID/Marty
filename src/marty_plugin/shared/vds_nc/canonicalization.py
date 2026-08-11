"""Compatibility adapter for Rust-owned VDS-NC canonicalization."""

from __future__ import annotations

from typing import Any

from marty_common.native_backends import NativeBackendError

from .native import canonicalize_profile
from .types import CanonicalizeError, DocumentType


class VDSNCCanonicalizer:
    """Preserve the Python API while delegating canonicalization to Rust."""

    @staticmethod
    def canonicalize(data: dict[str, Any], doc_type: DocumentType) -> str:
        try:
            return canonicalize_profile(doc_type.value, data)
        except NativeBackendError as exc:
            raise CanonicalizeError(str(exc)) from exc

    @staticmethod
    def validate_canonicalization_drift(
        original_canonical: str,
        new_data: dict[str, Any],
        doc_type: DocumentType,
    ) -> list[str]:
        try:
            current = canonicalize_profile(doc_type.value, new_data)
        except NativeBackendError as exc:
            return [f"Canonicalization validation failed: {exc}"]
        if current != original_canonical:
            return ["Canonicalization drift detected: original != new"]
        return []
