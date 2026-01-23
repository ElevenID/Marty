"""
Event Handlers for Digital Identity

Subscribes to domain events and performs side effects like audit logging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from digital_identity.domain.entities import AuditEvent
from digital_identity.domain.events import (
    DomainEvent,
    FlowCreatedEvent,
    FlowUpdatedEvent,
    FlowDeletedEvent,
    FlowStartedEvent,
    FlowStepCompletedEvent,
    FlowAwaitingApprovalEvent,
    FlowApprovedEvent,
    FlowRejectedEvent,
    FlowCompletedEvent,
    FlowFailedEvent,
    FlowCancelledEvent,
)

logger = logging.getLogger(__name__)


class AuditEventHandler:
    """
    Handler that converts domain events into audit events for compliance.
    
    Subscribes to all Flow-related domain events and persists them
    to the audit log via the AuditEventRepository.
    
    This provides:
    - Immutable audit trail for compliance
    - Event correlation via execution_id
    - Queryable history by entity type and ID
    """
    
    def __init__(self, audit_repository: Any):  # AuditEventRepositoryPort
        """
        Initialize audit event handler.
        
        Args:
            audit_repository: Repository for persisting audit events
        """
        self._audit_repository = audit_repository
    
    async def handle_event(self, event: DomainEvent) -> None:
        """
        Handle a domain event by creating an audit record.
        
        Args:
            event: The domain event to audit
        """
        try:
            # Map event to audit event
            audit_event = self._map_to_audit_event(event)
            
            if audit_event:
                await self._audit_repository.save(audit_event)
                logger.debug(f"Audited event: {event.event_type} for {audit_event.entity_id}")
        
        except Exception as e:
            # Don't fail the main operation if audit logging fails
            logger.error(f"Failed to audit event {event.event_type}: {e}")
    
    def _map_to_audit_event(self, event: DomainEvent) -> AuditEvent | None:
        """
        Map a domain event to an audit event.
        
        Args:
            event: The domain event
            
        Returns:
            AuditEvent or None if event type not audited
        """
        # Flow lifecycle events
        if isinstance(event, FlowCreatedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="Flow",
                entity_id=event.flow_id,
                action="created",
                payload={
                    "name": event.name,
                    "flow_type": event.flow_type.value if hasattr(event.flow_type, "value") else str(event.flow_type),
                },
                occurred_at=event.occurred_at,
                correlation_id=event.flow_id,
            )
        
        elif isinstance(event, FlowUpdatedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="Flow",
                entity_id=event.flow_id,
                action="updated",
                payload={
                    "changes": event.changes,
                },
                occurred_at=event.occurred_at,
                correlation_id=event.flow_id,
            )
        
        elif isinstance(event, FlowDeletedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="Flow",
                entity_id=event.flow_id,
                action="deleted",
                payload={
                    "name": event.name,
                },
                occurred_at=event.occurred_at,
                correlation_id=event.flow_id,
            )
        
        # Flow execution events
        elif isinstance(event, FlowStartedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="FlowExecution",
                entity_id=event.execution_id,
                action="started",
                payload={
                    "flow_id": event.flow_id,
                    "flow_type": event.flow_type.value if hasattr(event.flow_type, "value") else str(event.flow_type),
                    "context": event.context,
                },
                occurred_at=event.occurred_at,
                correlation_id=event.execution_id,
            )
        
        elif isinstance(event, FlowStepCompletedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="FlowExecution",
                entity_id=event.execution_id,
                action="step_completed",
                payload={
                    "flow_id": event.flow_id,
                    "step_name": event.step_name,
                    "step_index": event.step_index,
                    "result": event.result,
                },
                occurred_at=event.occurred_at,
                correlation_id=event.execution_id,
            )
        
        elif isinstance(event, FlowAwaitingApprovalEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="FlowExecution",
                entity_id=event.execution_id,
                action="awaiting_approval",
                payload={
                    "flow_id": event.flow_id,
                    "step_name": event.step_name,
                    "context_data": event.context_data,
                },
                occurred_at=event.occurred_at,
                correlation_id=event.execution_id,
            )
        
        elif isinstance(event, FlowApprovedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="FlowExecution",
                entity_id=event.execution_id,
                action="approved",
                payload={
                    "flow_id": event.flow_id,
                    "approved_by": event.approved_by,
                    "reason": event.reason,
                },
                occurred_at=event.occurred_at,
                actor_id=event.approved_by,
                correlation_id=event.execution_id,
            )
        
        elif isinstance(event, FlowRejectedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="FlowExecution",
                entity_id=event.execution_id,
                action="rejected",
                payload={
                    "flow_id": event.flow_id,
                    "rejected_by": event.rejected_by,
                    "reason": event.reason,
                },
                occurred_at=event.occurred_at,
                actor_id=event.rejected_by,
                correlation_id=event.execution_id,
            )
        
        elif isinstance(event, FlowCompletedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="FlowExecution",
                entity_id=event.execution_id,
                action="completed",
                payload={
                    "flow_id": event.flow_id,
                    "flow_type": event.flow_type.value if hasattr(event.flow_type, "value") else str(event.flow_type),
                    "results": event.results,
                },
                occurred_at=event.occurred_at,
                correlation_id=event.execution_id,
            )
        
        elif isinstance(event, FlowFailedEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="FlowExecution",
                entity_id=event.execution_id,
                action="failed",
                payload={
                    "flow_id": event.flow_id,
                    "flow_type": event.flow_type.value if hasattr(event.flow_type, "value") else str(event.flow_type),
                    "error": event.error,
                    "step_name": event.step_name,
                },
                occurred_at=event.occurred_at,
                correlation_id=event.execution_id,
            )
        
        elif isinstance(event, FlowCancelledEvent):
            return AuditEvent(
                event_type=event.event_type,
                entity_type="FlowExecution",
                entity_id=event.execution_id,
                action="cancelled",
                payload={
                    "flow_id": event.flow_id,
                    "cancelled_by": event.cancelled_by,
                    "reason": event.reason,
                },
                occurred_at=event.occurred_at,
                actor_id=event.cancelled_by,
                correlation_id=event.execution_id,
            )
        
        else:
            # Unknown event type - don't audit
            logger.debug(f"Event type {event.event_type} not configured for audit logging")
            return None
