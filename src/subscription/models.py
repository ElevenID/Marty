"""
Subscription Models

SQLAlchemy models for multi-tenant subscription management.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class SubscriptionStatus(str, Enum):
    """Subscription status values."""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    TRIALING = "trialing"


class Organization(Base):
    """
    Organization (tenant) in the multi-tenant system.
    
    Each organization has:
    - One or more subscriptions
    - Multiple API keys
    - Webhook endpoints
    - Usage records
    """
    __tablename__ = "organizations"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    
    # Square integration
    square_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Organization settings
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription",
        back_populates="organization",
        lazy="selectin",
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="organization",
        lazy="selectin",
    )
    webhook_endpoints: Mapped[list["WebhookEndpoint"]] = relationship(
        "WebhookEndpoint",
        back_populates="organization",
        lazy="selectin",
    )


class Subscription(Base):
    """
    Subscription for an organization.
    
    Tracks:
    - Current plan and status
    - Usage limits and counters
    - Billing period
    - Square subscription ID
    """
    __tablename__ = "subscriptions"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Plan info
    plan: Mapped[str] = mapped_column(String(50), nullable=False)  # free, starter, professional, enterprise
    status: Mapped[SubscriptionStatus] = mapped_column(
        String(20),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )
    
    # Square integration
    square_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Usage limits
    api_calls_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    api_calls_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Billing period
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="subscriptions",
    )
    usage_records: Mapped[list["UsageRecord"]] = relationship(
        "UsageRecord",
        back_populates="subscription",
        lazy="selectin",
    )


class APIKey(Base):
    """
    API key for authenticating requests.
    
    Features:
    - Scoped access control
    - IP allowlisting
    - Usage tracking
    - Revocation support
    """
    __tablename__ = "api_keys"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Key identification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)  # For identification
    
    # Permissions
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    
    # IP restrictions
    ip_allowlist: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    
    # Flags
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Lifecycle
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="api_keys",
    )


class WebhookEndpoint(Base):
    """
    Webhook endpoint for receiving event notifications.
    
    Features:
    - Event type filtering
    - HMAC signature verification
    - Retry tracking
    - Circuit breaker state
    """
    __tablename__ = "webhook_endpoints"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Endpoint configuration
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(64), nullable=False)  # For HMAC signing
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Event filtering
    event_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    
    # Status
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Circuit breaker state
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="webhook_endpoints",
    )


class UsageRecord(Base):
    """
    Detailed API usage record for analytics and billing.
    
    Tracks:
    - Endpoint usage
    - Request counts
    - Timestamps for aggregation
    """
    __tablename__ = "usage_records"
    
    id: Mapped[UUID] = mapped_column(primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Usage details
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Timestamps
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    
    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        back_populates="usage_records",
    )
