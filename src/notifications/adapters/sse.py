"""
SSE Adapter

Server-Sent Events adapter for real-time dashboard notifications.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional
from uuid import UUID

from ..types import ChannelType, DeliveryResult, NotificationPayload

logger = logging.getLogger(__name__)


@dataclass
class SSEConnection:
    """A single SSE client connection."""
    id: str
    user_id: Optional[str] = None
    organization_id: Optional[UUID] = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_event_id: Optional[str] = None


class SSEAdapter:
    """
    Server-Sent Events adapter for real-time notifications.
    
    Features:
    - Connection management
    - Event broadcasting
    - User/organization targeting
    - Heartbeat support
    """
    
    def __init__(
        self,
        heartbeat_interval: int = 30,
        max_connections_per_user: int = 5,
    ):
        """
        Initialize the SSE adapter.
        
        Args:
            heartbeat_interval: Seconds between heartbeat messages
            max_connections_per_user: Maximum concurrent connections per user
        """
        self._heartbeat_interval = heartbeat_interval
        self._max_connections_per_user = max_connections_per_user
        self._connections: dict[str, SSEConnection] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the SSE adapter (heartbeat task)."""
        if self._running:
            return
        
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("SSE adapter started")
    
    async def stop(self) -> None:
        """Stop the SSE adapter."""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        for conn in list(self._connections.values()):
            await conn.queue.put(None)  # Signal close
        
        self._connections.clear()
        logger.info("SSE adapter stopped")
    
    def add_connection(
        self,
        connection_id: str,
        user_id: Optional[str] = None,
        organization_id: Optional[UUID] = None,
    ) -> SSEConnection:
        """
        Add a new SSE connection.
        
        Args:
            connection_id: Unique connection identifier
            user_id: Optional user identifier
            organization_id: Optional organization identifier
            
        Returns:
            SSEConnection object
        """
        # Check connection limit
        if user_id:
            user_connections = [
                c for c in self._connections.values()
                if c.user_id == user_id
            ]
            if len(user_connections) >= self._max_connections_per_user:
                # Remove oldest connection
                oldest = min(user_connections, key=lambda c: c.connected_at)
                self.remove_connection(oldest.id)
        
        connection = SSEConnection(
            id=connection_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        self._connections[connection_id] = connection
        
        logger.debug(f"Added SSE connection {connection_id}")
        return connection
    
    def remove_connection(self, connection_id: str) -> None:
        """Remove an SSE connection."""
        if connection_id in self._connections:
            del self._connections[connection_id]
            logger.debug(f"Removed SSE connection {connection_id}")
    
    async def send(self, payload: NotificationPayload) -> DeliveryResult:
        """
        Send a notification via SSE.
        
        Broadcasts to matching connections based on target.
        
        Args:
            payload: The notification payload
            
        Returns:
            DeliveryResult with success status
        """
        matching_connections = self._get_matching_connections(payload)
        
        if not matching_connections:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.SSE,
                success=True,
                metadata={"connections": 0, "skipped": "No matching connections"},
            )
        
        # Build SSE event
        event = self._build_event(payload)
        
        # Send to all matching connections
        send_count = 0
        for conn in matching_connections:
            try:
                await asyncio.wait_for(
                    conn.queue.put(event),
                    timeout=1.0,
                )
                send_count += 1
            except asyncio.TimeoutError:
                logger.warning(f"Timeout sending to connection {conn.id}")
            except Exception as e:
                logger.error(f"Error sending to connection {conn.id}: {e}")
        
        return DeliveryResult(
            notification_id=payload.id,
            channel=ChannelType.SSE,
            success=send_count > 0,
            delivered_at=datetime.now(timezone.utc) if send_count > 0 else None,
            metadata={
                "connections": send_count,
                "total_matched": len(matching_connections),
            },
        )
    
    def _get_matching_connections(
        self,
        payload: NotificationPayload,
    ) -> list[SSEConnection]:
        """Get connections that should receive this notification."""
        matching = []
        
        for conn in self._connections.values():
            # Check organization match
            if payload.target and payload.target.organization_id:
                if conn.organization_id == payload.target.organization_id:
                    matching.append(conn)
                    continue
            
            # Check user match
            if payload.target and payload.target.user_id:
                if conn.user_id == payload.target.user_id:
                    matching.append(conn)
                    continue
            
            # If no specific target, send to all
            if not payload.target:
                matching.append(conn)
        
        return matching
    
    def _build_event(self, payload: NotificationPayload) -> str:
        """Build SSE event string."""
        data = json.dumps({
            "id": str(payload.id),
            "type": payload.event_type,
            "title": payload.title,
            "body": payload.body,
            "data": payload.data,
            "timestamp": payload.created_at.isoformat(),
        })
        
        lines = [
            f"id: {payload.id}",
            f"event: {payload.event_type}",
            f"data: {data}",
            "",  # Empty line to end event
        ]
        
        return "\n".join(lines)
    
    async def event_stream(
        self,
        connection: SSEConnection,
    ) -> AsyncIterator[str]:
        """
        Generate SSE event stream for a connection.
        
        This is an async generator that yields SSE events.
        Use this in a FastAPI streaming response.
        
        Args:
            connection: The SSE connection
            
        Yields:
            SSE formatted event strings
        """
        try:
            while self._running:
                try:
                    # Wait for event with timeout for heartbeat
                    event = await asyncio.wait_for(
                        connection.queue.get(),
                        timeout=self._heartbeat_interval,
                    )
                    
                    if event is None:
                        break  # Connection closed
                    
                    yield event
                    
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield ": heartbeat\n\n"
                    
        finally:
            self.remove_connection(connection.id)
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to all connections."""
        while self._running:
            await asyncio.sleep(self._heartbeat_interval)
            
            # Heartbeats are handled in event_stream via timeout
            # This loop is for connection cleanup
            now = datetime.now(timezone.utc)
            stale = []
            
            for conn_id, conn in self._connections.items():
                # Check for stale connections (no activity for 5 minutes)
                if (now - conn.connected_at).total_seconds() > 300:
                    if conn.queue.empty():
                        stale.append(conn_id)
            
            for conn_id in stale:
                logger.info(f"Removing stale connection {conn_id}")
                self.remove_connection(conn_id)
    
    @property
    def connection_count(self) -> int:
        """Get current connection count."""
        return len(self._connections)
    
    def get_connection_stats(self) -> dict[str, Any]:
        """Get connection statistics."""
        by_org: dict[str, int] = {}
        by_user: dict[str, int] = {}
        
        for conn in self._connections.values():
            if conn.organization_id:
                org_key = str(conn.organization_id)
                by_org[org_key] = by_org.get(org_key, 0) + 1
            if conn.user_id:
                by_user[conn.user_id] = by_user.get(conn.user_id, 0) + 1
        
        return {
            "total_connections": len(self._connections),
            "by_organization": by_org,
            "by_user": by_user,
        }
    
    async def close(self) -> None:
        """Close the adapter (alias for stop)."""
        await self.stop()
