"""
Email Adapter

Email notification adapter supporting SendGrid, AWS SES, and MailHog (dev).
"""
from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Optional

import httpx

from ..types import ChannelType, DeliveryResult, NotificationPayload

logger = logging.getLogger(__name__)


class EmailProvider(str, Enum):
    """Supported email providers."""
    SENDGRID = "sendgrid"
    SES = "ses"
    MAILHOG = "mailhog"  # Development/testing provider


@dataclass
class EmailConfig:
    """Email adapter configuration."""
    provider: EmailProvider
    from_email: str
    from_name: str = "Marty"
    
    # SendGrid settings
    sendgrid_api_key: Optional[str] = None
    
    # SES settings
    ses_region: str = "us-east-1"
    ses_access_key: Optional[str] = None
    ses_secret_key: Optional[str] = None
    
    # MailHog settings (development)
    mailhog_host: str = "localhost"
    mailhog_port: int = 1025
    
    @classmethod
    def from_environment(cls) -> "EmailConfig":
        """
        Create config from environment variables.
        
        Auto-selects MailHog in development mode.
        """
        env = os.getenv("ENVIRONMENT", "development")
        
        # Use MailHog for development/testing
        if env in ("development", "testing", "test"):
            return cls(
                provider=EmailProvider.MAILHOG,
                from_email=os.getenv("EMAIL_FROM", "noreply@marty.demo"),
                from_name=os.getenv("EMAIL_FROM_NAME", "Marty Trust Services"),
                mailhog_host=os.getenv("MAILHOG_HOST", "mailhog"),
                mailhog_port=int(os.getenv("MAILHOG_PORT", "1025")),
            )
        
        # Production: prefer SendGrid, fallback to SES
        if os.getenv("SENDGRID_API_KEY"):
            return cls(
                provider=EmailProvider.SENDGRID,
                from_email=os.getenv("EMAIL_FROM", "noreply@marty.io"),
                from_name=os.getenv("EMAIL_FROM_NAME", "Marty"),
                sendgrid_api_key=os.getenv("SENDGRID_API_KEY"),
            )
        
        return cls(
            provider=EmailProvider.SES,
            from_email=os.getenv("EMAIL_FROM", "noreply@marty.io"),
            from_name=os.getenv("EMAIL_FROM_NAME", "Marty"),
            ses_region=os.getenv("AWS_REGION", "us-east-1"),
            ses_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
            ses_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )


class EmailAdapter:
    """
    Email notification adapter.
    
    Features:
    - SendGrid and AWS SES support
    - HTML and plain text templates
    - Delivery tracking
    """
    
    SENDGRID_ENDPOINT = "https://api.sendgrid.com/v3/mail/send"
    
    def __init__(self, config: EmailConfig):
        """
        Initialize the email adapter.
        
        Args:
            config: Email configuration
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def send(self, payload: NotificationPayload) -> DeliveryResult:
        """
        Send an email notification.
        
        Args:
            payload: The notification payload
            
        Returns:
            DeliveryResult with success status
        """
        if not payload.target or not payload.target.email_addresses:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="NO_RECIPIENTS",
                error_message="No email addresses provided",
            )
        
        if self.config.provider == EmailProvider.SENDGRID:
            return await self._send_sendgrid(payload)
        elif self.config.provider == EmailProvider.SES:
            return await self._send_ses(payload)
        elif self.config.provider == EmailProvider.MAILHOG:
            return await self._send_mailhog(payload)
        else:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="INVALID_PROVIDER",
                error_message=f"Unknown provider: {self.config.provider}",
            )
    
    async def _send_sendgrid(self, payload: NotificationPayload) -> DeliveryResult:
        """Send email via SendGrid."""
        if not self.config.sendgrid_api_key:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="NO_API_KEY",
                error_message="SendGrid API key not configured",
            )
        
        client = await self._get_client()
        
        # Build email content
        html_content = self._build_html_content(payload)
        
        email_data = {
            "personalizations": [
                {
                    "to": [
                        {"email": addr}
                        for addr in payload.target.email_addresses
                    ],
                    "subject": payload.title or "Notification from Marty",
                }
            ],
            "from": {
                "email": self.config.from_email,
                "name": self.config.from_name,
            },
            "content": [
                {
                    "type": "text/plain",
                    "value": payload.body,
                },
                {
                    "type": "text/html",
                    "value": html_content,
                },
            ],
            "custom_args": {
                "notification_id": str(payload.id),
                "event_type": payload.event_type,
            },
        }
        
        try:
            response = await client.post(
                self.SENDGRID_ENDPOINT,
                json=email_data,
                headers={
                    "Authorization": f"Bearer {self.config.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
            )
            
            if response.status_code in (200, 202):
                return DeliveryResult(
                    notification_id=payload.id,
                    channel=ChannelType.EMAIL,
                    success=True,
                    delivered_at=datetime.now(timezone.utc),
                    metadata={
                        "message_id": response.headers.get("X-Message-Id"),
                        "recipients": len(payload.target.email_addresses),
                    },
                )
            
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code=str(response.status_code),
                error_message=response.text[:200],
            )
            
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="EXCEPTION",
                error_message=str(e),
                should_retry=True,
            )
    
    async def _send_ses(self, payload: NotificationPayload) -> DeliveryResult:
        """Send email via AWS SES."""
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="MISSING_DEPENDENCY",
                error_message="boto3 not installed",
            )
        
        try:
            ses = boto3.client(
                'ses',
                region_name=self.config.ses_region,
                aws_access_key_id=self.config.ses_access_key,
                aws_secret_access_key=self.config.ses_secret_key,
            )
            
            response = ses.send_email(
                Source=f"{self.config.from_name} <{self.config.from_email}>",
                Destination={
                    'ToAddresses': payload.target.email_addresses,
                },
                Message={
                    'Subject': {
                        'Data': payload.title or "Notification from Marty",
                        'Charset': 'UTF-8',
                    },
                    'Body': {
                        'Text': {
                            'Data': payload.body,
                            'Charset': 'UTF-8',
                        },
                        'Html': {
                            'Data': self._build_html_content(payload),
                            'Charset': 'UTF-8',
                        },
                    },
                },
            )
            
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=True,
                delivered_at=datetime.now(timezone.utc),
                metadata={
                    "message_id": response['MessageId'],
                    "recipients": len(payload.target.email_addresses),
                },
            )
            
        except ClientError as e:
            logger.error(f"SES error: {e}")
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code=e.response['Error']['Code'],
                error_message=e.response['Error']['Message'],
                should_retry='Throttl' in str(e),
            )
        except Exception as e:
            logger.error(f"SES error: {e}")
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="EXCEPTION",
                error_message=str(e),
                should_retry=True,
            )

    async def _send_mailhog(self, payload: NotificationPayload) -> DeliveryResult:
        """
        Send email via MailHog (development/testing SMTP server).
        
        MailHog captures all emails for viewing at http://localhost:8025
        No authentication required - perfect for development.
        """
        import asyncio
        
        try:
            # Build the email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = payload.title or "Notification from Marty"
            msg['From'] = f"{self.config.from_name} <{self.config.from_email}>"
            msg['To'] = ", ".join(payload.target.email_addresses)
            msg['X-Notification-ID'] = str(payload.id)
            msg['X-Event-Type'] = payload.event_type
            
            # Plain text part
            text_part = MIMEText(payload.body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # HTML part
            html_content = self._build_html_content(payload)
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Send via SMTP (run in thread pool to avoid blocking)
            def send_smtp():
                with smtplib.SMTP(
                    self.config.mailhog_host, 
                    self.config.mailhog_port,
                    timeout=10
                ) as server:
                    server.sendmail(
                        self.config.from_email,
                        payload.target.email_addresses,
                        msg.as_string()
                    )
            
            await asyncio.get_event_loop().run_in_executor(None, send_smtp)
            
            logger.info(
                f"MailHog: Sent email to {payload.target.email_addresses} "
                f"(view at http://{self.config.mailhog_host}:8025)"
            )
            
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=True,
                delivered_at=datetime.now(timezone.utc),
                metadata={
                    "provider": "mailhog",
                    "recipients": len(payload.target.email_addresses),
                    "mailhog_ui": f"http://{self.config.mailhog_host}:8025",
                },
            )
            
        except smtplib.SMTPException as e:
            logger.error(f"MailHog SMTP error: {e}")
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="SMTP_ERROR",
                error_message=str(e),
                should_retry=True,
            )
        except ConnectionRefusedError:
            logger.error(
                f"MailHog connection refused at "
                f"{self.config.mailhog_host}:{self.config.mailhog_port}"
            )
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="CONNECTION_REFUSED",
                error_message="MailHog not running. Start with docker-compose.",
                should_retry=True,
            )
        except Exception as e:
            logger.error(f"MailHog error: {e}")
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.EMAIL,
                success=False,
                error_code="EXCEPTION",
                error_message=str(e),
                should_retry=True,
            )
    
    def _build_html_content(self, payload: NotificationPayload) -> str:
        """Build HTML email content."""
        # Simple HTML template
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{payload.title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: #2563eb;
            color: white;
            padding: 20px;
            border-radius: 8px 8px 0 0;
        }}
        .content {{
            background: #f9fafb;
            padding: 20px;
            border: 1px solid #e5e7eb;
            border-top: none;
            border-radius: 0 0 8px 8px;
        }}
        .footer {{
            text-align: center;
            color: #6b7280;
            font-size: 12px;
            margin-top: 20px;
        }}
        .event-type {{
            display: inline-block;
            background: #dbeafe;
            color: #1e40af;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="margin: 0;">{payload.title}</h1>
    </div>
    <div class="content">
        <span class="event-type">{payload.event_type}</span>
        <p>{payload.body}</p>
    </div>
    <div class="footer">
        <p>This is an automated notification from Marty.</p>
        <p>© {datetime.now().year} Marty</p>
    </div>
</body>
</html>
"""
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
