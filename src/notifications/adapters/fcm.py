"""
FCM Adapter

Firebase Cloud Messaging adapter for push notifications.
Supports batching, exponential backoff, and token validation.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..types import ChannelType, DeliveryResult, NotificationPayload, NotificationPriority

logger = logging.getLogger(__name__)


@dataclass
class FCMConfig:
    """FCM configuration."""
    project_id: str
    service_account_path: Optional[str] = None
    service_account_json: Optional[dict] = None
    
    # Batching
    max_batch_size: int = 500
    
    # Retry settings
    max_retries: int = 3
    initial_backoff: float = 1.0
    max_backoff: float = 30.0


class FCMAdapter:
    """
    Firebase Cloud Messaging adapter.
    
    Features:
    - Batch sending (up to 500 messages)
    - Exponential backoff retry
    - Token validation and cleanup
    - Priority mapping
    """
    
    FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    
    def __init__(
        self,
        config: FCMConfig,
        token_invalidator: Optional[Any] = None,  # Callback to mark tokens invalid
    ):
        """
        Initialize the FCM adapter.
        
        Args:
            config: FCM configuration
            token_invalidator: Optional callback to handle invalid tokens
        """
        self.config = config
        self._token_invalidator = token_invalidator
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def _get_access_token(self) -> str:
        """Get OAuth2 access token for FCM API."""
        # Check if current token is still valid
        if (
            self._access_token 
            and self._token_expires_at 
            and datetime.now(timezone.utc) < self._token_expires_at
        ):
            return self._access_token
        
        # Get new token using google-auth
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            
            scopes = ["https://www.googleapis.com/auth/firebase.messaging"]
            
            if self.config.service_account_path:
                credentials = service_account.Credentials.from_service_account_file(
                    self.config.service_account_path,
                    scopes=scopes,
                )
            elif self.config.service_account_json:
                credentials = service_account.Credentials.from_service_account_info(
                    self.config.service_account_json,
                    scopes=scopes,
                )
            else:
                raise ValueError("No service account credentials provided")
            
            credentials.refresh(Request())
            self._access_token = credentials.token
            self._token_expires_at = credentials.expiry
            
            return self._access_token
            
        except ImportError:
            logger.error("google-auth not installed. Install with: pip install google-auth")
            raise
    
    async def send(self, payload: NotificationPayload) -> DeliveryResult:
        """
        Send a notification via FCM.
        
        Args:
            payload: The notification payload
            
        Returns:
            DeliveryResult with success status
        """
        if not payload.target or not payload.target.device_tokens:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.FCM,
                success=False,
                error_code="NO_TOKENS",
                error_message="No device tokens provided",
            )
        
        tokens = payload.target.device_tokens
        
        # Use batch sending for multiple tokens
        if len(tokens) > 1:
            return await self._send_batch(payload, tokens)
        
        return await self._send_single(payload, tokens[0])
    
    async def _send_single(
        self,
        payload: NotificationPayload,
        token: str,
    ) -> DeliveryResult:
        """Send to a single device."""
        message = self._build_message(payload, token)
        
        for attempt in range(self.config.max_retries):
            try:
                client = await self._get_client()
                access_token = await self._get_access_token()
                
                url = self.FCM_ENDPOINT.format(project_id=self.config.project_id)
                
                response = await client.post(
                    url,
                    json={"message": message},
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )
                
                if response.status_code == 200:
                    return DeliveryResult(
                        notification_id=payload.id,
                        channel=ChannelType.FCM,
                        success=True,
                        delivered_at=datetime.now(timezone.utc),
                        metadata={"message_id": response.json().get("name")},
                    )
                
                # Handle errors
                error_data = response.json().get("error", {})
                error_code = error_data.get("code", str(response.status_code))
                error_message = error_data.get("message", response.text)
                
                # Check for invalid token
                if response.status_code == 404 or "UNREGISTERED" in str(error_data):
                    await self._handle_invalid_token(token)
                    return DeliveryResult(
                        notification_id=payload.id,
                        channel=ChannelType.FCM,
                        success=False,
                        error_code="INVALID_TOKEN",
                        error_message="Token is no longer valid",
                    )
                
                # Retry on transient errors
                if response.status_code in (429, 500, 503):
                    backoff = min(
                        self.config.initial_backoff * (2 ** attempt),
                        self.config.max_backoff,
                    )
                    logger.warning(f"FCM retry {attempt + 1}, backing off {backoff}s")
                    await asyncio.sleep(backoff)
                    continue
                
                return DeliveryResult(
                    notification_id=payload.id,
                    channel=ChannelType.FCM,
                    success=False,
                    error_code=error_code,
                    error_message=error_message,
                    attempt_number=attempt + 1,
                )
                
            except Exception as e:
                logger.error(f"FCM send error: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.initial_backoff * (2 ** attempt))
                    continue
                    
                return DeliveryResult(
                    notification_id=payload.id,
                    channel=ChannelType.FCM,
                    success=False,
                    error_code="EXCEPTION",
                    error_message=str(e),
                    attempt_number=attempt + 1,
                    should_retry=True,
                )
        
        return DeliveryResult(
            notification_id=payload.id,
            channel=ChannelType.FCM,
            success=False,
            error_code="MAX_RETRIES",
            error_message="Max retries exceeded",
        )
    
    async def _send_batch(
        self,
        payload: NotificationPayload,
        tokens: list[str],
    ) -> DeliveryResult:
        """Send to multiple devices in batches."""
        total_success = 0
        total_failure = 0
        failed_tokens = []
        
        # Process in batches
        for i in range(0, len(tokens), self.config.max_batch_size):
            batch = tokens[i:i + self.config.max_batch_size]
            
            # Send each message in the batch
            tasks = [
                self._send_single(payload, token)
                for token in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, DeliveryResult) and result.success:
                    total_success += 1
                else:
                    total_failure += 1
        
        success = total_failure == 0
        
        return DeliveryResult(
            notification_id=payload.id,
            channel=ChannelType.FCM,
            success=success,
            delivered_at=datetime.now(timezone.utc) if success else None,
            metadata={
                "total_tokens": len(tokens),
                "success_count": total_success,
                "failure_count": total_failure,
            },
        )
    
    def _serialize_data_value(self, value: Any) -> str:
        """Serialize a value for FCM data payload. All values must be strings."""
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        # For complex types (list, dict), use JSON serialization
        return json.dumps(value)
    
    def _build_message(self, payload: NotificationPayload, token: str) -> dict:
        """Build FCM message payload."""
        # Map priority
        priority = "normal"
        if payload.priority in (NotificationPriority.HIGH, NotificationPriority.CRITICAL):
            priority = "high"
        
        message = {
            "token": token,
            "notification": {
                "title": payload.title,
                "body": payload.body,
            },
            "data": {
                "notification_id": str(payload.id),
                "event_type": payload.event_type,
                **{k: self._serialize_data_value(v) for k, v in payload.data.items()},
            },
            "android": {
                "priority": priority,
                "ttl": f"{payload.ttl_seconds}s",
            },
            "apns": {
                "payload": {
                    "aps": {
                        "alert": {
                            "title": payload.title,
                            "body": payload.body,
                        },
                        "sound": "default" if priority == "high" else None,
                    },
                },
                "headers": {
                    "apns-priority": "10" if priority == "high" else "5",
                    "apns-expiration": str(int(payload.ttl_seconds)),
                },
            },
        }
        
        # Add collapse key if provided
        if payload.collapse_key:
            message["android"]["collapse_key"] = payload.collapse_key
            message["apns"]["headers"]["apns-collapse-id"] = payload.collapse_key
        
        return message
    
    async def _handle_invalid_token(self, token: str) -> None:
        """Handle an invalid FCM token."""
        logger.info(f"Marking token as invalid: {token[:20]}...")
        
        if self._token_invalidator:
            try:
                if asyncio.iscoroutinefunction(self._token_invalidator):
                    await self._token_invalidator(token)
                else:
                    self._token_invalidator(token)
            except Exception as e:
                logger.error(f"Error in token invalidator: {e}")
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
