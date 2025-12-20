"""
Notification utilities for sending alerts
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage

import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)


class Notifier:
    """
    Utility for sending notifications through various channels
    like email, webhooks, etc.
    """

    def __init__(self) -> None:
        """Initialize the notifier with configuration from settings"""
        self.config = settings.NOTIFICATIONS if hasattr(settings, "NOTIFICATIONS") else {}

    async def send_notification(
        self, subject: str, message: str, channel: str | None = None
    ) -> None:
        """
        Send a notification using the configured channels

        Args:
            subject: The notification subject
            message: The notification message
            channel: Optional specific channel to use (email, webhook)
        """
        if channel == "email" or channel is None:
            await self._send_email_notification(subject, message)

        if channel == "webhook" or channel is None:
            await self._send_webhook_notification(subject, message)

    async def _send_email_notification(self, subject: str, message: str) -> None:
        """
        Send an email notification

        Args:
            subject: Email subject
            message: Email body
        """
        email_config = self.config.get("email", {})

        if not email_config.get("enabled", False):
            logger.debug("Email notifications are disabled")
            return

        try:
            # Get email configuration
            smtp_server = email_config.get("smtp_server")
            smtp_port = email_config.get("smtp_port", 587)
            from_address = email_config.get("from_address")
            to_addresses = email_config.get("to_addresses", [])

            if not smtp_server or not from_address or not to_addresses:
                logger.warning("Incomplete email configuration")
                return

            # Create the email message
            msg = EmailMessage()
            msg.set_content(message)
            msg["Subject"] = subject
            msg["From"] = from_address
            msg["To"] = ", ".join(to_addresses)

            # Send the email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                if email_config.get("use_tls", True):
                    server.starttls()

                if email_config.get("username") and email_config.get("password"):
                    server.login(email_config["username"], email_config["password"])

                server.send_message(msg)

            logger.info(f"Email notification sent: {subject}")

        except Exception as e:
            logger.exception(f"Failed to send email notification: {e}")

    async def _send_webhook_notification(self, subject: str, message: str) -> None:
        """
        Send a webhook notification

        Args:
            subject: Notification subject
            message: Notification message
        """
        webhook_config = self.config.get("webhook", {})

        if not webhook_config.get("enabled", False):
            logger.debug("Webhook notifications are disabled")
            return

        try:
            webhook_url = webhook_config.get("url")
            if not webhook_url:
                logger.warning("No webhook URL configured")
                return

            # Prepare payload
            payload = {
                "subject": subject,
                "message": message,
                "type": "certificate_alert",
                "timestamp": str(datetime.now()),
            }

            # Add authentication if configured
            headers = {"Content-Type": "application/json"}
            if webhook_config.get("auth_token"):
                headers["Authorization"] = f"Bearer {webhook_config['auth_token']}"

            # Send the webhook request
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        logger.warning(
                            f"Webhook returned non-200 status: {response.status}, {response_text}"
                        )
                    else:
                        logger.info(f"Webhook notification sent: {subject}")

        except Exception as e:
            logger.exception(f"Failed to send webhook notification: {e}")

    async def send_expiry_notification(
        self, cert_id: str, subject: str, expiry_date: str, days_left: int
    ) -> None:
        """
        Send a certificate expiry notification

        Args:
            cert_id: Certificate ID
            subject: Certificate subject
            expiry_date: Certificate expiry date
            days_left: Days left until expiry
        """
        notification_subject = f"Certificate Expiring Soon: {subject}"
        notification_message = (
            f"Certificate with ID {cert_id} will expire in {days_left} days "
            f"(on {expiry_date}). Please plan for certificate renewal."
        )

        await self.send_notification(notification_subject, notification_message)

    async def send_revocation_notification(
        self, cert_id: str, subject: str, reason: str | None = None
    ) -> None:
        """
        Send a certificate revocation notification

        Args:
            cert_id: Certificate ID
            subject: Certificate subject
            reason: Optional revocation reason
        """
        notification_subject = f"Certificate Revoked: {subject}"
        notification_message = f"Certificate with ID {cert_id} has been revoked."

        if reason:
            notification_message += f" Reason: {reason}"

        await self.send_notification(notification_subject, notification_message)
