"""
Security incident monitoring and alerting system for Marty services.

Provides real-time security incident detection, classification, and response
coordination to protect against security threats and operational anomalies.
"""

from __future__ import annotations

import json
import logging
import smtplib
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any

import requests

from .access_control import AuditEvent, AuditLogEntry

logger = logging.getLogger(__name__)


class IncidentSeverity(Enum):
    """Security incident severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentType(Enum):
    """Types of security incidents."""

    UNAUTHORIZED_ACCESS = "unauthorized_access"
    BRUTE_FORCE_ATTACK = "brute_force_attack"
    DATA_BREACH = "data_breach"
    MALICIOUS_REQUEST = "malicious_request"
    CERTIFICATE_COMPROMISE = "certificate_compromise"
    KEY_COMPROMISE = "key_compromise"
    SERVICE_DISRUPTION = "service_disruption"
    CONFIGURATION_TAMPERING = "configuration_tampering"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    COMPLIANCE_VIOLATION = "compliance_violation"


class IncidentStatus(Enum):
    """Security incident response status."""

    NEW = "new"
    INVESTIGATING = "investigating"
    CONFIRMED = "confirmed"
    RESPONDING = "responding"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


@dataclass
class SecurityIncident:
    """Security incident record."""

    incident_id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    title: str
    description: str
    detected_at: datetime = field(default_factory=datetime.now)
    status: IncidentStatus = IncidentStatus.NEW
    affected_services: list[str] = field(default_factory=list)
    affected_users: list[str] = field(default_factory=list)
    indicators: dict[str, Any] = field(default_factory=dict)
    response_actions: list[str] = field(default_factory=list)
    assigned_to: str | None = None
    resolution_notes: str | None = None
    resolved_at: datetime | None = None
    false_positive_reason: str | None = None


class SecurityRule:
    """Security monitoring rule definition."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        description: str,
        condition: Callable[[AuditLogEntry], bool],
        incident_type: IncidentType,
        severity: IncidentSeverity,
        cooldown_seconds: int = 300,
    ) -> None:
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.condition = condition
        self.incident_type = incident_type
        self.severity = severity
        self.cooldown_seconds = cooldown_seconds
        self.last_triggered = None


class AlertChannel(ABC):
    """Abstract base class for alert channels."""

    @abstractmethod
    def send_alert(self, incident: SecurityIncident) -> bool:
        """Send security incident alert."""


class EmailAlertChannel(AlertChannel):
    """Email-based security alerting."""

    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: list[str],
        use_tls: bool = True,
    ) -> None:
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails
        self.use_tls = use_tls

    def send_alert(self, incident: SecurityIncident) -> bool:
        """Send incident alert via email."""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)
            msg["Subject"] = f"[SECURITY ALERT] {incident.severity.value.upper()}: {incident.title}"

            body = f"""
Security Incident Detected

Incident ID: {incident.incident_id}
Type: {incident.incident_type.value}
Severity: {incident.severity.value.upper()}
Detected: {incident.detected_at.isoformat()}
Status: {incident.status.value}

Description: {incident.description}

Affected Services: {", ".join(incident.affected_services) if incident.affected_services else "None"}
Affected Users: {", ".join(incident.affected_users) if incident.affected_users else "None"}

Indicators:
{json.dumps(incident.indicators, indent=2)}

Please investigate immediately if severity is HIGH or CRITICAL.
            """.strip()

            msg.attach(MIMEText(body, "plain"))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            text = msg.as_string()
            server.sendmail(self.from_email, self.to_emails, text)
            server.quit()

            logger.info(f"Security alert sent via email for incident {incident.incident_id}")

        except Exception as e:
            logger.exception(f"Failed to send email alert for incident {incident.incident_id}: {e}")
            return False
        else:
            return True


class WebhookAlertChannel(AlertChannel):
    """Webhook-based security alerting (Slack, Teams, etc.)."""

    def __init__(self, webhook_url: str, timeout: int = 10) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send_alert(self, incident: SecurityIncident) -> bool:
        """Send incident alert via webhook."""
        try:
            payload = {
                "incident_id": incident.incident_id,
                "type": incident.incident_type.value,
                "severity": incident.severity.value,
                "title": incident.title,
                "description": incident.description,
                "detected_at": incident.detected_at.isoformat(),
                "status": incident.status.value,
                "affected_services": incident.affected_services,
                "affected_users": incident.affected_users,
                "indicators": incident.indicators,
            }

            # Format for Slack
            if "slack" in self.webhook_url.lower():
                color_map = {
                    IncidentSeverity.LOW: "good",
                    IncidentSeverity.MEDIUM: "warning",
                    IncidentSeverity.HIGH: "danger",
                    IncidentSeverity.CRITICAL: "danger",
                }

                slack_payload = {
                    "attachments": [
                        {
                            "color": color_map.get(incident.severity, "warning"),
                            "title": f"Security Incident: {incident.title}",
                            "text": incident.description,
                            "fields": [
                                {
                                    "title": "Incident ID",
                                    "value": incident.incident_id,
                                    "short": True,
                                },
                                {
                                    "title": "Type",
                                    "value": incident.incident_type.value,
                                    "short": True,
                                },
                                {
                                    "title": "Severity",
                                    "value": incident.severity.value.upper(),
                                    "short": True,
                                },
                                {"title": "Status", "value": incident.status.value, "short": True},
                                {
                                    "title": "Detected",
                                    "value": incident.detected_at.isoformat(),
                                    "short": True,
                                },
                            ],
                            "ts": int(incident.detected_at.timestamp()),
                        }
                    ]
                }
                payload = slack_payload

            response = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
            response.raise_for_status()

            logger.info(f"Security alert sent via webhook for incident {incident.incident_id}")

        except Exception as e:
            logger.exception(
                f"Failed to send webhook alert for incident {incident.incident_id}: {e}"
            )
            return False
        else:
            return True


class SecurityMonitor:
    """Security incident monitoring and response system."""

    def __init__(self) -> None:
        self.rules: dict[str, SecurityRule] = {}
        self.incidents: dict[str, SecurityIncident] = {}
        self.alert_channels: list[AlertChannel] = []
        self.is_monitoring = False
        self.monitor_thread: threading.Thread | None = None
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._lock = threading.Lock()

        # Setup default security rules
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Set up default security monitoring rules."""

        # Brute force detection
        self.add_rule(
            SecurityRule(
                rule_id="brute_force_login",
                name="Brute Force Login Detection",
                description="Detect multiple failed login attempts from same user/IP",
                condition=lambda entry: (
                    entry.event_type == AuditEvent.USER_LOGIN
                    and entry.result == "failure"
                    and "authentication" in (entry.action or "")
                ),
                incident_type=IncidentType.BRUTE_FORCE_ATTACK,
                severity=IncidentSeverity.MEDIUM,
                cooldown_seconds=600,
            )
        )

        # Unauthorized access attempts
        self.add_rule(
            SecurityRule(
                rule_id="unauthorized_access",
                name="Unauthorized Access Detection",
                description="Detect permission denied events",
                condition=lambda entry: entry.event_type == AuditEvent.PERMISSION_DENIED,
                incident_type=IncidentType.UNAUTHORIZED_ACCESS,
                severity=IncidentSeverity.HIGH,
                cooldown_seconds=300,
            )
        )

        # Key/Certificate compromise indicators
        self.add_rule(
            SecurityRule(
                rule_id="key_compromise",
                name="Key Compromise Detection",
                description="Detect suspicious key operations",
                condition=lambda entry: (
                    entry.event_type == AuditEvent.KEY_DELETED
                    and entry.risk_level in ("high", "critical")
                ),
                incident_type=IncidentType.KEY_COMPROMISE,
                severity=IncidentSeverity.CRITICAL,
                cooldown_seconds=0,
            )
        )

        # Configuration tampering
        self.add_rule(
            SecurityRule(
                rule_id="config_tampering",
                name="Configuration Tampering Detection",
                description="Detect unauthorized configuration changes",
                condition=lambda entry: (
                    entry.event_type == AuditEvent.CONFIGURATION_CHANGED
                    and entry.result == "success"
                    and entry.risk_level in ("medium", "high", "critical")
                ),
                incident_type=IncidentType.CONFIGURATION_TAMPERING,
                severity=IncidentSeverity.HIGH,
                cooldown_seconds=300,
            )
        )

        # Anomaly detection
        self.add_rule(
            SecurityRule(
                rule_id="anomaly_detected",
                name="Anomalous Behavior Detection",
                description="Detect flagged anomalous behavior",
                condition=lambda entry: entry.event_type == AuditEvent.ANOMALY_DETECTED,
                incident_type=IncidentType.ANOMALOUS_BEHAVIOR,
                severity=IncidentSeverity.MEDIUM,
                cooldown_seconds=600,
            )
        )

    def add_rule(self, rule: SecurityRule) -> None:
        """Add a security monitoring rule."""
        with self._lock:
            self.rules[rule.rule_id] = rule
            logger.info(f"Added security rule: {rule.name}")

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a security monitoring rule."""
        with self._lock:
            if rule_id in self.rules:
                del self.rules[rule_id]
                logger.info(f"Removed security rule: {rule_id}")
                return True
            return False

    def add_alert_channel(self, channel: AlertChannel) -> None:
        """Add an alert channel for incident notifications."""
        self.alert_channels.append(channel)
        logger.info(f"Added alert channel: {type(channel).__name__}")

    def evaluate_event(self, audit_entry: AuditLogEntry) -> list[SecurityIncident]:
        """Evaluate an audit event against security rules."""
        triggered_incidents = []

        with self._lock:
            for rule in self.rules.values():
                try:
                    # Check cooldown
                    if (
                        rule.last_triggered
                        and rule.cooldown_seconds > 0
                        and (datetime.now() - rule.last_triggered).total_seconds()
                        < rule.cooldown_seconds
                    ):
                        continue

                    # Evaluate rule condition
                    if rule.condition(audit_entry):
                        incident = self._create_incident(rule, audit_entry)
                        triggered_incidents.append(incident)
                        rule.last_triggered = datetime.now()

                        logger.warning(
                            f"Security rule triggered: {rule.name} for event {audit_entry.event_id}"
                        )

                except Exception as e:
                    logger.exception(f"Error evaluating security rule {rule.rule_id}: {e}")

        # Send alerts for new incidents
        for incident in triggered_incidents:
            self._send_alerts(incident)

        return triggered_incidents

    def _create_incident(self, rule: SecurityRule, audit_entry: AuditLogEntry) -> SecurityIncident:
        """Create a security incident from triggered rule."""
        incident_id = f"INC-{int(datetime.now().timestamp())}-{rule.rule_id}"

        incident = SecurityIncident(
            incident_id=incident_id,
            incident_type=rule.incident_type,
            severity=rule.severity,
            title=f"{rule.name} - {audit_entry.event_type.value}",
            description=f"{rule.description}. Event: {audit_entry.action or 'unknown'} "
            f"by {audit_entry.username or 'unknown user'}.",
            affected_services=[audit_entry.service_name] if audit_entry.service_name else [],
            affected_users=[audit_entry.user_id] if audit_entry.user_id else [],
            indicators={
                "triggering_event_id": audit_entry.event_id,
                "event_type": audit_entry.event_type.value,
                "user_id": audit_entry.user_id,
                "username": audit_entry.username,
                "service_name": audit_entry.service_name,
                "ip_address": audit_entry.ip_address,
                "risk_level": audit_entry.risk_level,
                "additional_data": audit_entry.additional_data,
            },
        )

        with self._lock:
            self.incidents[incident_id] = incident

        return incident

    def _send_alerts(self, incident: SecurityIncident) -> None:
        """Send alerts for a security incident."""
        for channel in self.alert_channels:
            try:
                self.executor.submit(channel.send_alert, incident)
            except Exception as e:
                logger.exception(f"Error submitting alert for incident {incident.incident_id}: {e}")

    def get_incident(self, incident_id: str) -> SecurityIncident | None:
        """Get security incident by ID."""
        with self._lock:
            return self.incidents.get(incident_id)

    def update_incident_status(
        self,
        incident_id: str,
        status: IncidentStatus,
        assigned_to: str | None = None,
        resolution_notes: str | None = None,
    ) -> bool:
        """Update security incident status."""
        with self._lock:
            incident = self.incidents.get(incident_id)
            if not incident:
                return False

            incident.status = status
            if assigned_to:
                incident.assigned_to = assigned_to
            if resolution_notes:
                incident.resolution_notes = resolution_notes

            if status in (IncidentStatus.RESOLVED, IncidentStatus.FALSE_POSITIVE):
                incident.resolved_at = datetime.now()

            logger.info(f"Updated incident {incident_id} status to {status.value}")
            return True

    def get_incidents(
        self,
        severity: IncidentSeverity | None = None,
        status: IncidentStatus | None = None,
        incident_type: IncidentType | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[SecurityIncident]:
        """Get filtered list of security incidents."""
        with self._lock:
            incidents = list(self.incidents.values())

        # Apply filters
        if severity:
            incidents = [i for i in incidents if i.severity == severity]
        if status:
            incidents = [i for i in incidents if i.status == status]
        if incident_type:
            incidents = [i for i in incidents if i.incident_type == incident_type]
        if start_time:
            incidents = [i for i in incidents if i.detected_at >= start_time]
        if end_time:
            incidents = [i for i in incidents if i.detected_at <= end_time]

        # Sort by detection time (newest first)
        incidents.sort(key=lambda i: i.detected_at, reverse=True)

        return incidents

    def start_monitoring(self) -> None:
        """Start the security monitoring system."""
        if self.is_monitoring:
            logger.warning("Security monitoring is already running")
            return

        self.is_monitoring = True
        logger.info("Security incident monitoring started")

    def stop_monitoring(self) -> None:
        """Stop the security monitoring system."""
        if not self.is_monitoring:
            return

        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()

        self.executor.shutdown(wait=True)
        logger.info("Security incident monitoring stopped")


def create_security_monitor() -> SecurityMonitor:
    """Create a default security monitor."""
    return SecurityMonitor()


def create_email_alert_channel(
    smtp_server: str,
    smtp_port: int,
    username: str,
    password: str,
    from_email: str,
    to_emails: list[str],
) -> EmailAlertChannel:
    """Create email alert channel."""
    return EmailAlertChannel(
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        username=username,
        password=password,
        from_email=from_email,
        to_emails=to_emails,
    )


def create_slack_alert_channel(webhook_url: str) -> WebhookAlertChannel:
    """Create Slack webhook alert channel."""
    return WebhookAlertChannel(webhook_url)
