"""
Access control and audit logging system for Marty services.

Provides comprehensive access control management with role-based permissions
and detailed audit logging for security compliance and monitoring.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class Permission(Enum):
    """System permissions."""

    # Document operations
    CREATE_DOCUMENT = "create_document"
    READ_DOCUMENT = "read_document"
    SIGN_DOCUMENT = "sign_document"
    REVOKE_DOCUMENT = "revoke_document"

    # Certificate operations
    ISSUE_CERTIFICATE = "issue_certificate"
    REVOKE_CERTIFICATE = "revoke_certificate"
    VALIDATE_CERTIFICATE = "validate_certificate"

    # Key management
    GENERATE_KEY = "generate_key"
    ROTATE_KEY = "rotate_key"
    DELETE_KEY = "delete_key"

    # PKD operations
    UPDATE_PKD = "update_pkd"
    QUERY_PKD = "query_pkd"

    # Administrative
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    CONFIGURE_SYSTEM = "configure_system"

    # Trust operations
    MANAGE_TRUST_ANCHORS = "manage_trust_anchors"
    VERIFY_TRUST_CHAIN = "verify_trust_chain"


class Role(Enum):
    """System roles with predefined permission sets."""

    ADMIN = "admin"
    OPERATOR = "operator"
    AUDITOR = "auditor"
    DOCUMENT_ISSUER = "document_issuer"
    VALIDATOR = "validator"
    READ_ONLY = "read_only"


class AuditEvent(Enum):
    """Types of auditable events."""

    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    PERMISSION_DENIED = "permission_denied"
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_SIGNED = "document_signed"
    DOCUMENT_VERIFIED = "document_verified"
    DOCUMENT_REVOKED = "document_revoked"
    CERTIFICATE_ISSUED = "certificate_issued"
    CERTIFICATE_REVOKED = "certificate_revoked"
    KEY_GENERATED = "key_generated"
    KEY_ROTATED = "key_rotated"
    KEY_DELETED = "key_deleted"
    PKD_UPDATE = "pkd_update"
    CONFIGURATION_CHANGED = "configuration_changed"
    SECURITY_INCIDENT = "security_incident"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class User:
    """User account with roles and permissions."""

    user_id: str
    username: str
    email: str
    roles: set[Role] = field(default_factory=set)
    custom_permissions: set[Permission] = field(default_factory=set)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_login: datetime | None = None
    failed_login_attempts: int = 0
    account_locked_until: datetime | None = None
    session_token: str | None = None
    session_expires_at: datetime | None = None


@dataclass
class AuditLogEntry:
    """Audit log entry for security events."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: AuditEvent = AuditEvent.SECURITY_INCIDENT
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: str | None = None
    username: str | None = None
    service_name: str | None = None
    resource_id: str | None = None
    resource_type: str | None = None
    action: str | None = None
    result: str = "success"  # success, failure, error
    error_message: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    additional_data: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"  # low, medium, high, critical


class AccessControlException(Exception):
    """Exception raised for access control violations."""


class AuditLogger(ABC):
    """Abstract interface for audit logging."""

    @abstractmethod
    def log_event(self, entry: AuditLogEntry) -> None:
        """Log an audit event."""

    @abstractmethod
    def query_events(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_types: list[AuditEvent] | None = None,
        user_id: str | None = None,
        risk_level: str | None = None,
    ) -> list[AuditLogEntry]:
        """Query audit events with filters."""


class FileAuditLogger(AuditLogger):
    """File-based audit logger for development and small deployments."""

    def __init__(self, log_file_path: str = "/var/log/marty/audit.log") -> None:
        self.log_file_path = log_file_path
        self._lock = threading.Lock()

    def log_event(self, entry: AuditLogEntry) -> None:
        """Log audit event to file."""
        try:
            with self._lock, open(self.log_file_path, "a", encoding="utf-8") as f:
                log_data = {
                    "event_id": entry.event_id,
                    "event_type": entry.event_type.value,
                    "timestamp": entry.timestamp.isoformat(),
                    "user_id": entry.user_id,
                    "username": entry.username,
                    "service_name": entry.service_name,
                    "resource_id": entry.resource_id,
                    "resource_type": entry.resource_type,
                    "action": entry.action,
                    "result": entry.result,
                    "error_message": entry.error_message,
                    "ip_address": entry.ip_address,
                    "user_agent": entry.user_agent,
                    "additional_data": entry.additional_data,
                    "risk_level": entry.risk_level,
                }
                f.write(json.dumps(log_data) + "\n")
        except Exception:
            logger.exception("Failed to write audit log")

    def query_events(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_types: list[AuditEvent] | None = None,
        user_id: str | None = None,
        risk_level: str | None = None,
    ) -> list[AuditLogEntry]:
        """Query audit events from file."""
        events = []
        try:
            with open(self.log_file_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        log_data = json.loads(line.strip())
                        event_time = datetime.fromisoformat(log_data["timestamp"])

                        # Apply filters
                        if start_time and event_time < start_time:
                            continue
                        if end_time and event_time > end_time:
                            continue
                        if event_types and AuditEvent(log_data["event_type"]) not in event_types:
                            continue
                        if user_id and log_data["user_id"] != user_id:
                            continue
                        if risk_level and log_data["risk_level"] != risk_level:
                            continue

                        entry = AuditLogEntry(
                            event_id=log_data["event_id"],
                            event_type=AuditEvent(log_data["event_type"]),
                            timestamp=event_time,
                            user_id=log_data["user_id"],
                            username=log_data["username"],
                            service_name=log_data["service_name"],
                            resource_id=log_data["resource_id"],
                            resource_type=log_data["resource_type"],
                            action=log_data["action"],
                            result=log_data["result"],
                            error_message=log_data["error_message"],
                            ip_address=log_data["ip_address"],
                            user_agent=log_data["user_agent"],
                            additional_data=log_data["additional_data"],
                            risk_level=log_data["risk_level"],
                        )
                        events.append(entry)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping malformed audit log entry: {e}")
                        continue
        except FileNotFoundError:
            logger.warning(f"Audit log file not found: {self.log_file_path}")
        except Exception:
            logger.exception("Error reading audit log")

        return events


class AccessControlManager:
    """Manages user access control and permissions."""

    # Role permission mappings
    ROLE_PERMISSIONS = {
        Role.ADMIN: {
            Permission.CREATE_DOCUMENT,
            Permission.READ_DOCUMENT,
            Permission.SIGN_DOCUMENT,
            Permission.REVOKE_DOCUMENT,
            Permission.ISSUE_CERTIFICATE,
            Permission.REVOKE_CERTIFICATE,
            Permission.VALIDATE_CERTIFICATE,
            Permission.GENERATE_KEY,
            Permission.ROTATE_KEY,
            Permission.DELETE_KEY,
            Permission.UPDATE_PKD,
            Permission.QUERY_PKD,
            Permission.MANAGE_USERS,
            Permission.VIEW_AUDIT_LOGS,
            Permission.CONFIGURE_SYSTEM,
            Permission.MANAGE_TRUST_ANCHORS,
            Permission.VERIFY_TRUST_CHAIN,
        },
        Role.OPERATOR: {
            Permission.CREATE_DOCUMENT,
            Permission.READ_DOCUMENT,
            Permission.SIGN_DOCUMENT,
            Permission.VALIDATE_CERTIFICATE,
            Permission.QUERY_PKD,
            Permission.VERIFY_TRUST_CHAIN,
        },
        Role.AUDITOR: {
            Permission.READ_DOCUMENT,
            Permission.VIEW_AUDIT_LOGS,
            Permission.QUERY_PKD,
        },
        Role.DOCUMENT_ISSUER: {
            Permission.CREATE_DOCUMENT,
            Permission.READ_DOCUMENT,
            Permission.SIGN_DOCUMENT,
            Permission.ISSUE_CERTIFICATE,
            Permission.VALIDATE_CERTIFICATE,
        },
        Role.VALIDATOR: {
            Permission.READ_DOCUMENT,
            Permission.VALIDATE_CERTIFICATE,
            Permission.VERIFY_TRUST_CHAIN,
        },
        Role.READ_ONLY: {
            Permission.READ_DOCUMENT,
            Permission.QUERY_PKD,
        },
    }

    def __init__(self, audit_logger: AuditLogger) -> None:
        self.audit_logger = audit_logger
        self.users: dict[str, User] = {}
        self.sessions: dict[str, User] = {}
        self._lock = threading.Lock()

    def create_user(
        self,
        user_id: str,
        username: str,
        email: str,
        roles: set[Role] | None = None,
        custom_permissions: set[Permission] | None = None,
    ) -> User:
        """Create a new user account."""
        with self._lock:
            if user_id in self.users:
                msg = f"User {user_id} already exists"
                raise AccessControlException(msg)

            user = User(
                user_id=user_id,
                username=username,
                email=email,
                roles=roles or set(),
                custom_permissions=custom_permissions or set(),
            )
            self.users[user_id] = user

            self.audit_logger.log_event(
                AuditLogEntry(
                    event_type=AuditEvent.USER_LOGIN,
                    user_id=user_id,
                    username=username,
                    action="create_user",
                    result="success",
                    additional_data={"roles": [r.value for r in user.roles]},
                )
            )

            return user

    def authenticate_user(self, username: str, password_hash: str) -> str | None:
        """Authenticate user and create session token."""
        user = None
        for u in self.users.values():
            if u.username == username and u.is_active:
                user = u
                break

        if not user:
            self.audit_logger.log_event(
                AuditLogEntry(
                    event_type=AuditEvent.USER_LOGIN,
                    username=username,
                    action="authentication",
                    result="failure",
                    error_message="User not found or inactive",
                    risk_level="medium",
                )
            )
            return None

        # Check account lockout
        if user.account_locked_until and datetime.now() < user.account_locked_until:
            self.audit_logger.log_event(
                AuditLogEntry(
                    event_type=AuditEvent.USER_LOGIN,
                    user_id=user.user_id,
                    username=username,
                    action="authentication",
                    result="failure",
                    error_message="Account locked",
                    risk_level="medium",
                )
            )
            return None

        # In a real implementation, you would verify password_hash
        # For now, we'll assume authentication is successful if we reach here

        # Create session
        session_token = str(uuid.uuid4())
        user.session_token = session_token
        user.session_expires_at = datetime.now() + timedelta(hours=8)
        user.last_login = datetime.now()
        user.failed_login_attempts = 0
        user.account_locked_until = None

        self.sessions[session_token] = user

        self.audit_logger.log_event(
            AuditLogEntry(
                event_type=AuditEvent.USER_LOGIN,
                user_id=user.user_id,
                username=username,
                action="authentication",
                result="success",
            )
        )

        return session_token

    def get_user_by_session(self, session_token: str) -> User | None:
        """Get user by session token."""
        user = self.sessions.get(session_token)
        if not user:
            return None

        # Check session expiry
        if user.session_expires_at and datetime.now() > user.session_expires_at:
            self.logout_user(session_token)
            return None

        return user

    def logout_user(self, session_token: str) -> None:
        """Logout user and invalidate session."""
        user = self.sessions.pop(session_token, None)
        if user:
            user.session_token = None
            user.session_expires_at = None

            self.audit_logger.log_event(
                AuditLogEntry(
                    event_type=AuditEvent.USER_LOGOUT,
                    user_id=user.user_id,
                    username=user.username,
                    action="logout",
                    result="success",
                )
            )

    def has_permission(self, user: User, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        if not user.is_active:
            return False

        # Check custom permissions
        if permission in user.custom_permissions:
            return True

        # Check role-based permissions
        return any(permission in self.ROLE_PERMISSIONS.get(role, set()) for role in user.roles)

    def require_permission(self, permission: Permission):
        """Decorator to require specific permission for a function."""

        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Extract user from kwargs or context
                user = kwargs.get("user") or kwargs.get("current_user")
                if not user:
                    self.audit_logger.log_event(
                        AuditLogEntry(
                            event_type=AuditEvent.PERMISSION_DENIED,
                            action=func.__name__,
                            result="failure",
                            error_message="No user provided",
                            risk_level="high",
                        )
                    )
                    msg = "Authentication required"
                    raise AccessControlException(msg)

                if not self.has_permission(user, permission):
                    self.audit_logger.log_event(
                        AuditLogEntry(
                            event_type=AuditEvent.PERMISSION_DENIED,
                            user_id=user.user_id,
                            username=user.username,
                            action=func.__name__,
                            result="failure",
                            error_message=f"Permission denied: {permission.value}",
                            risk_level="medium",
                            additional_data={"required_permission": permission.value},
                        )
                    )
                    msg = f"Permission denied: {permission.value}"
                    raise AccessControlException(msg)

                return func(*args, **kwargs)

            return wrapper

        return decorator


def create_access_control_manager(
    audit_log_path: str = "/var/log/marty/audit.log",
) -> AccessControlManager:
    """Create a default access control manager with file audit logger."""
    audit_logger = FileAuditLogger(audit_log_path)
    return AccessControlManager(audit_logger)


# Example usage and testing functions
def setup_default_users(access_control: AccessControlManager) -> None:
    """Set up default system users for testing."""
    # Create admin user
    access_control.create_user(
        user_id="admin-001", username="admin", email="admin@marty.example.com", roles={Role.ADMIN}
    )

    # Create operator user
    access_control.create_user(
        user_id="op-001",
        username="operator",
        email="operator@marty.example.com",
        roles={Role.OPERATOR},
    )

    # Create auditor user
    access_control.create_user(
        user_id="audit-001",
        username="auditor",
        email="auditor@marty.example.com",
        roles={Role.AUDITOR},
    )
