"""
Webhook Adapter

HTTP webhook adapter for delivering notifications to external endpoints.
Supports HMAC signing, circuit breaker, and configurable retries.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..types import ChannelType, DeliveryResult, NotificationPayload

logger = logging.getLogger(__name__)


@dataclass
class WebhookEndpointConfig:
    """Configuration for a single webhook endpoint."""
    url: str
    secret: str
    event_types: list[str] = field(default_factory=list)  # Empty = all events
    enabled: bool = True


@dataclass
class WebhookConfig:
    """Webhook adapter configuration."""
    # Timeout settings
    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    
    # Retry settings
    max_retries: int = 3
    initial_backoff: float = 1.0
    max_backoff: float = 60.0
    
    # Circuit breaker settings
    failure_threshold: int = 5
    recovery_timeout: int = 300  # 5 minutes


@dataclass
class CircuitBreakerState:
    """Circuit breaker state for an endpoint."""
    failures: int = 0
    last_failure: Optional[datetime] = None
    is_open: bool = False
    
    def record_failure(self, threshold: int) -> None:
        """Record a failure and potentially open the circuit."""
        self.failures += 1
        self.last_failure = datetime.now(timezone.utc)
        if self.failures >= threshold:
            self.is_open = True
    
    def record_success(self) -> None:
        """Record a success and reset the circuit."""
        self.failures = 0
        self.is_open = False
    
    def should_allow(self, recovery_timeout: int) -> bool:
        """Check if a request should be allowed."""
        if not self.is_open:
            return True
        
        # Check if recovery timeout has elapsed
        if self.last_failure:
            elapsed = (datetime.now(timezone.utc) - self.last_failure).total_seconds()
            if elapsed >= recovery_timeout:
                return True  # Allow one attempt
        
        return False


class WebhookAdapter:
    """
    Webhook delivery adapter.
    
    Features:
    - HMAC-SHA256 signature for payload verification
    - Exponential backoff retry
    - Circuit breaker pattern
    - Event type filtering
    """
    
    def __init__(self, config: WebhookConfig):
        """
        Initialize the webhook adapter.
        
        Args:
            config: Webhook configuration
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._circuit_breakers: dict[str, CircuitBreakerState] = {}
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=self.config.connect_timeout,
                    read=self.config.read_timeout,
                    write=self.config.read_timeout,
                    pool=self.config.connect_timeout,
                ),
            )
        return self._client
    
    def _get_circuit_breaker(self, url: str) -> CircuitBreakerState:
        """Get or create circuit breaker for an endpoint."""
        if url not in self._circuit_breakers:
            self._circuit_breakers[url] = CircuitBreakerState()
        return self._circuit_breakers[url]
    
    async def send(
        self,
        payload: NotificationPayload,
        endpoints: Optional[list[WebhookEndpointConfig]] = None,
    ) -> DeliveryResult:
        """
        Send a notification to webhook endpoints.
        
        Args:
            payload: The notification payload
            endpoints: Optional list of endpoints (otherwise uses target)
            
        Returns:
            DeliveryResult with success status
        """
        # Get endpoints from payload target if not provided
        if not endpoints and payload.target:
            endpoints = [
                WebhookEndpointConfig(url=url, secret="")
                for url in payload.target.webhook_endpoints
            ]
        
        if not endpoints:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.WEBHOOK,
                success=False,
                error_code="NO_ENDPOINTS",
                error_message="No webhook endpoints provided",
            )
        
        # Filter by event type
        filtered_endpoints = [
            ep for ep in endpoints
            if ep.enabled and (
                not ep.event_types or 
                payload.event_type in ep.event_types
            )
        ]
        
        if not filtered_endpoints:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.WEBHOOK,
                success=True,
                metadata={"skipped": "No matching endpoints"},
            )
        
        # Send to all endpoints in parallel
        tasks = [
            self._deliver_to_endpoint(payload, ep)
            for ep in filtered_endpoints
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        success_count = sum(
            1 for r in results
            if isinstance(r, DeliveryResult) and r.success
        )
        total = len(filtered_endpoints)
        
        return DeliveryResult(
            notification_id=payload.id,
            channel=ChannelType.WEBHOOK,
            success=success_count > 0,
            delivered_at=datetime.now(timezone.utc) if success_count > 0 else None,
            metadata={
                "total_endpoints": total,
                "success_count": success_count,
                "failure_count": total - success_count,
            },
        )
    
    async def _deliver_to_endpoint(
        self,
        payload: NotificationPayload,
        endpoint: WebhookEndpointConfig,
    ) -> DeliveryResult:
        """Deliver to a single endpoint."""
        # Check circuit breaker
        circuit = self._get_circuit_breaker(endpoint.url)
        if not circuit.should_allow(self.config.recovery_timeout):
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.WEBHOOK,
                success=False,
                error_code="CIRCUIT_OPEN",
                error_message="Circuit breaker is open",
            )
        
        # Build request body
        body = json.dumps(payload.to_dict()).encode()
        
        # Generate signature
        signature = self._sign_payload(body, endpoint.secret)
        
        # Headers
        headers = {
            "Content-Type": "application/json",
            "X-Marty-Event": payload.event_type,
            "X-Marty-Signature": signature,
            "X-Marty-Delivery-Id": str(payload.id),
            "X-Marty-Timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        if payload.correlation_id:
            headers["X-Marty-Correlation-Id"] = payload.correlation_id
        
        # Attempt delivery with retries
        for attempt in range(self.config.max_retries):
            try:
                client = await self._get_client()
                
                response = await client.post(
                    endpoint.url,
                    content=body,
                    headers=headers,
                )
                
                if response.status_code < 400:
                    circuit.record_success()
                    return DeliveryResult(
                        notification_id=payload.id,
                        channel=ChannelType.WEBHOOK,
                        success=True,
                        delivered_at=datetime.now(timezone.utc),
                        attempt_number=attempt + 1,
                        metadata={
                            "status_code": response.status_code,
                            "endpoint": endpoint.url,
                        },
                    )
                
                # Server error - retry
                if response.status_code >= 500:
                    circuit.record_failure(self.config.failure_threshold)
                    backoff = min(
                        self.config.initial_backoff * (2 ** attempt),
                        self.config.max_backoff,
                    )
                    logger.warning(
                        f"Webhook {endpoint.url} returned {response.status_code}, "
                        f"retry {attempt + 1}, backing off {backoff}s"
                    )
                    await asyncio.sleep(backoff)
                    continue
                
                # Client error - don't retry
                return DeliveryResult(
                    notification_id=payload.id,
                    channel=ChannelType.WEBHOOK,
                    success=False,
                    error_code=str(response.status_code),
                    error_message=response.text[:200],
                    attempt_number=attempt + 1,
                )
                
            except httpx.TimeoutException:
                circuit.record_failure(self.config.failure_threshold)
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.initial_backoff * (2 ** attempt))
                    continue
                    
                return DeliveryResult(
                    notification_id=payload.id,
                    channel=ChannelType.WEBHOOK,
                    success=False,
                    error_code="TIMEOUT",
                    error_message=f"Request to {endpoint.url} timed out",
                    should_retry=True,
                )
                
            except Exception as e:
                circuit.record_failure(self.config.failure_threshold)
                logger.error(f"Webhook error for {endpoint.url}: {e}")
                
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.initial_backoff * (2 ** attempt))
                    continue
                
                return DeliveryResult(
                    notification_id=payload.id,
                    channel=ChannelType.WEBHOOK,
                    success=False,
                    error_code="EXCEPTION",
                    error_message=str(e),
                    should_retry=True,
                )
        
        return DeliveryResult(
            notification_id=payload.id,
            channel=ChannelType.WEBHOOK,
            success=False,
            error_code="MAX_RETRIES",
            error_message="Max retries exceeded",
        )
    
    def _sign_payload(self, body: bytes, secret: str) -> str:
        """Generate HMAC-SHA256 signature for payload."""
        if not secret:
            return ""
        
        signature = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        
        return f"sha256={signature}"
    
    @staticmethod
    def verify_signature(body: bytes, secret: str, signature: str) -> bool:
        """
        Verify webhook signature.
        
        Args:
            body: Raw request body
            secret: Webhook secret
            signature: X-Marty-Signature header value
            
        Returns:
            True if signature is valid
        """
        if not signature.startswith("sha256="):
            return False
        
        expected = f"sha256={hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}"
        return hmac.compare_digest(expected, signature)
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
