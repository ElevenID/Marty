"""Service for handling PKD synchronization operations."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.db.database import DatabaseManager
from app.models.pkd_models import (
    ComponentSyncStatus,
    PkdSyncRequest,
    PkdSyncResponse,
    PkdSyncStatusResponse,
    SyncStatus,
)
from app.services.pkd_mirror_service import PKDMirrorService

logger = logging.getLogger(__name__)


class SyncService:
    """Service for coordinating PKD mirror synchronisation runs."""

    def __init__(self, pkd_mirror: PKDMirrorService | None = None) -> None:
        pkd_url = settings.EXTERNAL_PKD_URL or "https://pkddownloadsg.icao.int"
        self.pkd_mirror = pkd_mirror or PKDMirrorService(pkd_url=pkd_url)
        self._sync_jobs: dict[str, PkdSyncStatusResponse] = {}

    async def initiate_sync(self, request: PkdSyncRequest) -> PkdSyncResponse:
        """Kick off a background sync job for the requested PKD components."""

        sync_id = str(uuid.uuid4())
        now = datetime.now()

        normalized, invalid = self._normalise_components(request.components)
        if not normalized and invalid:
            # No valid components to run; return immediate failure status
            status = PkdSyncStatusResponse(
                id=sync_id,
                status=SyncStatus.FAILED,
                start_time=now,
                end_time=now,
                components={comp.lower(): ComponentSyncStatus.FAILED for comp in invalid},
                error_message="No recognised PKD components in request",
            )
            self._sync_jobs[sync_id] = status
            await DatabaseManager.store_sync_job(
                {
                    "id": sync_id,
                    "status": SyncStatus.FAILED.value,
                    "sync_source": request.sync_source,
                    "start_time": now,
                    "end_time": now,
                    "components": [comp.lower() for comp in invalid],
                    "error_message": status.error_message,
                }
            )
            return PkdSyncResponse(id=sync_id, status=SyncStatus.FAILED, start_time=now)

        component_statuses: dict[str, ComponentSyncStatus] = dict.fromkeys(
            normalized, ComponentSyncStatus.PENDING
        )
        for invalid_component in invalid:
            component_statuses[invalid_component.lower()] = ComponentSyncStatus.FAILED

        status = PkdSyncStatusResponse(
            id=sync_id,
            status=SyncStatus.INITIATED,
            start_time=now,
            components=component_statuses,
        )
        self._sync_jobs[sync_id] = status

        await DatabaseManager.store_sync_job(
            {
                "id": sync_id,
                "status": SyncStatus.INITIATED.value,
                "sync_source": request.sync_source,
                "start_time": now,
                "components": normalized or list(component_statuses.keys()),
            }
        )

        asyncio.create_task(self._perform_sync(sync_id, request, normalized, invalid))
        return PkdSyncResponse(id=sync_id, status=SyncStatus.INITIATED, start_time=now)

    async def get_sync_status(self, sync_id: str | None = None) -> PkdSyncStatusResponse:
        """Return the status for a specific or the most recent sync job."""

        if self._sync_jobs:
            if sync_id is None:
                sync_id = list(self._sync_jobs.keys())[-1]
            job = self._sync_jobs.get(sync_id)
            if job:
                return job

        job_data: dict[str, Any] | None
        if sync_id is None:
            job_data = await DatabaseManager.get_latest_sync_job()
        else:
            job_data = await DatabaseManager.get_sync_job(sync_id)

        if job_data:
            return self._convert_db_job(job_data)

        if sync_id is not None:
            msg = f"Sync job with ID {sync_id} not found"
            raise ValueError(msg)

        return PkdSyncStatusResponse(
            id="00000000-0000-0000-0000-000000000000",
            status=SyncStatus.NOT_STARTED,
        )

    async def _perform_sync(
        self,
        sync_id: str,
        request: PkdSyncRequest,
        components: list[str],
        invalid: list[str],
    ) -> None:
        """Run the PKD mirror synchronisation in the background."""

        status = self._sync_jobs.get(sync_id)
        if status is None:
            logger.error("Sync job with ID %s not found", sync_id)
            return

        status.status = SyncStatus.IN_PROGRESS
        await DatabaseManager.update_sync_job(sync_id, {"status": SyncStatus.IN_PROGRESS.value})

        # Mark invalid components as failed upfront
        failed_components: list[str] = []
        for invalid_component in invalid:
            key = invalid_component.lower()
            status.components[key] = ComponentSyncStatus.FAILED
            failed_components.append(key)

        try:
            if components:
                results = await asyncio.to_thread(self.pkd_mirror.sync_components, components)
                for component in components:
                    success = results.get(component, False)
                    comp_status = (
                        ComponentSyncStatus.COMPLETED if success else ComponentSyncStatus.FAILED
                    )
                    status.components[component] = comp_status
                    if not success:
                        failed_components.append(component)
            else:
                status.error_message = "No valid PKD components supplied for synchronisation"

        except Exception as exc:  # pragma: no cover - defensive guard around network IO
            logger.exception("PKD sync task %s failed: %s", sync_id, exc)
            status.error_message = str(exc)
            failed_components.extend(
                component for component in components if component not in failed_components
            )

        end_time = datetime.now()
        status.end_time = end_time

        if failed_components:
            status.status = SyncStatus.FAILED
            if not status.error_message:
                status.error_message = "Failed components: " + ", ".join(
                    sorted(set(failed_components))
                )
        elif components:
            status.status = SyncStatus.COMPLETED
        else:
            status.status = SyncStatus.FAILED

        await DatabaseManager.update_sync_job(
            sync_id,
            {
                "status": status.status.value,
                "end_time": end_time,
                "error_message": status.error_message,
            },
        )

    def _normalise_components(self, components: list[str] | None) -> tuple[list[str], list[str]]:
        """Map request components to canonical identifiers."""

        requested = components or ["csca", "dsc", "crl"]
        normalised: list[str] = []
        invalid: list[str] = []
        seen: set[str] = set()

        for entry in requested:
            canonical = self.pkd_mirror.resolve_component(entry)
            if canonical is None:
                invalid.append(entry)
                continue
            if canonical not in seen:
                seen.add(canonical)
                normalised.append(canonical)

        return normalised, invalid

    def _convert_db_job(self, job: dict[str, Any]) -> PkdSyncStatusResponse:
        """Convert a stored sync job into an API response."""

        sync_status = SyncStatus(job["status"])
        if sync_status == SyncStatus.COMPLETED:
            default_component_status = ComponentSyncStatus.COMPLETED
        elif sync_status == SyncStatus.IN_PROGRESS:
            default_component_status = ComponentSyncStatus.IN_PROGRESS
        elif sync_status == SyncStatus.FAILED:
            default_component_status = ComponentSyncStatus.FAILED
        else:
            default_component_status = ComponentSyncStatus.PENDING

        components = dict.fromkeys(job.get("components", []), default_component_status)

        return PkdSyncStatusResponse(
            id=job["id"],
            status=sync_status,
            start_time=job.get("start_time"),
            end_time=job.get("end_time"),
            components=components,
            error_message=job.get("error_message"),
        )
