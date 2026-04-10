"""
Structured audit logging for KMS operations.

Configures the ``kms_audit`` logger with a JSON formatter that emits
machine-readable audit records.  Every log record is guaranteed to
include:
- ``timestamp`` (ISO-8601)
- ``level``
- ``event`` (the log message)
- ``logger``
- Any ``extra`` fields passed via the ``extra=`` kwarg

Usage (callsites remain unchanged)::

    audit_logger = logging.getLogger("kms_audit")
    audit_logger.info("KMS configured", extra={
        "user_id": "u-123",
        "org_id": "o-456",
        "provider": "aws_kms",
    })

Call :func:`configure_audit_logging` once at application startup (e.g.
inside ``register_routes``).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


class _JSONAuditFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    Standard fields (``timestamp``, ``level``, ``logger``, ``event``)
    are always present.  All user-supplied ``extra`` keys are merged
    at the top level, *except* internal Python logging keys.
    """

    _INTERNAL_KEYS = frozenset({
        "args", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module",
        "msecs", "message", "msg", "name", "pathname", "process",
        "processName", "relativeCreated", "stack_info", "taskName",
        "thread", "threadName",
    })

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }

        # Merge user-provided extra keys
        for key, value in record.__dict__.items():
            if key not in self._INTERNAL_KEYS and key not in entry:
                try:
                    json.dumps(value)  # only include JSON-serialisable values
                    entry[key] = value
                except (TypeError, ValueError):
                    entry[key] = str(value)

        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


def configure_audit_logging(
    *,
    log_file: str | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Attach a JSON handler to the ``kms_audit`` logger.

    Parameters
    ----------
    log_file:
        Path to the audit log file.  Defaults to ``KMS_AUDIT_LOG_FILE``
        env var.  When **None** / empty, a :class:`logging.StreamHandler`
        writing to *stderr* is used instead.
    level:
        Minimum severity to record.

    Returns
    -------
    The configured ``kms_audit`` logger.
    """
    audit_logger = logging.getLogger("kms_audit")

    # Avoid double-attachment when ``configure_audit_logging`` is
    # called more than once (e.g. in tests).
    if any(isinstance(h, (logging.FileHandler, logging.StreamHandler))
           and isinstance(h.formatter, _JSONAuditFormatter)
           for h in audit_logger.handlers):
        return audit_logger

    audit_logger.setLevel(level)

    log_file = log_file or os.getenv("KMS_AUDIT_LOG_FILE")
    if log_file:
        handler: logging.Handler = logging.FileHandler(log_file, encoding="utf-8")
    else:
        handler = logging.StreamHandler()

    handler.setFormatter(_JSONAuditFormatter())
    audit_logger.addHandler(handler)

    return audit_logger
