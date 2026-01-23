"""
Key usage anomaly detection system for Marty services.

Monitors cryptographic key usage patterns to detect anomalies, unauthorized usage,
and potential security incidents related to key management.
"""

from __future__ import annotations

import hashlib
import logging
import statistics
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class KeyType(Enum):
    """Types of cryptographic keys to monitor."""

    SIGNING_KEY = "signing_key"
    ENCRYPTION_KEY = "encryption_key"
    ROOT_CA_KEY = "root_ca_key"
    INTERMEDIATE_CA_KEY = "intermediate_ca_key"
    DOCUMENT_SIGNER_KEY = "document_signer_key"
    TLS_SERVER_KEY = "tls_server_key"
    CLIENT_AUTH_KEY = "client_auth_key"
    CSCA_KEY = "csca_key"
    DSC_KEY = "dsc_key"
    HSM_KEY = "hsm_key"


class KeyOperation(Enum):
    """Types of key operations to monitor."""

    SIGN = "sign"
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"
    VERIFY = "verify"
    KEY_EXCHANGE = "key_exchange"
    DERIVE = "derive"
    GENERATE = "generate"
    IMPORT = "import"
    EXPORT = "export"
    DELETE = "delete"
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"


class AnomalyType(Enum):
    """Types of key usage anomalies."""

    UNUSUAL_FREQUENCY = "unusual_frequency"
    TIME_ANOMALY = "time_anomaly"
    LOCATION_ANOMALY = "location_anomaly"
    OPERATION_ANOMALY = "operation_anomaly"
    VOLUME_SPIKE = "volume_spike"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    FAILED_OPERATIONS = "failed_operations"
    EXPIRED_KEY_USAGE = "expired_key_usage"
    REVOKED_KEY_USAGE = "revoked_key_usage"
    PATTERN_DEVIATION = "pattern_deviation"


class AnomalySeverity(Enum):
    """Severity levels for anomalies."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class KeyUsageEvent:
    """Individual key usage event."""

    event_id: str
    timestamp: datetime
    key_id: str
    key_type: KeyType
    operation: KeyOperation
    user_id: str
    source_ip: str
    user_agent: str
    success: bool
    error_message: str | None = None
    data_size: int = 0  # Size of data operated on
    duration_ms: int = 0  # Operation duration
    additional_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KeyInfo:
    """Key information for monitoring."""

    key_id: str
    key_type: KeyType
    created_at: datetime
    expires_at: datetime | None = None
    is_active: bool = True
    is_revoked: bool = False
    revoked_at: datetime | None = None
    allowed_operations: set[KeyOperation] = field(default_factory=set)
    allowed_users: set[str] = field(default_factory=set)
    allowed_ip_ranges: list[str] = field(default_factory=list)
    max_daily_operations: int = 1000
    max_hourly_operations: int = 100


@dataclass
class UsagePattern:
    """Historical usage pattern for a key."""

    key_id: str
    daily_usage_stats: dict[str, float] = field(default_factory=dict)  # mean, std, min, max
    hourly_usage_stats: dict[str, float] = field(default_factory=dict)
    common_operations: set[KeyOperation] = field(default_factory=set)
    common_users: set[str] = field(default_factory=set)
    common_ip_ranges: set[str] = field(default_factory=set)
    common_time_ranges: list[tuple[int, int]] = field(
        default_factory=list
    )  # (start_hour, end_hour)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class KeyAnomalyAlert:
    """Key usage anomaly alert."""

    alert_id: str
    key_id: str
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    description: str
    detected_at: datetime
    events_involved: list[KeyUsageEvent]
    confidence_score: float  # 0.0 to 1.0
    recommended_actions: list[str] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved: bool = False
    resolved_by: str | None = None
    resolved_at: datetime | None = None


class KeyUsageCollector:
    """Collects key usage events from various sources."""

    def __init__(self) -> None:
        self.events: list[KeyUsageEvent] = []
        self.event_listeners: list[Callable[[KeyUsageEvent], None]] = []
        self._lock = threading.Lock()

    def add_event(self, event: KeyUsageEvent) -> None:
        """Add a key usage event."""
        with self._lock:
            self.events.append(event)

            # Notify listeners
            for listener in self.event_listeners:
                try:
                    listener(event)
                except Exception as e:
                    logger.exception(f"Error notifying event listener: {e}")

    def add_event_listener(self, listener: Callable[[KeyUsageEvent], None]) -> None:
        """Add an event listener."""
        self.event_listeners.append(listener)

    def get_events_for_key(
        self, key_id: str, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> list[KeyUsageEvent]:
        """Get events for a specific key within a time range."""
        with self._lock:
            filtered_events = [e for e in self.events if e.key_id == key_id]

            if start_time:
                filtered_events = [e for e in filtered_events if e.timestamp >= start_time]
            if end_time:
                filtered_events = [e for e in filtered_events if e.timestamp <= end_time]

            return filtered_events

    def get_events_for_user(
        self, user_id: str, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> list[KeyUsageEvent]:
        """Get events for a specific user within a time range."""
        with self._lock:
            filtered_events = [e for e in self.events if e.user_id == user_id]

            if start_time:
                filtered_events = [e for e in filtered_events if e.timestamp >= start_time]
            if end_time:
                filtered_events = [e for e in filtered_events if e.timestamp <= end_time]

            return filtered_events


class PatternLearner:
    """Learns normal usage patterns for keys."""

    def __init__(self, learning_window_days: int = 30) -> None:
        self.learning_window_days = learning_window_days
        self.patterns: dict[str, UsagePattern] = {}
        self._lock = threading.Lock()

    def update_pattern(self, key_id: str, events: list[KeyUsageEvent]) -> None:
        """Update usage pattern for a key based on recent events."""
        if not events:
            return

        with self._lock:
            pattern = self.patterns.get(key_id, UsagePattern(key_id=key_id))

            # Calculate daily usage statistics
            daily_counts = defaultdict(int)
            hourly_counts = defaultdict(int)
            operations = set()
            users = set()
            ips = set()

            for event in events:
                day_key = event.timestamp.date().isoformat()
                hour_key = event.timestamp.hour

                daily_counts[day_key] += 1
                hourly_counts[hour_key] += 1
                operations.add(event.operation)
                users.add(event.user_id)

                # Extract IP network (first 3 octets for IPv4)
                ip_parts = event.source_ip.split(".")
                if len(ip_parts) >= 3:
                    ip_network = ".".join(ip_parts[:3]) + ".0"
                    ips.add(ip_network)

            # Calculate statistics
            daily_values = list(daily_counts.values())
            if daily_values:
                pattern.daily_usage_stats = {
                    "mean": statistics.mean(daily_values),
                    "std": statistics.stdev(daily_values) if len(daily_values) > 1 else 0,
                    "min": min(daily_values),
                    "max": max(daily_values),
                }

            hourly_values = list(hourly_counts.values())
            if hourly_values:
                pattern.hourly_usage_stats = {
                    "mean": statistics.mean(hourly_values),
                    "std": statistics.stdev(hourly_values) if len(hourly_values) > 1 else 0,
                    "min": min(hourly_values),
                    "max": max(hourly_values),
                }

            pattern.common_operations = operations
            pattern.common_users = users
            pattern.common_ip_ranges = ips
            pattern.last_updated = datetime.now(timezone.utc)

            # Determine common time ranges
            active_hours = [h for h in range(24) if hourly_counts[h] > 0]
            if active_hours:
                # Group consecutive hours
                pattern.common_time_ranges = self._group_consecutive_hours(active_hours)

            self.patterns[key_id] = pattern

    def _group_consecutive_hours(self, hours: list[int]) -> list[tuple[int, int]]:
        """Group consecutive hours into ranges."""
        if not hours:
            return []

        sorted_hours = sorted(hours)
        ranges = []
        start = sorted_hours[0]
        end = sorted_hours[0]

        for hour in sorted_hours[1:]:
            if hour == end + 1:
                end = hour
            else:
                ranges.append((start, end))
                start = end = hour

        ranges.append((start, end))
        return ranges

    def get_pattern(self, key_id: str) -> UsagePattern | None:
        """Get usage pattern for a key."""
        with self._lock:
            return self.patterns.get(key_id)


class AnomalyDetector:
    """Detects anomalies in key usage patterns."""

    def __init__(self, sensitivity: float = 0.8, min_events_for_detection: int = 10) -> None:
        self.sensitivity = sensitivity
        self.min_events_for_detection = min_events_for_detection

    def detect_anomalies(
        self,
        key_id: str,
        recent_events: list[KeyUsageEvent],
        pattern: UsagePattern | None,
        key_info: KeyInfo | None,
    ) -> list[KeyAnomalyAlert]:
        """Detect anomalies in key usage."""
        anomalies = []

        if len(recent_events) < self.min_events_for_detection:
            return anomalies

        # Check for various anomaly types
        anomalies.extend(self._detect_frequency_anomalies(key_id, recent_events, pattern))
        anomalies.extend(self._detect_time_anomalies(key_id, recent_events, pattern))
        anomalies.extend(self._detect_operation_anomalies(key_id, recent_events, pattern, key_info))
        anomalies.extend(self._detect_user_anomalies(key_id, recent_events, pattern, key_info))
        anomalies.extend(self._detect_ip_anomalies(key_id, recent_events, pattern, key_info))
        anomalies.extend(self._detect_failure_anomalies(key_id, recent_events))
        anomalies.extend(self._detect_expired_key_usage(key_id, recent_events, key_info))
        anomalies.extend(self._detect_volume_spikes(key_id, recent_events, pattern))

        return anomalies

    def _detect_frequency_anomalies(
        self, key_id: str, events: list[KeyUsageEvent], pattern: UsagePattern | None
    ) -> list[KeyAnomalyAlert]:
        """Detect unusual frequency of key usage."""
        if not pattern or not pattern.daily_usage_stats:
            return []

        now = datetime.now(timezone.utc)
        today = now.date()
        today_events = [e for e in events if e.timestamp.date() == today]

        daily_count = len(today_events)
        expected_mean = pattern.daily_usage_stats["mean"]
        expected_std = pattern.daily_usage_stats["std"]

        # Calculate z-score
        if expected_std > 0:
            z_score = abs(daily_count - expected_mean) / expected_std

            if z_score > 3 * self.sensitivity:  # 3 standard deviations
                severity = AnomalySeverity.CRITICAL if z_score > 5 else AnomalySeverity.HIGH

                alert = KeyAnomalyAlert(
                    alert_id=self.generate_alert_id(key_id, AnomalyType.UNUSUAL_FREQUENCY),
                    key_id=key_id,
                    anomaly_type=AnomalyType.UNUSUAL_FREQUENCY,
                    severity=severity,
                    description=f"Unusual frequency: {daily_count} operations today (expected: {expected_mean:.1f}±{expected_std:.1f})",
                    detected_at=now,
                    events_involved=today_events,
                    confidence_score=min(z_score / 5.0, 1.0),
                    recommended_actions=[
                        "Review recent key usage patterns",
                        "Check for automated processes",
                        "Verify user authorization",
                    ],
                )

                return [alert]

        return []

    def _detect_time_anomalies(
        self, key_id: str, events: list[KeyUsageEvent], pattern: UsagePattern | None
    ) -> list[KeyAnomalyAlert]:
        """Detect usage at unusual times."""
        if not pattern or not pattern.common_time_ranges:
            return []

        unusual_events = []

        for event in events:
            event_hour = event.timestamp.hour
            is_in_normal_range = any(
                start <= event_hour <= end for start, end in pattern.common_time_ranges
            )

            if not is_in_normal_range:
                unusual_events.append(event)

        if len(unusual_events) > len(events) * 0.3:  # More than 30% outside normal hours
            alert = KeyAnomalyAlert(
                alert_id=self.generate_alert_id(key_id, AnomalyType.TIME_ANOMALY),
                key_id=key_id,
                anomaly_type=AnomalyType.TIME_ANOMALY,
                severity=AnomalySeverity.MEDIUM,
                description=f"Key used outside normal hours: {len(unusual_events)} events",
                detected_at=datetime.now(timezone.utc),
                events_involved=unusual_events,
                confidence_score=len(unusual_events) / len(events),
                recommended_actions=[
                    "Verify after-hours access authorization",
                    "Check for automated processes",
                    "Review time-based access controls",
                ],
            )

            return [alert]

        return []

    def _detect_operation_anomalies(
        self,
        key_id: str,
        events: list[KeyUsageEvent],
        pattern: UsagePattern | None,
        key_info: KeyInfo | None,
    ) -> list[KeyAnomalyAlert]:
        """Detect unusual operations on the key."""
        anomalies = []

        # Check against allowed operations
        if key_info and key_info.allowed_operations:
            unauthorized_ops = [
                event for event in events if event.operation not in key_info.allowed_operations
            ]

            if unauthorized_ops:
                alert = KeyAnomalyAlert(
                    alert_id=self.generate_alert_id(key_id, AnomalyType.OPERATION_ANOMALY),
                    key_id=key_id,
                    anomaly_type=AnomalyType.OPERATION_ANOMALY,
                    severity=AnomalySeverity.HIGH,
                    description=f"Unauthorized operations detected: {len(unauthorized_ops)} events",
                    detected_at=datetime.now(timezone.utc),
                    events_involved=unauthorized_ops,
                    confidence_score=1.0,
                    recommended_actions=[
                        "Review key operation permissions",
                        "Investigate unauthorized access",
                        "Consider revoking key if compromised",
                    ],
                )
                anomalies.append(alert)

        # Check against historical patterns
        if pattern and pattern.common_operations:
            unusual_ops = [
                event for event in events if event.operation not in pattern.common_operations
            ]

            if len(unusual_ops) > len(events) * 0.5:  # More than 50% unusual operations
                alert = KeyAnomalyAlert(
                    alert_id=self.generate_alert_id(key_id, AnomalyType.PATTERN_DEVIATION),
                    key_id=key_id,
                    anomaly_type=AnomalyType.PATTERN_DEVIATION,
                    severity=AnomalySeverity.MEDIUM,
                    description=f"Unusual operations pattern: {len(unusual_ops)} events",
                    detected_at=datetime.now(timezone.utc),
                    events_involved=unusual_ops,
                    confidence_score=len(unusual_ops) / len(events),
                    recommended_actions=[
                        "Review new operation patterns",
                        "Verify legitimate usage",
                        "Update usage patterns if appropriate",
                    ],
                )
                anomalies.append(alert)

        return anomalies

    def _detect_user_anomalies(
        self,
        key_id: str,
        events: list[KeyUsageEvent],
        pattern: UsagePattern | None,
        key_info: KeyInfo | None,
    ) -> list[KeyAnomalyAlert]:
        """Detect usage by unauthorized users."""
        anomalies = []

        # Check against allowed users
        if key_info and key_info.allowed_users:
            unauthorized_events = [
                event for event in events if event.user_id not in key_info.allowed_users
            ]

            if unauthorized_events:
                alert = KeyAnomalyAlert(
                    alert_id=self.generate_alert_id(key_id, AnomalyType.UNAUTHORIZED_ACCESS),
                    key_id=key_id,
                    anomaly_type=AnomalyType.UNAUTHORIZED_ACCESS,
                    severity=AnomalySeverity.CRITICAL,
                    description=f"Unauthorized user access: {len(unauthorized_events)} events",
                    detected_at=datetime.now(timezone.utc),
                    events_involved=unauthorized_events,
                    confidence_score=1.0,
                    recommended_actions=[
                        "Immediately investigate unauthorized access",
                        "Review user permissions",
                        "Consider emergency key rotation",
                        "Check for compromised accounts",
                    ],
                )
                anomalies.append(alert)

        return anomalies

    def _detect_ip_anomalies(
        self,
        key_id: str,
        events: list[KeyUsageEvent],
        pattern: UsagePattern | None,
        key_info: KeyInfo | None,
    ) -> list[KeyAnomalyAlert]:
        """Detect usage from unusual IP addresses."""
        if not pattern or not pattern.common_ip_ranges:
            return []

        unusual_events = []

        for event in events:
            ip_parts = event.source_ip.split(".")
            if len(ip_parts) >= 3:
                ip_network = ".".join(ip_parts[:3]) + ".0"
                if ip_network not in pattern.common_ip_ranges:
                    unusual_events.append(event)

        if len(unusual_events) > len(events) * 0.2:  # More than 20% from unusual IPs
            alert = KeyAnomalyAlert(
                alert_id=self.generate_alert_id(key_id, AnomalyType.LOCATION_ANOMALY),
                key_id=key_id,
                anomaly_type=AnomalyType.LOCATION_ANOMALY,
                severity=AnomalySeverity.MEDIUM,
                description=f"Access from unusual IP addresses: {len(unusual_events)} events",
                detected_at=datetime.now(timezone.utc),
                events_involved=unusual_events,
                confidence_score=len(unusual_events) / len(events),
                recommended_actions=[
                    "Verify source IP addresses",
                    "Check VPN and remote access logs",
                    "Review network access controls",
                    "Consider IP whitelisting",
                ],
            )

            return [alert]

        return []

    def _detect_failure_anomalies(
        self, key_id: str, events: list[KeyUsageEvent]
    ) -> list[KeyAnomalyAlert]:
        """Detect unusual number of failed operations."""
        failed_events = [e for e in events if not e.success]

        if not failed_events:
            return []

        failure_rate = len(failed_events) / len(events)

        if failure_rate > 0.1:  # More than 10% failure rate
            severity = AnomalySeverity.HIGH if failure_rate > 0.5 else AnomalySeverity.MEDIUM

            alert = KeyAnomalyAlert(
                alert_id=self.generate_alert_id(key_id, AnomalyType.FAILED_OPERATIONS),
                key_id=key_id,
                anomaly_type=AnomalyType.FAILED_OPERATIONS,
                severity=severity,
                description=f"High failure rate: {failure_rate:.1%} ({len(failed_events)} failed operations)",
                detected_at=datetime.now(timezone.utc),
                events_involved=failed_events,
                confidence_score=failure_rate,
                recommended_actions=[
                    "Investigate operation failures",
                    "Check key validity and permissions",
                    "Review error messages",
                    "Consider key health check",
                ],
            )

            return [alert]

        return []

    def _detect_expired_key_usage(
        self, key_id: str, events: list[KeyUsageEvent], key_info: KeyInfo | None
    ) -> list[KeyAnomalyAlert]:
        """Detect usage of expired or revoked keys."""
        if not key_info:
            return []

        anomalies = []

        # Check for expired key usage
        if key_info.expires_at:
            expired_events = [e for e in events if e.timestamp > key_info.expires_at]
            if expired_events:
                alert = KeyAnomalyAlert(
                    alert_id=self.generate_alert_id(key_id, AnomalyType.EXPIRED_KEY_USAGE),
                    key_id=key_id,
                    anomaly_type=AnomalyType.EXPIRED_KEY_USAGE,
                    severity=AnomalySeverity.CRITICAL,
                    description=f"Expired key usage detected: {len(expired_events)} events",
                    detected_at=datetime.now(timezone.utc),
                    events_involved=expired_events,
                    confidence_score=1.0,
                    recommended_actions=[
                        "Immediately stop using expired key",
                        "Rotate to new key",
                        "Investigate how expired key was used",
                        "Update key management procedures",
                    ],
                )
                anomalies.append(alert)

        # Check for revoked key usage
        if key_info.is_revoked and key_info.revoked_at:
            revoked_events = [e for e in events if e.timestamp > key_info.revoked_at]
            if revoked_events:
                alert = KeyAnomalyAlert(
                    alert_id=self.generate_alert_id(key_id, AnomalyType.REVOKED_KEY_USAGE),
                    key_id=key_id,
                    anomaly_type=AnomalyType.REVOKED_KEY_USAGE,
                    severity=AnomalySeverity.CRITICAL,
                    description=f"Revoked key usage detected: {len(revoked_events)} events",
                    detected_at=datetime.now(timezone.utc),
                    events_involved=revoked_events,
                    confidence_score=1.0,
                    recommended_actions=[
                        "Immediately investigate revoked key usage",
                        "Check key revocation procedures",
                        "Verify key access controls",
                        "Consider security incident response",
                    ],
                )
                anomalies.append(alert)

        return anomalies

    def _detect_volume_spikes(
        self, key_id: str, events: list[KeyUsageEvent], pattern: UsagePattern | None
    ) -> list[KeyAnomalyAlert]:
        """Detect sudden volume spikes in key usage."""
        if not pattern or not pattern.hourly_usage_stats:
            return []

        now = datetime.now(timezone.utc)
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        # Count events in current hour
        current_hour_events = [
            e
            for e in events
            if e.timestamp >= current_hour and e.timestamp < current_hour + timedelta(hours=1)
        ]

        hourly_count = len(current_hour_events)
        expected_mean = pattern.hourly_usage_stats["mean"]
        expected_std = pattern.hourly_usage_stats["std"]

        if expected_std > 0:
            z_score = (hourly_count - expected_mean) / expected_std

            if z_score > 4 * self.sensitivity:  # Significant spike
                alert = KeyAnomalyAlert(
                    alert_id=self.generate_alert_id(key_id, AnomalyType.VOLUME_SPIKE),
                    key_id=key_id,
                    anomaly_type=AnomalyType.VOLUME_SPIKE,
                    severity=AnomalySeverity.HIGH,
                    description=f"Volume spike detected: {hourly_count} operations this hour (expected: {expected_mean:.1f})",
                    detected_at=now,
                    events_involved=current_hour_events,
                    confidence_score=min(z_score / 6.0, 1.0),
                    recommended_actions=[
                        "Investigate sudden increase in key usage",
                        "Check for bulk operations or attacks",
                        "Review system logs for anomalies",
                        "Consider rate limiting",
                    ],
                )

                return [alert]

        return []

    def generate_alert_id(self, key_id: str, anomaly_type: AnomalyType) -> str:
        """Generate a unique alert ID."""
        timestamp = int(datetime.now(timezone.utc).timestamp())
        data = f"{key_id}-{anomaly_type.value}-{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


class KeyUsageAnomalyMonitor:
    """Main key usage anomaly monitoring system."""

    def __init__(
        self,
        check_interval_minutes: int = 15,
        learning_window_days: int = 30,
        sensitivity: float = 0.8,
    ) -> None:
        self.check_interval_minutes = check_interval_minutes
        self.learning_window_days = learning_window_days

        self.collector = KeyUsageCollector()
        self.pattern_learner = PatternLearner(learning_window_days)
        self.detector = AnomalyDetector(sensitivity)

        self.keys: dict[str, KeyInfo] = {}
        self.alerts: dict[str, KeyAnomalyAlert] = {}
        self.alert_callbacks: list[Callable[[KeyAnomalyAlert], None]] = []

        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def add_key(self, key_info: KeyInfo) -> None:
        """Add a key for monitoring."""
        with self._lock:
            self.keys[key_info.key_id] = key_info
        logger.info(f"Added key for monitoring: {key_info.key_id}")

    def remove_key(self, key_id: str) -> None:
        """Remove a key from monitoring."""
        with self._lock:
            self.keys.pop(key_id, None)
        logger.info(f"Removed key from monitoring: {key_id}")

    def add_alert_callback(self, callback: Callable[[KeyAnomalyAlert], None]) -> None:
        """Add callback for anomaly alerts."""
        self.alert_callbacks.append(callback)

    def record_key_usage(self, event: KeyUsageEvent) -> None:
        """Record a key usage event."""
        self.collector.add_event(event)

    def start_monitoring(self) -> None:
        """Start the anomaly monitoring process."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Key usage anomaly monitoring is already running")
            return

        # Set up event listener for real-time detection
        self.collector.add_event_listener(self._process_real_time_event)

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Key usage anomaly monitoring started")

    def stop_monitoring(self) -> None:
        """Stop the anomaly monitoring process."""
        if self._monitor_thread:
            self._stop_event.set()
            self._monitor_thread.join()
        logger.info("Key usage anomaly monitoring stopped")

    def _process_real_time_event(self, event: KeyUsageEvent) -> None:
        """Process events in real-time for immediate threat detection."""
        with self._lock:
            key_info = self.keys.get(event.key_id)

        if not key_info:
            return

        # Check for immediate critical issues
        datetime.now(timezone.utc)

        # Expired key usage
        if key_info.expires_at and event.timestamp > key_info.expires_at:
            self._create_immediate_alert(
                event.key_id,
                AnomalyType.EXPIRED_KEY_USAGE,
                AnomalySeverity.CRITICAL,
                "Expired key usage detected immediately",
                [event],
            )

        # Revoked key usage
        if key_info.is_revoked and key_info.revoked_at and event.timestamp > key_info.revoked_at:
            self._create_immediate_alert(
                event.key_id,
                AnomalyType.REVOKED_KEY_USAGE,
                AnomalySeverity.CRITICAL,
                "Revoked key usage detected immediately",
                [event],
            )

        # Unauthorized user
        if key_info.allowed_users and event.user_id not in key_info.allowed_users:
            self._create_immediate_alert(
                event.key_id,
                AnomalyType.UNAUTHORIZED_ACCESS,
                AnomalySeverity.CRITICAL,
                f"Unauthorized user access: {event.user_id}",
                [event],
            )

        # Unauthorized operation
        if key_info.allowed_operations and event.operation not in key_info.allowed_operations:
            self._create_immediate_alert(
                event.key_id,
                AnomalyType.OPERATION_ANOMALY,
                AnomalySeverity.HIGH,
                f"Unauthorized operation: {event.operation.value}",
                [event],
            )

    def _create_immediate_alert(
        self,
        key_id: str,
        anomaly_type: AnomalyType,
        severity: AnomalySeverity,
        description: str,
        events: list[KeyUsageEvent],
    ) -> None:
        """Create an immediate alert for critical issues."""
        alert_id = self.detector.generate_alert_id(key_id, anomaly_type)

        # Check if we already have a similar alert recently
        recent_alerts = [
            alert
            for alert in self.alerts.values()
            if alert.key_id == key_id
            and alert.anomaly_type == anomaly_type
            and (datetime.now(timezone.utc) - alert.detected_at).seconds < 3600
        ]

        if recent_alerts:
            return  # Don't spam alerts

        alert = KeyAnomalyAlert(
            alert_id=alert_id,
            key_id=key_id,
            anomaly_type=anomaly_type,
            severity=severity,
            description=description,
            detected_at=datetime.now(timezone.utc),
            events_involved=events,
            confidence_score=1.0,
            recommended_actions=[
                "Immediate investigation required",
                "Consider emergency response procedures",
            ],
        )

        with self._lock:
            self.alerts[alert_id] = alert

        # Notify callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.exception(f"Error sending immediate alert via callback: {e}")

        logger.critical(f"IMMEDIATE ALERT: {description}")

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while not self._stop_event.is_set():
            try:
                self._run_periodic_analysis()
                self._stop_event.wait(self.check_interval_minutes * 60)

            except Exception as e:
                logger.exception(f"Error in key usage monitoring loop: {e}")
                self._stop_event.wait(300)  # Wait 5 minutes before retrying

    def _run_periodic_analysis(self) -> None:
        """Run periodic anomaly analysis."""
        now = datetime.now(timezone.utc)
        analysis_window = now - timedelta(hours=24)  # Analyze last 24 hours

        with self._lock:
            keys_to_analyze = list(self.keys.keys())

        for key_id in keys_to_analyze:
            try:
                # Get recent events
                events = self.collector.get_events_for_key(key_id, analysis_window, now)
                if not events:
                    continue

                # Update pattern learning
                learning_start = now - timedelta(days=self.learning_window_days)
                historical_events = self.collector.get_events_for_key(key_id, learning_start, now)
                self.pattern_learner.update_pattern(key_id, historical_events)

                # Get pattern and key info
                pattern = self.pattern_learner.get_pattern(key_id)
                key_info = self.keys.get(key_id)

                # Detect anomalies
                anomalies = self.detector.detect_anomalies(key_id, events, pattern, key_info)

                # Process new anomalies
                for anomaly in anomalies:
                    # Check if we already have this alert
                    existing_alert = self.alerts.get(anomaly.alert_id)
                    if not existing_alert:
                        with self._lock:
                            self.alerts[anomaly.alert_id] = anomaly

                        # Notify callbacks
                        for callback in self.alert_callbacks:
                            try:
                                callback(anomaly)
                            except Exception as e:
                                logger.exception(f"Error sending anomaly alert via callback: {e}")

                        logger.warning(f"Key usage anomaly detected: {anomaly.description}")

            except Exception as e:
                logger.exception(f"Error analyzing key {key_id}: {e}")

    def get_alerts(
        self,
        key_id: str | None = None,
        severity: AnomalySeverity | None = None,
        unacknowledged_only: bool = False,
    ) -> list[KeyAnomalyAlert]:
        """Get anomaly alerts with optional filtering."""
        with self._lock:
            alerts = list(self.alerts.values())

        if key_id:
            alerts = [a for a in alerts if a.key_id == key_id]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if unacknowledged_only:
            alerts = [a for a in alerts if not a.acknowledged]

        return sorted(alerts, key=lambda a: a.detected_at, reverse=True)

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an anomaly alert."""
        with self._lock:
            alert = self.alerts.get(alert_id)
            if alert:
                alert.acknowledged = True
                alert.acknowledged_by = acknowledged_by
                alert.acknowledged_at = datetime.now(timezone.utc)
                logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
                return True
            return False

    def resolve_alert(self, alert_id: str, resolved_by: str) -> bool:
        """Resolve an anomaly alert."""
        with self._lock:
            alert = self.alerts.get(alert_id)
            if alert:
                alert.resolved = True
                alert.resolved_by = resolved_by
                alert.resolved_at = datetime.now(timezone.utc)
                logger.info(f"Alert {alert_id} resolved by {resolved_by}")
                return True
            return False


def create_key_usage_monitor(
    check_interval_minutes: int = 15, learning_window_days: int = 30, sensitivity: float = 0.8
) -> KeyUsageAnomalyMonitor:
    """Create a key usage anomaly monitor with default settings."""
    return KeyUsageAnomalyMonitor(check_interval_minutes, learning_window_days, sensitivity)
