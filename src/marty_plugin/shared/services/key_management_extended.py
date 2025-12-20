#!/usr/bin/env python3
"""
Extended Key Management Service Features.

This module provides additional functionality for the Key Management Service:
1. Automatic key rotation scheduling
2. Key usage tracking
3. Security reporting
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
import threading
from collections import defaultdict
from typing import Any

from .key_management_service import KeyManagementService, KeyType

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class KeyRotationScheduler:
    """
    Scheduler for automatic key rotation based on rotation policies.

    This class provides functionality to automatically check keys for
    rotation eligibility based on their rotation policies and rotate
    them when necessary.
    """

    def __init__(self, key_management_service: KeyManagementService) -> None:
        """
        Initialize the key rotation scheduler.

        Args:
            key_management_service: The key management service to use
        """
        self.key_management_service = key_management_service
        self._scheduler_thread = None
        self._scheduler_running = False
        self._stop_event = threading.Event()

        logger.info("Initialized Key Rotation Scheduler")

    def start(self, check_interval_seconds: int = 3600) -> None:
        """
        Start the key rotation scheduler.

        Args:
            check_interval_seconds: How often to check for keys that need rotation (in seconds)
        """
        if self._scheduler_running:
            logger.warning("Scheduler is already running")
            return

        self._stop_event.clear()
        self._scheduler_running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, args=(check_interval_seconds,), daemon=True
        )
        self._scheduler_thread.start()

        logger.info(f"Started key rotation scheduler (check interval: {check_interval_seconds}s)")

    def stop(self) -> None:
        """Stop the key rotation scheduler."""
        if not self._scheduler_running:
            logger.warning("Scheduler is not running")
            return

        self._stop_event.set()
        self._scheduler_thread.join(timeout=5.0)
        self._scheduler_running = False

        logger.info("Stopped key rotation scheduler")

    def _scheduler_loop(self, check_interval_seconds: int) -> None:
        """
        Main scheduler loop that periodically checks keys for rotation.

        Args:
            check_interval_seconds: How often to check for keys that need rotation
        """
        while not self._stop_event.is_set():
            try:
                self._check_and_rotate_keys()
            except Exception as e:
                logger.exception(f"Error in key rotation check: {e!s}")

            # Wait for the next check interval or until stopped
            self._stop_event.wait(check_interval_seconds)

    def _check_and_rotate_keys(self) -> None:
        """
        Check all keys with rotation policies and rotate those that need it.
        """
        logger.debug("Checking for keys that need rotation")
        now = datetime.datetime.now()
        rotated_keys = 0

        # Get all keys
        all_keys = self.key_management_service.list_keys()

        for key_info in all_keys:
            key_id = key_info.get("key_id")

            # Skip keys that don't have a rotation policy or are already rotated
            if "rotation_policy" not in key_info or key_info.get("rotated", False):
                continue

            rotation_policy = key_info["rotation_policy"]

            # Skip keys where auto_rotate is disabled
            if not rotation_policy.get("auto_rotate", False):
                continue

            # Check if the key is due for rotation
            if "last_rotation" in rotation_policy:
                try:
                    last_rotation = datetime.datetime.fromisoformat(
                        rotation_policy["last_rotation"]
                    )
                    interval_days = rotation_policy["rotation_interval_days"]
                    next_rotation = last_rotation + datetime.timedelta(days=interval_days)

                    if now >= next_rotation:
                        logger.info(f"Key {key_id} is due for rotation")
                        new_key_info = self.key_management_service.rotate_key(key_id)
                        logger.info(f"Rotated key {key_id} to {new_key_info['key_id']}")
                        rotated_keys += 1
                except (ValueError, KeyError) as e:
                    logger.warning(f"Error checking rotation for key {key_id}: {e!s}")
            else:
                # If there's no last_rotation date, assume this is a new policy and set it
                key_info["rotation_policy"]["last_rotation"] = now.isoformat()
                self.key_management_service._save_key_info(key_id, key_info)

        logger.info(f"Rotation check completed. Rotated {rotated_keys} keys.")


class KeyUsageTracker:
    """
    Tracker for key usage operations.

    This class provides functionality to record and query key usage data,
    enabling monitoring of how keys are used over time.
    """

    def __init__(
        self, key_management_service: KeyManagementService, usage_db_path: str | None = None
    ) -> None:
        """
        Initialize the key usage tracker.

        Args:
            key_management_service: The key management service to use
            usage_db_path: Path to the SQLite database for usage data
        """
        self.key_management_service = key_management_service

        # Set default database path if not provided
        if usage_db_path is None:
            base_dir = os.path.dirname(key_management_service.key_store_path)
            self.usage_db_path = os.path.join(base_dir, "key_usage.db")
        else:
            self.usage_db_path = usage_db_path

        # Initialize the database
        self._initialize_database()

        logger.info(f"Initialized Key Usage Tracker with database at {self.usage_db_path}")

    def _initialize_database(self) -> None:
        """Initialize the SQLite database for storing usage data."""
        try:
            conn = sqlite3.connect(self.usage_db_path)
            cursor = conn.cursor()

            # Create the usage table if it doesn't exist
            cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS key_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                operation TEXT NOT NULL,
                details TEXT
            )
            """
            )

            # Create indices for faster queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_key_id ON key_usage(key_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON key_usage(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation ON key_usage(operation)")

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            logger.exception(f"Database initialization error: {e!s}")
            raise

    def record_usage(
        self, key_id: str, operation: str, details: dict[str, Any] | None = None
    ) -> None:
        """
        Record a usage event for a key.

        Args:
            key_id: Identifier of the key
            operation: Type of operation performed with the key
            details: Additional details about the usage
        """
        # Verify the key exists
        try:
            self.key_management_service.get_key_info(key_id)
        except Exception as e:
            logger.warning(f"Attempted to record usage for non-existent key {key_id}: {e!s}")
            return

        timestamp = datetime.datetime.now().isoformat()
        details_json = json.dumps(details or {})

        try:
            conn = sqlite3.connect(self.usage_db_path)
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO key_usage (key_id, timestamp, operation, details) VALUES (?, ?, ?, ?)",
                (key_id, timestamp, operation, details_json),
            )

            conn.commit()
            conn.close()

            logger.debug(f"Recorded {operation} usage for key {key_id}")

        except sqlite3.Error as e:
            logger.exception(f"Error recording key usage: {e!s}")

    def get_key_usage(
        self,
        key_id: str,
        operation: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Get usage data for a key.

        Args:
            key_id: Identifier of the key
            operation: Optional filter for operation type
            start_time: Optional start time for filtering (ISO format)
            end_time: Optional end time for filtering (ISO format)
            limit: Maximum number of records to return

        Returns:
            List of usage records
        """
        query = "SELECT timestamp, operation, details FROM key_usage WHERE key_id = ?"
        params = [key_id]

        # Add filters if provided
        if operation:
            query += " AND operation = ?"
            params.append(operation)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time:
            # Use strict less than for end_time to exclude the end time point
            query += " AND timestamp < ?"
            params.append(end_time)

        # Add ordering and limit
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        try:
            conn = sqlite3.connect(self.usage_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(query, params)
            rows = cursor.fetchall()

            result = []
            for row in rows:
                record = {
                    "timestamp": row["timestamp"],
                    "operation": row["operation"],
                    "details": json.loads(row["details"]),
                }
                result.append(record)

            conn.close()
        except sqlite3.Error as e:
            logger.exception(f"Error retrieving key usage: {e!s}")
            return []
        else:
            return result

    def get_usage_statistics(self, key_id: str) -> dict[str, Any]:
        """
        Generate statistics about key usage.

        Args:
            key_id: Identifier of the key

        Returns:
            Dictionary with usage statistics
        """
        conn = None
        try:
            conn = sqlite3.connect(self.usage_db_path)
            cursor = conn.cursor()

            # Get total number of usages
            cursor.execute("SELECT COUNT(*) FROM key_usage WHERE key_id = ?", (key_id,))
            total_usages = cursor.fetchone()[0]

            # Get counts by operation
            cursor.execute(
                "SELECT operation, COUNT(*) FROM key_usage WHERE key_id = ? GROUP BY operation",
                (key_id,),
            )
            operation_counts = {row[0]: row[1] for row in cursor.fetchall()}

            # Extract document types from details and count them
            document_types = defaultdict(int)
            cursor.execute("SELECT details FROM key_usage WHERE key_id = ?", (key_id,))
            for row in cursor.fetchall():
                details = json.loads(row[0])
                if "document_type" in details:
                    document_types[details["document_type"]] += 1

            # Get the first and last usage timestamps
            cursor.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM key_usage WHERE key_id = ?", (key_id,)
            )
            time_row = cursor.fetchone()
            first_usage = time_row[0] if time_row and time_row[0] else None
            last_usage = time_row[1] if time_row and time_row[1] else None

            conn.close()

            return {
                "total_usages": total_usages,
                "operations": operation_counts,
                "document_types": dict(document_types),
                "first_usage": first_usage,
                "last_usage": last_usage,
            }

        except sqlite3.Error as e:
            logger.exception(f"Error generating usage statistics: {e!s}")
            if conn:
                conn.close()
            return {"total_usages": 0, "operations": {}, "document_types": {}}


class SecurityReportGenerator:
    """
    Generator for security reports about key management.

    This class analyzes keys and their usage patterns to generate
    reports on security risks, weaknesses, and recommendations.
    """

    # Security thresholds
    MIN_SECURE_RSA_KEY_SIZE = 2048
    MIN_SECURE_EC_CURVES = {"secp256r1", "secp384r1", "secp521r1"}
    MAX_RECOMMENDED_KEY_AGE_DAYS = 365
    MAX_RECOMMENDED_ROTATION_INTERVAL = 180
    HIGH_USAGE_THRESHOLD = 500

    def __init__(
        self,
        key_management_service: KeyManagementService,
        usage_tracker: KeyUsageTracker | None = None,
    ) -> None:
        """
        Initialize the security report generator.

        Args:
            key_management_service: The key management service to use
            usage_tracker: Optional key usage tracker for usage-based analysis
        """
        self.key_management_service = key_management_service
        self.usage_tracker = usage_tracker

        logger.info("Initialized Security Report Generator")

    def generate_key_strength_report(self) -> dict[str, Any]:
        """
        Generate a report on key strength issues.

        Returns:
            Dictionary with key strength analysis
        """
        logger.info("Generating key strength report")

        weak_keys = []
        recommended_actions = {}

        # Get all keys
        all_keys = self.key_management_service.list_keys()

        for key_info in all_keys:
            key_id = key_info.get("key_id")
            key_type = key_info.get("key_type")

            # Check RSA key sizes
            if key_type == KeyType.RSA.value:
                key_size = key_info.get("key_size")
                if key_size and key_size < self.MIN_SECURE_RSA_KEY_SIZE:
                    weak_keys.append(key_id)
                    recommended_actions[key_id] = (
                        f"Increase RSA key size from {key_size} to at least {self.MIN_SECURE_RSA_KEY_SIZE} bits"
                    )

            # Check EC curves
            elif key_type == KeyType.EC.value:
                curve_name = key_info.get("curve_name")
                if curve_name and curve_name not in self.MIN_SECURE_EC_CURVES:
                    weak_keys.append(key_id)
                    recommended_actions[key_id] = (
                        f"Replace EC curve {curve_name} with a stronger curve like secp256r1"
                    )

        return {
            "weak_keys": weak_keys,
            "recommended_actions": recommended_actions,
            "total_keys_analyzed": len(all_keys),
            "keys_with_strength_issues": len(weak_keys),
        }

    def generate_expiry_report(self) -> dict[str, Any]:
        """
        Generate a report on key expiry status.

        Returns:
            Dictionary with key expiry analysis
        """
        logger.info("Generating key expiry report")

        expired_keys = []
        expiring_soon_keys = []
        keys_without_expiry = []

        # Get all keys
        all_keys = self.key_management_service.list_keys()
        now = datetime.datetime.now()

        for key_info in all_keys:
            key_id = key_info.get("key_id")

            if "expiry_date" in key_info:
                try:
                    expiry_date = datetime.datetime.fromisoformat(key_info["expiry_date"])
                    days_until_expiry = (expiry_date - now).days

                    if days_until_expiry < 0:
                        expired_keys.append(key_id)
                    elif days_until_expiry < 30:
                        expiring_soon_keys.append(
                            {"key_id": key_id, "days_until_expiry": days_until_expiry}
                        )
                except (ValueError, TypeError):
                    logger.warning(f"Invalid expiry date format for key {key_id}")
            else:
                keys_without_expiry.append(key_id)

        return {
            "expired_keys": expired_keys,
            "expiring_soon_keys": expiring_soon_keys,
            "keys_without_expiry": keys_without_expiry,
            "total_keys_analyzed": len(all_keys),
        }

    def generate_rotation_policy_report(self) -> dict[str, Any]:
        """
        Generate a report on key rotation policies.

        Returns:
            Dictionary with rotation policy analysis
        """
        logger.info("Generating rotation policy report")

        keys_without_policy = []
        keys_with_policy = []
        keys_with_long_intervals = []
        non_auto_rotate_keys = []

        # Get all keys
        all_keys = self.key_management_service.list_keys()

        for key_info in all_keys:
            key_id = key_info.get("key_id")

            if "rotation_policy" in key_info:
                policy = key_info["rotation_policy"]
                keys_with_policy.append(key_id)

                interval_days = policy.get("rotation_interval_days")
                if interval_days and interval_days > self.MAX_RECOMMENDED_ROTATION_INTERVAL:
                    keys_with_long_intervals.append(
                        {"key_id": key_id, "interval_days": interval_days}
                    )

                if not policy.get("auto_rotate", False):
                    non_auto_rotate_keys.append(key_id)
            else:
                keys_without_policy.append(key_id)

        return {
            "keys_without_policy": keys_without_policy,
            "keys_with_policy": keys_with_policy,
            "keys_with_long_intervals": keys_with_long_intervals,
            "non_auto_rotate_keys": non_auto_rotate_keys,
            "total_keys_analyzed": len(all_keys),
        }

    def generate_usage_anomaly_report(self) -> dict[str, Any]:
        """
        Generate a report on key usage anomalies.

        Returns:
            Dictionary with usage anomaly analysis
        """
        logger.info("Generating usage anomaly report")

        if not self.usage_tracker:
            logger.warning("No usage tracker provided, skipping usage anomaly report")
            return {
                "error": "No usage tracker provided",
                "high_usage_weak_keys": [],
                "usage_of_expired_keys": [],
                "abnormal_usage_patterns": [],
            }

        high_usage_weak_keys = []
        usage_of_expired_keys = []
        abnormal_usage_patterns = []

        # Get key strength information
        strength_report = self.generate_key_strength_report()
        weak_keys = set(strength_report["weak_keys"])

        # Get expiry information
        expiry_report = self.generate_expiry_report()
        expired_keys = set(expiry_report["expired_keys"])

        # Get all keys
        all_keys = self.key_management_service.list_keys()

        for key_info in all_keys:
            key_id = key_info.get("key_id")

            # Get usage statistics for this key
            usage_stats = self.usage_tracker.get_usage_statistics(key_id)
            total_usages = usage_stats.get("total_usages", 0)

            # Check for weak keys with high usage
            if key_id in weak_keys and total_usages > self.HIGH_USAGE_THRESHOLD:
                high_usage_weak_keys.append({"key_id": key_id, "total_usages": total_usages})

            # Check for usage of expired keys
            if key_id in expired_keys and total_usages > 0:
                usage_of_expired_keys.append({"key_id": key_id, "total_usages": total_usages})

            # Analyze for abnormal usage patterns
            # (This is a simplified example - in reality, more sophisticated
            # anomaly detection would be implemented)
            if total_usages > 0:
                operations = usage_stats.get("operations", {})
                if len(operations) > 0:
                    # Calculate ratio of most common operation to total usages
                    most_common_op = max(operations.items(), key=lambda x: x[1])
                    ratio = most_common_op[1] / total_usages

                    # If one operation dominates unusually (>95%), flag it
                    if ratio > 0.95 and total_usages > 100:
                        abnormal_usage_patterns.append(
                            {
                                "key_id": key_id,
                                "pattern": f"Excessive use of {most_common_op[0]} operation ({ratio:.2%})",
                                "total_usages": total_usages,
                            }
                        )

        return {
            "high_usage_weak_keys": high_usage_weak_keys,
            "usage_of_expired_keys": usage_of_expired_keys,
            "abnormal_usage_patterns": abnormal_usage_patterns,
        }

    def generate_comprehensive_report(self) -> dict[str, Any]:
        """
        Generate a comprehensive security report.

        Returns:
            Dictionary with comprehensive security analysis
        """
        logger.info("Generating comprehensive security report")

        # Generate individual reports
        key_strength = self.generate_key_strength_report()
        expiry_status = self.generate_expiry_report()
        rotation_policies = self.generate_rotation_policy_report()
        usage_anomalies = self.generate_usage_anomaly_report()

        # Calculate security score
        security_score = self._calculate_security_score(
            key_strength, expiry_status, rotation_policies, usage_anomalies
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            key_strength, expiry_status, rotation_policies, usage_anomalies
        )

        return {
            "report_date": datetime.datetime.now().isoformat(),
            "key_strength": key_strength,
            "expiry_status": expiry_status,
            "rotation_policies": rotation_policies,
            "usage_anomalies": usage_anomalies,
            "overall_security_score": security_score,
            "recommendations": recommendations,
        }

    def _calculate_security_score(
        self,
        key_strength: dict[str, Any],
        expiry_status: dict[str, Any],
        rotation_policies: dict[str, Any],
        usage_anomalies: dict[str, Any],
    ) -> int:
        """
        Calculate an overall security score based on all reports.

        Args:
            key_strength: Key strength report
            expiry_status: Expiry status report
            rotation_policies: Rotation policy report
            usage_anomalies: Usage anomaly report

        Returns:
            Security score from 0-100 (higher is better)
        """
        total_keys = key_strength.get("total_keys_analyzed", 0)
        if total_keys == 0:
            return 0

        # Start with 100 points
        score = 100

        # Deduct points for weak keys (up to 25 points)
        weak_keys = len(key_strength.get("weak_keys", []))
        weak_key_penalty = min(25, (weak_keys / total_keys) * 50)
        score -= weak_key_penalty

        # Deduct points for expired keys (up to 25 points)
        expired_keys = len(expiry_status.get("expired_keys", []))
        expired_key_penalty = min(25, (expired_keys / total_keys) * 50)
        score -= expired_key_penalty

        # Deduct points for missing rotation policies (up to 20 points)
        keys_without_policy = len(rotation_policies.get("keys_without_policy", []))
        policy_penalty = min(20, (keys_without_policy / total_keys) * 30)
        score -= policy_penalty

        # Deduct points for usage anomalies (up to 20 points)
        high_usage_weak = len(usage_anomalies.get("high_usage_weak_keys", []))
        usage_expired = len(usage_anomalies.get("usage_of_expired_keys", []))
        anomaly_penalty = min(20, ((high_usage_weak + usage_expired) / max(1, total_keys)) * 40)
        score -= anomaly_penalty

        # Deduct points for non-auto-rotating keys (up to 10 points)
        non_auto = len(rotation_policies.get("non_auto_rotate_keys", []))
        auto_penalty = min(10, (non_auto / total_keys) * 15)
        score -= auto_penalty

        # Ensure score is between 0 and 100
        return max(0, min(100, round(score)))

    def _generate_recommendations(
        self,
        key_strength: dict[str, Any],
        expiry_status: dict[str, Any],
        rotation_policies: dict[str, Any],
        usage_anomalies: dict[str, Any],
    ) -> list[str]:
        """
        Generate security recommendations based on all reports.

        Args:
            key_strength: Key strength report
            expiry_status: Expiry status report
            rotation_policies: Rotation policy report
            usage_anomalies: Usage anomaly report

        Returns:
            List of security recommendations
        """
        recommendations = []

        # Add key strength recommendations
        weak_keys = len(key_strength.get("weak_keys", []))
        if weak_keys > 0:
            recommendations.append(
                f"Strengthen {weak_keys} weak keys to meet current security standards "
                f"(minimum {self.MIN_SECURE_RSA_KEY_SIZE} bits for RSA)"
            )

        # Add expiry recommendations
        expired_keys = len(expiry_status.get("expired_keys", []))
        if expired_keys > 0:
            recommendations.append(f"Replace or renew {expired_keys} expired keys")

        keys_without_expiry = len(expiry_status.get("keys_without_expiry", []))
        if keys_without_expiry > 0:
            recommendations.append(
                f"Set expiry dates for {keys_without_expiry} keys that currently have no expiration"
            )

        # Add rotation policy recommendations
        keys_without_policy = len(rotation_policies.get("keys_without_policy", []))
        if keys_without_policy > 0:
            recommendations.append(
                f"Implement rotation policies for {keys_without_policy} keys that have no policy"
            )

        keys_with_long_intervals = len(rotation_policies.get("keys_with_long_intervals", []))
        if keys_with_long_intervals > 0:
            recommendations.append(
                f"Reduce rotation intervals for {keys_with_long_intervals} keys "
                f"(recommended maximum: {self.MAX_RECOMMENDED_ROTATION_INTERVAL} days)"
            )

        # Add usage anomaly recommendations
        high_usage_weak = len(usage_anomalies.get("high_usage_weak_keys", []))
        if high_usage_weak > 0:
            recommendations.append(
                f"Immediately replace {high_usage_weak} weak keys that are frequently used"
            )

        usage_expired = len(usage_anomalies.get("usage_of_expired_keys", []))
        if usage_expired > 0:
            recommendations.append(
                f"Stop using {usage_expired} expired keys and replace them with new ones"
            )

        return recommendations
