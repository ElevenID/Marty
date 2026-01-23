"""
ISO 18013-5 Python Bridge to Rust Implementation

This module provides Python wrappers around the Rust marty-iso18013 crate,
offering a drop-in replacement for the existing Python implementation with
significant performance improvements.

Usage:
    from marty_iso18013_bridge import DeviceEngagement, Session, BleTransport
    
    # Create device engagement
    engagement = DeviceEngagement.new()
    engagement.add_ble("0000FFF0-0000-1000-8000-00805F9B34FB")
    
    # Generate QR code
    qr_data = engagement.to_bytes()
    
    # Establish session
    session = Session(engagement)
"""

from typing import Optional, Dict, List, Any
import asyncio

try:
    # Import the Rust module (built with maturin)
    from marty_iso18013 import (
        DeviceEngagement as _RustDeviceEngagement,
        SessionConfig as _RustSessionConfig,
        TransportMethod,
        EngagementMethod,
        SessionState,
        ResponseStatus,
    )
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    # Fallback to pure Python implementation
    from marty_plugin.iso18013 import (
        DeviceEngagement as _RustDeviceEngagement,
        # ... other imports
    )


class DeviceEngagement:
    """
    Device engagement for ISO 18013-5 communication.
    
    Wraps the Rust implementation with a Python-friendly API.
    """
    
    def __init__(self):
        """Create a new device engagement."""
        if RUST_AVAILABLE:
            self._inner = _RustDeviceEngagement.new()
        else:
            # Fallback to Python implementation
            from marty_plugin.iso18013.core import DeviceEngagement as PyDE
            self._inner = PyDE.new_qr()
    
    def add_ble_transport(self, service_uuid: str) -> None:
        """
        Add a BLE transport with the given service UUID.
        
        Args:
            service_uuid: BLE service UUID (e.g., "0000FFF0-0000-1000-8000-00805F9B34FB")
        """
        if RUST_AVAILABLE:
            self._inner.add_ble(service_uuid)
        else:
            self._inner.add_ble_transport(service_uuid)
    
    def add_https_transport(self, url: str) -> None:
        """
        Add an HTTPS transport with the given URL.
        
        Args:
            url: HTTPS endpoint URL
        """
        if RUST_AVAILABLE:
            self._inner.add_https(url)
        else:
            self._inner.add_https_transport(url)
    
    def to_cbor(self) -> bytes:
        """Encode the device engagement as CBOR."""
        if RUST_AVAILABLE:
            return bytes(self._inner.to_bytes())
        else:
            return self._inner.to_cbor()
    
    def to_bytes(self) -> bytes:
        """Alias for to_cbor()."""
        return self.to_cbor()
    
    @staticmethod
    def from_cbor(data: bytes) -> 'DeviceEngagement':
        """
        Decode device engagement from CBOR.
        
        Args:
            data: CBOR-encoded device engagement
            
        Returns:
            DeviceEngagement instance
        """
        engagement = DeviceEngagement.__new__(DeviceEngagement)
        if RUST_AVAILABLE:
            engagement._inner = _RustDeviceEngagement.from_bytes(data)
        else:
            from marty_plugin.iso18013.core import DeviceEngagement as PyDE
            engagement._inner = PyDE.from_cbor(data)
        return engagement
    
    @staticmethod
    def from_bytes(data: bytes) -> 'DeviceEngagement':
        """Alias for from_cbor()."""
        return DeviceEngagement.from_cbor(data)
    
    def to_qr_code(self) -> bytes:
        """
        Generate a QR code containing the device engagement.
        
        Returns:
            PNG image data
        """
        if RUST_AVAILABLE:
            # Rust implementation has built-in QR generation
            return bytes(self._inner.to_qr_code())
        else:
            # Python implementation
            import qrcode
            from io import BytesIO
            qr = qrcode.QRCode()
            qr.add_data(self.to_cbor())
            qr.make()
            img = qr.make_image()
            buf = BytesIO()
            img.save(buf, format='PNG')
            return buf.getvalue()


class SessionConfig:
    """
    Configuration for an ISO 18013-5 session.
    """
    
    def __init__(
        self,
        timeout_secs: int = 300,
        max_message_size: int = 1024 * 1024,
        verbose: bool = False
    ):
        """
        Create a new session configuration.
        
        Args:
            timeout_secs: Session timeout in seconds (default: 300)
            max_message_size: Maximum message size in bytes (default: 1MB)
            verbose: Enable verbose logging (default: False)
        """
        if RUST_AVAILABLE:
            self._inner = _RustSessionConfig(
                timeout_secs=timeout_secs,
                max_message_size=max_message_size,
                verbose=verbose
            )
        else:
            # Python implementation
            self.timeout_secs = timeout_secs
            self.max_message_size = max_message_size
            self.verbose = verbose
    
    @property
    def timeout_secs(self) -> int:
        """Get session timeout in seconds."""
        if RUST_AVAILABLE:
            return self._inner.timeout_secs
        else:
            return self._timeout_secs
    
    @timeout_secs.setter
    def timeout_secs(self, value: int):
        """Set session timeout in seconds."""
        if RUST_AVAILABLE:
            self._inner.timeout_secs = value
        else:
            self._timeout_secs = value


class Session:
    """
    ISO 18013-5 secure session.
    
    Handles session establishment, encryption, and message exchange.
    """
    
    def __init__(self, engagement: DeviceEngagement, config: Optional[SessionConfig] = None):
        """
        Create a new session from device engagement.
        
        Args:
            engagement: Device engagement
            config: Session configuration (optional)
        """
        self.engagement = engagement
        self.config = config or SessionConfig()
        self._established = False
        
        if RUST_AVAILABLE:
            # Rust implementation uses async, we'll need to handle that
            self._rust_session = None
        else:
            # Python implementation
            from marty_plugin.iso18013.protocols import OfflineProtocol
            self._protocol = OfflineProtocol()
    
    async def establish(self, peer_public_key: bytes) -> None:
        """
        Establish a secure session with the peer.
        
        Args:
            peer_public_key: Peer's public key for ECDH
        """
        if RUST_AVAILABLE:
            # TODO: Wrap Rust async session
            pass
        else:
            # Python implementation
            self._protocol.establish_session(peer_public_key)
        
        self._established = True
    
    async def send_encrypted(self, message: bytes) -> bytes:
        """
        Encrypt and send a message.
        
        Args:
            message: Plaintext message
            
        Returns:
            Encrypted message
        """
        if not self._established:
            raise RuntimeError("Session not established")
        
        if RUST_AVAILABLE:
            # TODO: Call Rust session
            pass
        else:
            return self._protocol.encrypt_message(message)
    
    async def receive_encrypted(self, ciphertext: bytes) -> bytes:
        """
        Receive and decrypt a message.
        
        Args:
            ciphertext: Encrypted message
            
        Returns:
            Decrypted message
        """
        if not self._established:
            raise RuntimeError("Session not established")
        
        if RUST_AVAILABLE:
            # TODO: Call Rust session
            pass
        else:
            return self._protocol.decrypt_message(ciphertext)


class Transport:
    """Base transport interface."""
    
    async def connect(self) -> None:
        """Connect to the transport."""
        raise NotImplementedError
    
    async def send(self, data: bytes) -> None:
        """Send data over the transport."""
        raise NotImplementedError
    
    async def receive(self) -> bytes:
        """Receive data from the transport."""
        raise NotImplementedError
    
    async def close(self) -> None:
        """Close the transport connection."""
        raise NotImplementedError
    
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        raise NotImplementedError


class BleTransport(Transport):
    """
    BLE transport for ISO 18013-5.
    
    Uses the Rust implementation for cross-platform BLE support.
    """
    
    def __init__(self, service_uuid: Optional[str] = None):
        """
        Create a new BLE transport.
        
        Args:
            service_uuid: BLE service UUID (default: MDL service UUID)
        """
        self.service_uuid = service_uuid or "0000FFF0-0000-1000-8000-00805F9B34FB"
        
        if RUST_AVAILABLE:
            # TODO: Initialize Rust BLE transport
            pass
        else:
            # Fallback to Python implementation
            from marty_plugin.iso18013.transport.ble_real import BleTransport as PyBLE
            self._inner = PyBLE(self.service_uuid)
    
    async def connect(self) -> None:
        """Connect to BLE device."""
        if RUST_AVAILABLE:
            # TODO: Call Rust transport
            pass
        else:
            await self._inner.connect()
    
    async def send(self, data: bytes) -> None:
        """Send data over BLE."""
        if RUST_AVAILABLE:
            # TODO: Call Rust transport
            pass
        else:
            await self._inner.send(data)
    
    async def receive(self) -> bytes:
        """Receive data from BLE."""
        if RUST_AVAILABLE:
            # TODO: Call Rust transport
            pass
        else:
            return await self._inner.receive()
    
    async def close(self) -> None:
        """Close BLE connection."""
        if RUST_AVAILABLE:
            # TODO: Call Rust transport
            pass
        else:
            await self._inner.close()
    
    def is_connected(self) -> bool:
        """Check if BLE is connected."""
        if RUST_AVAILABLE:
            # TODO: Call Rust transport
            return False
        else:
            return self._inner.is_connected()


# Export public API
__all__ = [
    'DeviceEngagement',
    'Session',
    'SessionConfig',
    'Transport',
    'BleTransport',
    'TransportMethod',
    'EngagementMethod',
    'SessionState',
    'ResponseStatus',
    'RUST_AVAILABLE',
]


def get_implementation() -> str:
    """
    Get the current implementation backend.
    
    Returns:
        'rust' if Rust implementation is available, 'python' otherwise
    """
    return 'rust' if RUST_AVAILABLE else 'python'


def get_version() -> str:
    """
    Get the ISO 18013-5 implementation version.
    
    Returns:
        Version string
    """
    return "0.1.0"
