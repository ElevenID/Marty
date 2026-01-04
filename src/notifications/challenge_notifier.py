"""
Marty Challenge Notifier

Marty-specific wrapper around MMF's push notification framework.
Handles Marty challenge payload formatting, signing, and delivery.

This module bridges the generic MMF push infrastructure with
Marty's specific challenge format (marty/v1).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

# Import from MMF push framework
# Note: mmf is a local package in the workspace
try:
    from mmf.core.push import (
        IPushManager,
        PushChannel,
        PushMessage,
        PushResult,
        PushTarget,
        PushPriority,
    )
except ImportError:
    # Fallback for when running outside the monorepo
    from marty_microservices_framework.mmf.core.push import (
        IPushManager,
        PushChannel,
        PushMessage,
        PushResult,
        PushTarget,
        PushPriority,
    )

from .signing import ChallengeSigner
from .types import ChallengeOption, MartyChallengePayload

logger = logging.getLogger(__name__)


@dataclass
class ChallengeDeliveryResult:
    """
    Result of a Marty challenge delivery.
    
    Wraps PushResult with Marty-specific context.
    """
    challenge_id: str
    device_id: str
    
    # Delivery status
    success: bool
    channel: PushChannel
    
    # Timing
    sent_at: datetime
    delivered_at: Optional[datetime] = None
    
    # Error info
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Raw results from all channels
    channel_results: list[PushResult] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/API response."""
        return {
            "challenge_id": self.challenge_id,
            "device_id": self.device_id,
            "success": self.success,
            "channel": self.channel.value,
            "sent_at": self.sent_at.isoformat(),
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class MartyChallengeNotifier:
    """
    Marty challenge notification service.
    
    Handles the Marty-specific aspects of challenge delivery:
    - Building MartyChallengePayload
    - Signing challenges with RSA
    - Formatting for FCM data payload
    - Routing to appropriate devices
    
    Usage:
        # Create with push manager and signer
        notifier = MartyChallengeNotifier(
            push_manager=push_manager,
            signer=challenge_signer,
        )
        
        # Send a challenge
        result = await notifier.send_challenge(
            challenge_id="chal-123",
            device_id="device-456",
            device_token="fcm-token-789",
            title="Authentication Request",
            question="Approve login from Chrome on MacOS?",
            options=[
                ChallengeOption(id="approve", label="Approve"),
                ChallengeOption(id="deny", label="Deny"),
            ],
        )
    """
    
    def __init__(
        self,
        push_manager: IPushManager,
        signer: ChallengeSigner | None = None,
        default_ttl: int = 120,
    ):
        """
        Initialize the challenge notifier.
        
        Args:
            push_manager: MMF push manager for delivery
            signer: Optional challenge signer for RSA signing
            default_ttl: Default TTL in seconds for challenges
        """
        self._push_manager = push_manager
        self._signer = signer
        self._default_ttl = default_ttl
    
    @property
    def signer(self) -> ChallengeSigner | None:
        """Get the challenge signer."""
        return self._signer
    
    @property
    def signing_enabled(self) -> bool:
        """Check if challenge signing is enabled."""
        return self._signer is not None
    
    def get_public_key_pem(self) -> str | None:
        """Get the server's public key in PEM format for client registration."""
        if self._signer:
            return self._signer.get_public_key_pem()
        return None
    
    def get_public_key_der_base64(self) -> str | None:
        """Get the server's public key in base64-encoded DER format."""
        if self._signer:
            return self._signer.get_public_key_der_base64()
        return None
    
    async def send_challenge(
        self,
        challenge_id: str,
        device_id: str,
        device_token: str,
        title: str,
        question: str,
        options: list[ChallengeOption] | None = None,
        nonce: str | None = None,
        ttl_seconds: int | None = None,
        credential_id: str | None = None,
        relying_party_id: str | None = None,
        require_signature: bool = True,
        additional_data: dict[str, Any] | None = None,
        channels: list[PushChannel] | None = None,
    ) -> ChallengeDeliveryResult:
        """
        Send a Marty challenge to a device.
        
        Args:
            challenge_id: Unique challenge identifier
            device_id: Target device identifier
            device_token: FCM/push token for the device
            title: Challenge title (shown in notification)
            question: Challenge question/prompt
            options: List of response options (buttons)
            nonce: Random nonce for replay protection (auto-generated if not provided)
            ttl_seconds: Challenge TTL in seconds
            credential_id: Optional related credential ID
            relying_party_id: Optional relying party identifier
            require_signature: Whether response must be signed
            additional_data: Additional data to include in payload
            channels: Channels to use (defaults to FCM)
            
        Returns:
            ChallengeDeliveryResult with delivery status
        """
        import secrets
        
        now = datetime.now(timezone.utc)
        ttl = ttl_seconds or self._default_ttl
        nonce = nonce or secrets.token_hex(16)
        options = options or []
        channels = channels or [PushChannel.FCM]
        
        # Build challenge payload
        challenge = MartyChallengePayload(
            challenge_id=challenge_id,
            device_id=device_id,
            title=title,
            question=question,
            nonce=nonce,
            options=options,
            ttl_seconds=ttl,
            created_at=now,
            credential_id=credential_id,
            relying_party_id=relying_party_id,
            require_signature=require_signature,
            data=additional_data or {},
        )
        
        # Sign the challenge if signer is configured
        if self._signer and require_signature:
            challenge.signature = self._signer.sign_challenge(challenge)
            logger.debug(f"Signed challenge {challenge_id}")
        
        # Convert to FCM data payload
        fcm_data = challenge.to_fcm_data()
        
        # Build push message
        message = PushMessage(
            target=PushTarget(
                device_tokens=[device_token],
            ),
            title=title,
            body=question,
            data=fcm_data,
            priority=PushPriority.HIGH,
            ttl_seconds=ttl,
            collapse_key=f"marty_challenge_{challenge_id}",
            mutable_content=True,  # Allow notification service extension
            content_available=True,  # Enable background processing
            correlation_id=challenge_id,
        )
        
        # Send via push manager
        try:
            results = await self._push_manager.send(message, channels=channels)
            
            # Aggregate results
            success = any(r.success for r in results)
            first_success = next((r for r in results if r.success), None)
            first_failure = next((r for r in results if not r.success), None)
            
            if success:
                logger.info(f"Challenge {challenge_id} delivered to device {device_id}")
                return ChallengeDeliveryResult(
                    challenge_id=challenge_id,
                    device_id=device_id,
                    success=True,
                    channel=first_success.channel if first_success else channels[0],
                    sent_at=now,
                    delivered_at=first_success.delivered_at if first_success else None,
                    channel_results=results,
                )
            else:
                error = first_failure
                logger.warning(
                    f"Challenge {challenge_id} delivery failed: "
                    f"{error.error_code if error else 'unknown'}"
                )
                return ChallengeDeliveryResult(
                    challenge_id=challenge_id,
                    device_id=device_id,
                    success=False,
                    channel=channels[0],
                    sent_at=now,
                    error_code=error.error_code if error else "DELIVERY_FAILED",
                    error_message=error.error_message if error else "All channels failed",
                    channel_results=results,
                )
                
        except Exception as e:
            logger.error(f"Challenge delivery error: {e}")
            return ChallengeDeliveryResult(
                challenge_id=challenge_id,
                device_id=device_id,
                success=False,
                channel=channels[0],
                sent_at=now,
                error_code="EXCEPTION",
                error_message=str(e),
            )
    
    async def send_challenge_to_user(
        self,
        challenge_id: str,
        user_id: str,
        device_tokens: list[str],
        device_ids: list[str],
        title: str,
        question: str,
        options: list[ChallengeOption] | None = None,
        ttl_seconds: int | None = None,
        require_signature: bool = True,
    ) -> list[ChallengeDeliveryResult]:
        """
        Send a challenge to all of a user's devices.
        
        Args:
            challenge_id: Unique challenge identifier
            user_id: Target user identifier
            device_tokens: List of FCM tokens for user's devices
            device_ids: Corresponding device IDs
            title: Challenge title
            question: Challenge question
            options: Response options
            ttl_seconds: Challenge TTL
            require_signature: Whether response must be signed
            
        Returns:
            List of ChallengeDeliveryResult for each device
        """
        if len(device_tokens) != len(device_ids):
            raise ValueError("device_tokens and device_ids must have same length")
        
        results = []
        for token, device_id in zip(device_tokens, device_ids):
            result = await self.send_challenge(
                challenge_id=challenge_id,
                device_id=device_id,
                device_token=token,
                title=title,
                question=question,
                options=options,
                ttl_seconds=ttl_seconds,
                require_signature=require_signature,
            )
            results.append(result)
        
        return results


class MockMartyChallengeNotifier:
    """
    Mock challenge notifier for testing.
    
    Captures sent challenges for test verification.
    """
    
    def __init__(self):
        """Initialize the mock notifier."""
        self._challenges: list[dict[str, Any]] = []
        self._should_fail = False
        self._failure_error = None
    
    @property
    def challenges(self) -> list[dict[str, Any]]:
        """Get all captured challenges."""
        return self._challenges
    
    @property
    def last_challenge(self) -> dict[str, Any] | None:
        """Get the most recently sent challenge."""
        return self._challenges[-1] if self._challenges else None
    
    def set_failure_mode(self, fail: bool, error: str | None = None) -> None:
        """Configure failure mode for testing error handling."""
        self._should_fail = fail
        self._failure_error = error
    
    def clear(self) -> None:
        """Clear captured challenges."""
        self._challenges.clear()
    
    async def send_challenge(
        self,
        challenge_id: str,
        device_id: str,
        device_token: str,
        title: str,
        question: str,
        options: list[ChallengeOption] | None = None,
        **kwargs,
    ) -> ChallengeDeliveryResult:
        """Capture a challenge and return mock result."""
        now = datetime.now(timezone.utc)
        
        self._challenges.append({
            "challenge_id": challenge_id,
            "device_id": device_id,
            "device_token": device_token,
            "title": title,
            "question": question,
            "options": [o.to_dict() for o in (options or [])],
            "kwargs": kwargs,
            "captured_at": now,
        })
        
        if self._should_fail:
            return ChallengeDeliveryResult(
                challenge_id=challenge_id,
                device_id=device_id,
                success=False,
                channel=PushChannel.FCM,
                sent_at=now,
                error_code="MOCK_FAILURE",
                error_message=self._failure_error or "Mock failure",
            )
        
        return ChallengeDeliveryResult(
            challenge_id=challenge_id,
            device_id=device_id,
            success=True,
            channel=PushChannel.FCM,
            sent_at=now,
            delivered_at=now,
        )
    
    async def send_challenge_to_user(
        self,
        challenge_id: str,
        user_id: str,
        device_tokens: list[str],
        device_ids: list[str],
        title: str,
        question: str,
        **kwargs,
    ) -> list[ChallengeDeliveryResult]:
        """Send to multiple devices."""
        results = []
        for token, device_id in zip(device_tokens, device_ids):
            result = await self.send_challenge(
                challenge_id=challenge_id,
                device_id=device_id,
                device_token=token,
                title=title,
                question=question,
                **kwargs,
            )
            results.append(result)
        return results
