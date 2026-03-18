"""
Verification Session Service

Application service for VerificationSession lifecycle management.
Status states: PENDING → AWAITING_PRESENTATION → VERIFYING → PASSED | FAILED
               Any → EXPIRED | CANCELLED
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from digital_identity.domain.entities import VerificationSession

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {"PASSED", "FAILED", "EXPIRED", "CANCELLED"}
_VALID_STATUSES = {
    "PENDING",
    "AWAITING_PRESENTATION",
    "VERIFYING",
    "PASSED",
    "FAILED",
    "EXPIRED",
    "CANCELLED",
}


class VerificationSessionService:
    """Service for Verification Session management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        flow_id: str,
        presentation_policy_id: str,
        flow_instance_id: str | None = None,
        deployment_profile_id: str | None = None,
        verifier_nonce: str | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VerificationSession:
        """Create a new Verification Session in PENDING state."""
        session = VerificationSession(
            flow_id=flow_id,
            presentation_policy_id=presentation_policy_id,
            flow_instance_id=flow_instance_id,
            deployment_profile_id=deployment_profile_id,
            verifier_nonce=verifier_nonce,
            status="PENDING",
            expires_at=expires_at,
            metadata=metadata or {},
        )
        saved = await self._repository.save(session)
        logger.info(f"Created Verification Session: {saved.id} (flow={flow_id})")
        return saved

    async def get(self, session_id: str) -> VerificationSession | None:
        """Get a Verification Session by ID."""
        return await self._repository.get(session_id)

    async def list_by_flow(
        self,
        flow_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[VerificationSession]:
        """List sessions for a specific flow."""
        return await self._repository.list_by_flow(flow_id, skip=skip, limit=limit)

    async def list_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[VerificationSession]:
        """List sessions by lifecycle status."""
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Valid: {_VALID_STATUSES}")
        return await self._repository.list_by_status(status, skip=skip, limit=limit)

    async def update(
        self,
        session_id: str,
        **updates: Any,
    ) -> VerificationSession | None:
        """Update a Verification Session (status transitions, result, holder_id)."""
        session = await self._repository.get(session_id)
        if not session:
            return None

        new_status = updates.get("status")
        if new_status is not None:
            if new_status not in _VALID_STATUSES:
                raise ValueError(f"Invalid status '{new_status}'. Valid: {_VALID_STATUSES}")
            if session.status in _TERMINAL_STATUSES:
                raise ValueError(
                    f"Cannot transition session from terminal status '{session.status}'"
                )
            session.status = new_status
            if new_status in ("PASSED", "FAILED", "EXPIRED", "CANCELLED"):
                session.completed_at = datetime.now(timezone.utc)

        for key in ("holder_id", "result", "error", "expires_at", "completed_at"):
            if key in updates and updates[key] is not None:
                setattr(session, key, updates[key])

        session.touch()
        saved = await self._repository.save(session)
        logger.info(f"Updated Verification Session: {session_id} status={session.status}")
        return saved

    async def delete(self, session_id: str) -> bool:
        """Delete a Verification Session."""
        existing = await self._repository.get(session_id)
        if not existing:
            return False
        result = await self._repository.delete(session_id)
        logger.info(f"Deleted Verification Session: {session_id}")
        return result
