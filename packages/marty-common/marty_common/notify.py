"""
Notification system for Marty services.

Provides a unified interface for sending notifications via email, webhook, and Slack.
Used primarily by the certificate lifecycle monitor for alerting.
"""

from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class NotificationSink(Protocol):
    """Protocol for notification sinks."""

    async def send(self, subject: str, message: str, level: str = "INFO") -> bool:
        """Send a notification."""
        ...


class EmailNotifier:
    """Email notification sink using SMTP."""

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize the email notifier.

        Args:
            config: Email configuration with keys:
                - recipients: List of email addresses
                - smtp_server: SMTP server hostname
                - smtp_port: SMTP server port (default: 587)
                - sender_email: Sender email address
                - use_tls: Whether to use TLS (default: True)
                - username: SMTP username (optional)
                - password: SMTP password (optional)
        """
        self.config = config
        self.recipients = config.get("recipients", [])
        self.smtp_server: str = config.get("smtp_server", "")
        self.smtp_port = config.get("smtp_port", 587)
        self.sender_email: str = config.get("sender_email", "")
        self.use_tls = config.get("use_tls", True)
        self.username = config.get("username")
        self.password = config.get("password")

        if not self.recipients or not self.smtp_server or not self.sender_email:
            raise ValueError("Email configuration missing required fields")

        # Ensure required fields are strings
        if not isinstance(self.smtp_server, str) or not isinstance(self.sender_email, str):
            raise ValueError("SMTP server and sender email must be strings")

    async def send(self, subject: str, message: str, level: str = "INFO") -> bool:
        """
        Send an email notification.

        Args:
            subject: Email subject
            message: Email body
            level: Notification level (INFO, WARNING, ERROR)

        Returns:
            True if email was sent successfully
        """
        try:
            # Create email message
            msg = EmailMessage()
            msg.set_content(message)
            msg["Subject"] = f"[{level}] {subject}"
            msg["From"] = self.sender_email
            msg["To"] = ", ".join(self.recipients)

            # Add headers for better categorization
            msg["X-Marty-Notification-Level"] = level
            msg["X-Marty-Component"] = "certificate-lifecycle-monitor"

            # Connect to SMTP server and send
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                # Authenticate if credentials are provided
                if self.username and self.password:
                    server.login(self.username, self.password)

                server.send_message(msg)

            logger.info("Email notification sent to %s recipients", len(self.recipients))
            return True

        except Exception as e:
            logger.exception("Failed to send email notification: %s", e)
            return False


class WebhookNotifier:
    """Generic webhook notification sink."""

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize the webhook notifier.

        Args:
            config: Webhook configuration with keys:
                - url: Webhook URL
                - timeout: Request timeout in seconds (default: 30)
                - headers: Additional HTTP headers (optional)
        """
        self.url: str = config.get("url", "")
        self.timeout = config.get("timeout", 30)
        self.headers = config.get("headers", {})

        if not self.url:
            raise ValueError("Webhook URL is required")

        # Ensure URL is a string
        if not isinstance(self.url, str):
            raise ValueError("Webhook URL must be a string")

        # Validate URL format
        parsed = urlparse(self.url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid webhook URL: {self.url}")

    async def send(self, subject: str, message: str, level: str = "INFO") -> bool:
        """
        Send a webhook notification.

        Args:
            subject: Notification subject
            message: Notification message
            level: Notification level (INFO, WARNING, ERROR)

        Returns:
            True if webhook was sent successfully
        """
        try:
            payload = {
                "subject": subject,
                "message": message,
                "level": level,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "component": "certificate-lifecycle-monitor",
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Marty/1.0 (Certificate Lifecycle Monitor)",
                **self.headers,
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()

            logger.info("Webhook notification sent to %s", self.url)
            return True

        except Exception as e:
            logger.exception("Failed to send webhook notification: %s", e)
            return False


class SlackNotifier:
    """Slack notification sink using webhooks."""

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize the Slack notifier.

        Args:
            config: Slack configuration with keys:
                - webhook_url: Slack webhook URL
                - channel: Slack channel (optional, override webhook default)
                - username: Bot username (optional)
                - timeout: Request timeout in seconds (default: 30)
        """
        self.webhook_url: str = config.get("webhook_url", "")
        self.channel = config.get("channel")
        self.username = config.get("username", "Marty Certificate Monitor")
        self.timeout = config.get("timeout", 30)

        if not self.webhook_url:
            raise ValueError("Slack webhook URL is required")

        # Ensure webhook URL is a string
        if not isinstance(self.webhook_url, str):
            raise ValueError("Slack webhook URL must be a string")

    async def send(self, subject: str, message: str, level: str = "INFO") -> bool:
        """
        Send a Slack notification.

        Args:
            subject: Notification subject
            message: Notification message
            level: Notification level (INFO, WARNING, ERROR)

        Returns:
            True if Slack notification was sent successfully
        """
        try:
            # Choose emoji based on level
            emoji_map = {
                "INFO": ":information_source:",
                "WARNING": ":warning:",
                "ERROR": ":rotating_light:",
            }
            emoji = emoji_map.get(level, ":information_source:")

            # Format message for Slack
            payload = {
                "text": f"{emoji} *{subject}*\n{message}",
                "username": self.username,
            }

            if self.channel:
                payload["channel"] = self.channel

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                )
                response.raise_for_status()

            logger.info("Slack notification sent successfully")
            return True

        except Exception as e:
            logger.exception("Failed to send Slack notification: %s", e)
            return False


class NotificationManager:
    """Manages multiple notification sinks."""

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize the notification manager.

        Args:
            config: Notification configuration with keys for each sink type
        """
        self.sinks: list[NotificationSink] = []

        # Initialize email notifier
        email_config = config.get("email", {})
        if email_config.get("enabled", False):
            try:
                self.sinks.append(EmailNotifier(email_config))
                logger.info("Email notifier initialized")
            except Exception as e:
                logger.warning("Failed to initialize email notifier: %s", e)

        # Initialize webhook notifier
        webhook_config = config.get("webhook", {})
        if webhook_config.get("enabled", False):
            try:
                self.sinks.append(WebhookNotifier(webhook_config))
                logger.info("Webhook notifier initialized")
            except Exception as e:
                logger.warning("Failed to initialize webhook notifier: %s", e)

        # Initialize Slack notifier
        slack_config = config.get("slack", {})
        if slack_config.get("enabled", False):
            try:
                self.sinks.append(SlackNotifier(slack_config))
                logger.info("Slack notifier initialized")
            except Exception as e:
                logger.warning("Failed to initialize Slack notifier: %s", e)

        if not self.sinks:
            logger.warning("No notification sinks configured or initialized")

    async def notify(self, subject: str, message: str, level: str = "INFO") -> dict[str, bool]:
        """
        Send a notification to all configured sinks.

        Args:
            subject: Notification subject
            message: Notification message
            level: Notification level (INFO, WARNING, ERROR)

        Returns:
            Dictionary mapping sink names to success status
        """
        results = {}

        for i, sink in enumerate(self.sinks):
            sink_name = f"{sink.__class__.__name__}_{i}"
            try:
                success = await sink.send(subject, message, level)
                results[sink_name] = success
            except Exception as e:
                logger.exception("Error sending notification via %s: %s", sink_name, e)
                results[sink_name] = False

        return results

    async def notify_certificate_expiry(
        self,
        certificate_id: str,
        subject_name: str,
        days_remaining: int,
        expiry_date: str,
    ) -> dict[str, bool]:
        """
        Send a certificate expiry notification.

        Args:
            certificate_id: Certificate ID
            subject_name: Certificate subject
            days_remaining: Days until expiry
            expiry_date: Expiry date string

        Returns:
            Dictionary mapping sink names to success status
        """
        # Determine notification level based on days remaining
        if days_remaining <= 1:
            level = "ERROR"
        elif days_remaining <= 7:
            level = "WARNING"
        else:
            level = "INFO"

        subject = (
            f"Certificate Expiring in {days_remaining} day{'s' if days_remaining != 1 else ''}"
        )
        message = (
            f"Certificate ID: {certificate_id}\n"
            f"Subject: {subject_name}\n"
            f"Expires: {expiry_date}\n"
            f"Days remaining: {days_remaining}"
        )

        return await self.notify(subject, message, level)

    async def notify_certificate_renewal(
        self,
        old_certificate_id: str,
        new_certificate_id: str,
        subject_name: str,
    ) -> dict[str, bool]:
        """
        Send a certificate renewal notification.

        Args:
            old_certificate_id: ID of the old certificate
            new_certificate_id: ID of the new certificate
            subject_name: Certificate subject

        Returns:
            Dictionary mapping sink names to success status
        """
        subject = "Certificate Renewed Successfully"
        message = (
            f"Old Certificate ID: {old_certificate_id}\n"
            f"New Certificate ID: {new_certificate_id}\n"
            f"Subject: {subject_name}\n"
            f"Renewal completed successfully"
        )

        return await self.notify(subject, message, "INFO")

    async def notify_certificate_revocation(
        self,
        certificate_id: str,
        subject_name: str,
        revocation_date: str,
        reason: str,
    ) -> dict[str, bool]:
        """
        Send a certificate revocation notification.

        Args:
            certificate_id: Certificate ID
            subject_name: Certificate subject
            revocation_date: Revocation date string
            reason: Revocation reason

        Returns:
            Dictionary mapping sink names to success status
        """
        subject = "Certificate Revoked"
        message = (
            f"Certificate ID: {certificate_id}\n"
            f"Subject: {subject_name}\n"
            f"Revoked: {revocation_date}\n"
            f"Reason: {reason}"
        )

        return await self.notify(subject, message, "WARNING")


def create_notification_manager(config: dict[str, Any]) -> NotificationManager:
    """
    Create a notification manager from configuration.

    Args:
        config: Notification configuration

    Returns:
        Configured NotificationManager instance
    """
    return NotificationManager(config)


__all__ = [
    "NotificationSink",
    "EmailNotifier",
    "WebhookNotifier",
    "SlackNotifier",
    "NotificationManager",
    "create_notification_manager",
]
