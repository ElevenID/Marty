"""
Domain Events Module

Provides typed domain events and event publishing infrastructure.
Built on top of MMF messaging for reliable delivery.
"""
from .domain_events import DomainEvent, DomainEventType
from .publisher import DomainEventPublisher

__all__ = [
    "DomainEvent",
    "DomainEventType",
    "DomainEventPublisher",
]
