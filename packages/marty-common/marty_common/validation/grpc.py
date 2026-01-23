"""Utilities to validate protobuf requests with Pydantic models."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

SchemaT = TypeVar("SchemaT", bound=BaseModel)

logger = logging.getLogger(__name__)


class RequestValidationError(Exception):
    """Raised when an inbound gRPC request fails schema validation."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self._errors = errors
        message = "; ".join(self._format_error(err) for err in errors)
        super().__init__(message or "Invalid request payload")

    @property
    def errors(self) -> list[dict[str, Any]]:
        return self._errors

    def details_map(self) -> dict[str, str]:
        """Collapse validation issues into a flat mapping for error payloads."""

        details: dict[str, str] = {}
        for err in self._errors:
            location = ".".join(str(part) for part in err.get("loc", ())) or "__root__"
            details[location] = err.get("msg", "invalid value")
        return details

    @staticmethod
    def _format_error(error: dict[str, Any]) -> str:
        location = ".".join(str(part) for part in error.get("loc", ())) or "field"
        message = error.get("msg", "Invalid value")
        return f"{location}: {message}"


def validate_request(schema: type[SchemaT], raw: Any) -> SchemaT:
    """Validate a protobuf message using the supplied Pydantic schema."""

    try:
        return schema.model_validate(raw, from_attributes=True)
    except ValidationError as exc:
        logger.debug("Request validation failed for %s: %s", schema.__name__, exc)
        raise RequestValidationError(exc.errors()) from exc
