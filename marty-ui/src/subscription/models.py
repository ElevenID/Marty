"""Subscription and organization SQLAlchemy models.

This module defines the data models for multi-tenant subscription management,
including organizations, subscriptions, API keys, webhooks, and usage tracking.
"""

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class SubscriptionTier(str, enum.Enum):
    """Available subscription tiers."""

    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class BillingPeriod(str, enum.Enum):
    """Billing period options."""

    MONTHLY = "monthly"
    YEARLY = "yearly"


class PaymentStatus(str, enum.Enum):
    """Payment status values."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class MemberRole(str, enum.Enum):
    """Organization member roles."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class APIKeyScope(str, enum.Enum):
    """API key permission scopes."""

    READ_CREDENTIALS = "read:credentials"
    WRITE_CREDENTIALS = "write:credentials"
    READ_TRUST_REGISTRY = "read:trust_registry"
    WRITE_TRUST_REGISTRY = "write:trust_registry"
    READ_REVOCATION = "read:revocation"
    WRITE_REVOCATION = "write:revocation"
    MANAGE_WEBHOOKS = "manage:webhooks"
    MANAGE_ORGANIZATION = "manage:organization"
    FULL_ACCESS = "full_access"


class UsageMetric(str, enum.Enum):
    """Types of usage metrics to track."""

    API_CALLS = "api_calls"
    CREDENTIALS_ISSUED = "credentials_issued"
    CREDENTIALS_VERIFIED = "credentials_verified"
    WEBHOOKS_DELIVERED = "webhooks_delivered"
    STORAGE_BYTES = "storage_bytes"
    ACTIVE_CREDENTIALS = "active_credentials"


class MembershipMode(str, enum.Enum):
    """How users can join an organization."""
    
    INVITE_ONLY = "invite_only"      # Only via email invitation from Keycloak
    APPROVAL_REQUIRED = "approval"   # Users can request, admin must approve
    OPEN = "open"                    # Anyone can join directly


class MembershipRequestStatus(str, enum.Enum):
    """Status of a membership request."""
    
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Organization(Base):
    """Organization (tenant) model.

    An organization represents a customer account that can have
    multiple users, API keys, and webhooks.

    Attributes:
        id: Unique organization identifier
        name: Organization display name
        slug: URL-friendly unique identifier
        square_customer_id: Square customer ID for billing
        subscription_tier: Current subscription tier
        is_active: Whether the organization is active
        settings: JSON blob for org-specific settings
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    square_customer_id = Column(String(100), unique=True, nullable=True)

    subscription_tier = Column(
        SQLEnum(SubscriptionTier),
        default=SubscriptionTier.FREE,
        nullable=False,
    )

    is_active = Column(Boolean, default=True, nullable=False)
    settings = Column(JSON, default=dict)

    # Discoverability and membership settings
    is_discoverable = Column(Boolean, default=False, nullable=False)  # Show in public org list
    membership_mode = Column(
        SQLEnum(MembershipMode),
        default=MembershipMode.INVITE_ONLY,
        nullable=False,
    )

    # Contact information
    contact_email = Column(String(255), nullable=True)
    contact_name = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="organization", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="organization", cascade="all, delete-orphan")
    webhooks = relationship("WebhookEndpoint", back_populates="organization", cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="organization", cascade="all, delete-orphan")
    credential_configs = relationship("CredentialTypeConfiguration", back_populates="organization", cascade="all, delete-orphan")
    invitations = relationship("OrganizationInvitation", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name={self.name}, tier={self.subscription_tier})>"

    @property
    def active_subscription(self) -> Optional["Subscription"]:
        """Get the current active subscription."""
        for sub in self.subscriptions:
            if sub.is_active and (sub.ends_at is None or sub.ends_at > datetime.utcnow()):
                return sub
        return None


class OrganizationMember(Base):
    """Organization member model.

    Links users to organizations with specific roles.

    Attributes:
        id: Unique member record ID
        organization_id: Parent organization ID
        user_id: Keycloak user ID
        role: Member's role in the organization
        is_active: Whether the membership is active
        invited_at: When the invitation was sent
        joined_at: When the user accepted the invitation
    """

    __tablename__ = "organization_members"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(String(36), nullable=False)

    role = Column(SQLEnum(MemberRole), default=MemberRole.MEMBER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    invited_by = Column(String(36), nullable=True)
    invited_at = Column(DateTime, nullable=True)
    joined_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="members")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_user"),
    )

    def __repr__(self) -> str:
        return f"<OrganizationMember(org={self.organization_id}, user={self.user_id}, role={self.role})>"


class MembershipRequest(Base):
    """Membership request model.

    Tracks requests from users to join organizations that require approval.

    Attributes:
        id: Unique request ID
        organization_id: Target organization ID
        user_id: Keycloak user ID of requester
        user_email: Email of requester (for display)
        status: Request status (pending, approved, rejected, cancelled)
        message: Optional message from requester
        reviewed_by: User ID of admin who reviewed the request
        reviewed_at: When the request was reviewed
        rejection_reason: Reason for rejection (if rejected)
    """

    __tablename__ = "membership_requests"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(String(36), nullable=False)
    user_email = Column(String(255), nullable=False)

    status = Column(
        SQLEnum(MembershipRequestStatus),
        default=MembershipRequestStatus.PENDING,
        nullable=False,
    )

    message = Column(Text, nullable=True)  # Optional message from requester
    reviewed_by = Column(String(36), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_user_request"),
    )

    def __repr__(self) -> str:
        return f"<MembershipRequest(org={self.organization_id}, user={self.user_email}, status={self.status})>"


class CredentialType(str, enum.Enum):
    """Types of credentials that can be configured for issuance."""
    
    TRAVEL_VISA = "travel_visa"
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"  # mDL
    ACCESS_BADGE = "access_badge"
    NATIONAL_ID = "national_id"


class CredentialTypeConfiguration(Base):
    """Credential type configuration model.

    Defines which credential types an organization can issue and
    the required/optional fields for each type.

    Attributes:
        id: Unique configuration ID
        organization_id: Parent organization ID
        credential_type: Type of credential
        display_name: Human-readable name for this configuration
        doctype: Document type identifier (e.g., org.iso.18013.5.1.mDL)
        required_fields: JSON list of required field names
        optional_fields: JSON list of optional field names
        validity_days: How long credentials are valid (default 365)
        is_active: Whether this configuration is active
    """

    __tablename__ = "credential_type_configurations"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    
    credential_type = Column(SQLEnum(CredentialType), nullable=False)
    display_name = Column(String(255), nullable=False)
    doctype = Column(String(255), nullable=True)  # e.g., org.iso.18013.5.1.mDL
    
    # Field configuration
    required_fields = Column(JSON, default=list)  # ["given_name", "family_name", "birth_date"]
    optional_fields = Column(JSON, default=list)  # ["portrait", "nationality"]
    
    # Validity
    validity_days = Column(Integer, default=365, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="credential_configs")
    
    __table_args__ = (
        UniqueConstraint("organization_id", "credential_type", name="uq_org_credential_type"),
    )
    
    def __repr__(self) -> str:
        return f"<CredentialTypeConfiguration(org={self.organization_id}, type={self.credential_type})>"


class OrganizationInvitation(Base):
    """Organization invitation model.

    Tracks invite codes and email-based invitations for organizations.

    Attributes:
        id: Unique invitation ID
        organization_id: Parent organization ID
        code: Unique invite code (8 chars alphanumeric)
        email: Specific email if personalized invitation
        role: Role to assign when invitation is accepted
        is_reusable: Whether code can be used multiple times
        max_uses: Maximum number of uses (null = unlimited for reusable)
        uses_count: Current number of uses
        expires_at: When the invitation expires
        created_by: User ID who created the invitation
    """

    __tablename__ = "organization_invitations"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)
    
    code = Column(String(16), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)  # null = generic invite code
    
    role = Column(SQLEnum(MemberRole), default=MemberRole.MEMBER, nullable=False)
    
    # Usage limits
    is_reusable = Column(Boolean, default=True, nullable=False)
    max_uses = Column(Integer, nullable=True)  # null = unlimited
    uses_count = Column(Integer, default=0, nullable=False)
    
    # Validity
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Tracking
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="invitations")
    
    def __repr__(self) -> str:
        return f"<OrganizationInvitation(org={self.organization_id}, code={self.code})>"
    
    @property
    def is_valid(self) -> bool:
        """Check if invitation is still valid."""
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        if self.max_uses and self.uses_count >= self.max_uses:
            return False
        return True


class DeviceRegistration(Base):
    """Device registration model.

    Tracks registered devices for push notifications and credential storage.

    Attributes:
        id: Unique device registration ID
        device_id: Device-provided unique identifier
        user_id: Keycloak user ID who owns the device
        fcm_token: Firebase Cloud Messaging token
        platform: Device platform (ios, android, web)
        app_version: App version string
        os_version: OS version string
        device_model: Device model name
        public_key: DER-encoded RSA public key (base64) for challenge signing
        key_id: Computed key ID (SHA-256 hash prefix) for key lookup
        is_active: Whether device is active
    """

    __tablename__ = "device_registrations"

    id = Column(String(36), primary_key=True)
    device_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    
    # Push notification token
    fcm_token = Column(String(512), nullable=True)
    
    # Device info
    platform = Column(String(20), nullable=False)  # ios, android, web
    app_version = Column(String(50), nullable=True)
    os_version = Column(String(50), nullable=True)
    device_model = Column(String(100), nullable=True)
    
    # Cryptographic key for push challenge signing
    public_key = Column(Text, nullable=True)  # Base64-encoded DER public key
    key_id = Column(String(32), nullable=True, index=True)  # First 16 chars of SHA-256 hex
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f"<DeviceRegistration(device={self.device_id}, user={self.user_id}, platform={self.platform})>"


class PushChallengeStatus(str, enum.Enum):
    """Status of a push challenge."""
    
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PushChallenge(Base):
    """Push challenge model.

    Tracks push notification challenges sent to devices for authentication
    or credential operations.

    Attributes:
        id: Unique challenge ID
        device_id: Target device ID
        title: Challenge title for display
        question: Challenge question/prompt
        nonce: Random nonce for signing
        credential_id: Optional associated credential ID
        status: Challenge status
        response_signature: Base64-encoded signature from device
        expires_at: When challenge expires
    """

    __tablename__ = "push_challenges"

    id = Column(String(36), primary_key=True)
    device_id = Column(String(255), ForeignKey("device_registrations.device_id"), nullable=False)
    
    # Challenge content
    title = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    nonce = Column(String(64), nullable=False)
    
    # Optional credential reference
    credential_id = Column(String(36), nullable=True)
    
    # Optional additional data (JSON)
    data = Column(JSON, nullable=True)
    
    # Status and response
    status = Column(
        SQLEnum(PushChallengeStatus),
        default=PushChallengeStatus.PENDING,
        nullable=False,
    )
    response_signature = Column(Text, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    
    # Validity
    expires_at = Column(DateTime, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    device = relationship("DeviceRegistration")
    
    def __repr__(self) -> str:
        return f"<PushChallenge(id={self.id}, device={self.device_id}, status={self.status})>"
    
    @property
    def is_expired(self) -> bool:
        """Check if challenge has expired."""
        return datetime.utcnow() > self.expires_at


class Subscription(Base):
    """Subscription model.

    Tracks billing subscriptions for organizations.

    Attributes:
        id: Unique subscription ID
        organization_id: Parent organization ID
        tier: Subscription tier
        billing_period: Monthly or yearly billing
        square_subscription_id: Square subscription ID
        square_plan_id: Square plan variation ID
        is_active: Whether the subscription is active
        starts_at: Subscription start date
        ends_at: Subscription end date (null for ongoing)
        cancelled_at: When subscription was cancelled
        trial_ends_at: Trial period end date
    """

    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)

    tier = Column(SQLEnum(SubscriptionTier), nullable=False)
    billing_period = Column(SQLEnum(BillingPeriod), default=BillingPeriod.MONTHLY)

    # Square integration
    square_subscription_id = Column(String(100), unique=True, nullable=True)
    square_plan_id = Column(String(100), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_trial = Column(Boolean, default=False, nullable=False)

    # Dates
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)

    # Cancellation
    cancellation_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, tier={self.tier}, active={self.is_active})>"


class Payment(Base):
    """Payment record model.

    Tracks individual payments for subscriptions.

    Attributes:
        id: Unique payment ID
        subscription_id: Parent subscription ID
        organization_id: Organization ID
        amount_cents: Payment amount in cents
        currency: Currency code (e.g., "USD")
        status: Payment status
        square_payment_id: Square payment ID
        payment_method: Payment method used
        failure_reason: Reason for failure if applicable
    """

    __tablename__ = "payments"

    id = Column(String(36), primary_key=True)
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)

    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)

    # Square integration
    square_payment_id = Column(String(100), unique=True, nullable=True)
    square_order_id = Column(String(100), nullable=True)

    payment_method = Column(String(50), nullable=True)
    failure_reason = Column(Text, nullable=True)

    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    subscription = relationship("Subscription", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, amount={self.amount_cents}, status={self.status})>"


class Invoice(Base):
    """Invoice model.

    Generated invoices for billing periods.

    Attributes:
        id: Unique invoice ID
        organization_id: Organization ID
        invoice_number: Human-readable invoice number
        amount_cents: Invoice total in cents
        currency: Currency code
        status: Invoice status
        period_start: Billing period start
        period_end: Billing period end
        due_at: Payment due date
        paid_at: When invoice was paid
    """

    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)

    invoice_number = Column(String(50), unique=True, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)

    status = Column(String(20), default="pending", nullable=False)

    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    due_at = Column(DateTime, nullable=False)
    paid_at = Column(DateTime, nullable=True)

    # Line items stored as JSON
    line_items = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Invoice(number={self.invoice_number}, amount={self.amount_cents})>"


class UsageRecord(Base):
    """Usage tracking record.

    Tracks API usage for billing and quota enforcement.

    Attributes:
        id: Unique record ID
        organization_id: Organization ID
        metric: Type of usage metric
        count: Usage count for this period
        period_start: Start of the usage period
        period_end: End of the usage period
    """

    __tablename__ = "usage_records"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)

    metric = Column(SQLEnum(UsageMetric), nullable=False)
    count = Column(Integer, default=0, nullable=False)

    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Optional breakdown by endpoint/resource
    breakdown = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="usage_records")

    __table_args__ = (
        UniqueConstraint("organization_id", "metric", "period_start", name="uq_org_metric_period"),
    )

    def __repr__(self) -> str:
        return f"<UsageRecord(org={self.organization_id}, metric={self.metric}, count={self.count})>"


class APIKey(Base):
    """API key model.

    API keys for programmatic access to the platform.

    Attributes:
        id: Unique key ID
        organization_id: Parent organization ID
        name: Human-readable key name
        key_hash: Argon2 hash of the key
        prefix: First 8 characters for identification
        scopes: List of permission scopes
        ip_allowlist: List of allowed IP addresses/CIDRs
        rate_limit_override: Custom rate limit (requests/minute)
        is_active: Whether the key is active
        last_used_at: Last usage timestamp
        expires_at: Expiration date (null for no expiry)
    """

    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Key storage (only hash stored, prefix for identification)
    key_hash = Column(String(255), nullable=False)
    prefix = Column(String(12), nullable=False)

    # Permissions
    scopes = Column(JSON, default=list)  # List of APIKeyScope values

    # Access control
    ip_allowlist = Column(JSON, default=list)  # List of IP addresses/CIDRs
    rate_limit_override = Column(Integer, nullable=True)  # requests per minute

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Audit
    created_by = Column(String(36), nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    last_used_ip = Column(String(45), nullable=True)
    use_count = Column(Integer, default=0)

    # Expiration
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name}, prefix={self.prefix})>"

    def is_expired(self) -> bool:
        """Check if the key has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def has_scope(self, scope: APIKeyScope) -> bool:
        """Check if the key has a specific scope."""
        if APIKeyScope.FULL_ACCESS.value in self.scopes:
            return True
        return scope.value in self.scopes


class WebhookEndpoint(Base):
    """Webhook endpoint registration.

    Registered webhook endpoints for event delivery.

    Attributes:
        id: Unique endpoint ID
        organization_id: Parent organization ID
        url: Webhook URL
        secret_hash: Hash of the signing secret
        event_types: List of event types to receive
        is_active: Whether the endpoint is active
        consecutive_failures: Count of consecutive delivery failures
        last_success_at: Last successful delivery timestamp
        last_failure_at: Last failed delivery timestamp
    """

    __tablename__ = "webhook_endpoints"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String(2048), nullable=False)

    # Authentication
    secret_hash = Column(String(255), nullable=False)

    # Subscription
    event_types = Column(JSON, default=list)  # List of event type patterns

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Health tracking
    consecutive_failures = Column(Integer, default=0)
    last_success_at = Column(DateTime, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)
    last_failure_reason = Column(Text, nullable=True)

    # Rate limiting for this endpoint
    max_retries = Column(Integer, default=3)
    timeout_seconds = Column(Integer, default=30)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="webhooks")
    deliveries = relationship("WebhookDelivery", back_populates="endpoint", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<WebhookEndpoint(id={self.id}, url={self.url[:50]})>"


class WebhookDelivery(Base):
    """Webhook delivery attempt record.

    Tracks individual webhook delivery attempts for debugging.

    Attributes:
        id: Unique delivery ID
        endpoint_id: Parent webhook endpoint ID
        event_type: Type of event delivered
        payload: Event payload (JSON)
        status_code: HTTP response status code
        response_body: Response body (truncated)
        duration_ms: Request duration in milliseconds
        attempt: Attempt number (1, 2, 3...)
        success: Whether delivery was successful
    """

    __tablename__ = "webhook_deliveries"

    id = Column(String(36), primary_key=True)
    endpoint_id = Column(String(36), ForeignKey("webhook_endpoints.id"), nullable=False)

    event_id = Column(String(36), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False)

    # Response
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)  # Truncated to 1KB
    response_headers = Column(JSON, nullable=True)

    # Timing
    duration_ms = Column(Integer, nullable=True)
    attempt = Column(Integer, default=1, nullable=False)

    # Status
    success = Column(Boolean, default=False, nullable=False)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    endpoint = relationship("WebhookEndpoint", back_populates="deliveries")

    def __repr__(self) -> str:
        return f"<WebhookDelivery(id={self.id}, event={self.event_type}, success={self.success})>"


# Tier limits configuration
TIER_LIMITS = {
    SubscriptionTier.FREE: {
        UsageMetric.API_CALLS: 1000,  # per month
        UsageMetric.CREDENTIALS_ISSUED: 10,
        UsageMetric.CREDENTIALS_VERIFIED: 100,
        UsageMetric.WEBHOOKS_DELIVERED: 100,
        UsageMetric.STORAGE_BYTES: 10 * 1024 * 1024,  # 10 MB
        UsageMetric.ACTIVE_CREDENTIALS: 10,
        "api_keys": 1,
        "webhooks": 1,
        "members": 1,
        "rate_limit": 10,  # requests per minute
    },
    SubscriptionTier.STARTER: {
        UsageMetric.API_CALLS: 50000,
        UsageMetric.CREDENTIALS_ISSUED: 500,
        UsageMetric.CREDENTIALS_VERIFIED: 5000,
        UsageMetric.WEBHOOKS_DELIVERED: 5000,
        UsageMetric.STORAGE_BYTES: 100 * 1024 * 1024,  # 100 MB
        UsageMetric.ACTIVE_CREDENTIALS: 500,
        "api_keys": 5,
        "webhooks": 5,
        "members": 5,
        "rate_limit": 100,
    },
    SubscriptionTier.PROFESSIONAL: {
        UsageMetric.API_CALLS: 500000,
        UsageMetric.CREDENTIALS_ISSUED: 5000,
        UsageMetric.CREDENTIALS_VERIFIED: 50000,
        UsageMetric.WEBHOOKS_DELIVERED: 50000,
        UsageMetric.STORAGE_BYTES: 1024 * 1024 * 1024,  # 1 GB
        UsageMetric.ACTIVE_CREDENTIALS: 5000,
        "api_keys": 20,
        "webhooks": 20,
        "members": 20,
        "rate_limit": 500,
    },
    SubscriptionTier.ENTERPRISE: {
        UsageMetric.API_CALLS: -1,  # Unlimited
        UsageMetric.CREDENTIALS_ISSUED: -1,
        UsageMetric.CREDENTIALS_VERIFIED: -1,
        UsageMetric.WEBHOOKS_DELIVERED: -1,
        UsageMetric.STORAGE_BYTES: -1,
        UsageMetric.ACTIVE_CREDENTIALS: -1,
        "api_keys": -1,
        "webhooks": -1,
        "members": -1,
        "rate_limit": 2000,
    },
}


def get_tier_limit(tier: SubscriptionTier, metric: str) -> int:
    """Get the limit for a specific metric and tier.

    Args:
        tier: Subscription tier
        metric: Metric name or UsageMetric enum

    Returns:
        Limit value, -1 for unlimited
    """
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS[SubscriptionTier.FREE])

    if isinstance(metric, UsageMetric):
        return tier_config.get(metric, 0)
    return tier_config.get(metric, 0)
