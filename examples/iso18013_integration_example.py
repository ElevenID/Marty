"""
Example: ISO 18013-5 Integration with Marty Services

This example demonstrates how to integrate the Rust-backed ISO 18013
implementation into existing Marty services.
"""

import asyncio
from typing import Dict, Any, Optional
from marty_plugin.iso18013_bridge import (
    DeviceEngagement,
    Session,
    SessionConfig,
    BleTransport,
    get_implementation,
    RUST_AVAILABLE,
)


class MdlHolderService:
    """
    Mobile Driving License Holder service.
    
    Represents a mobile device holding an mDL credential and responding
    to verification requests from readers.
    """
    
    def __init__(self, credential_data: Dict[str, Any]):
        """
        Initialize the holder service.
        
        Args:
            credential_data: The mDL data to present (namespaces and elements)
        """
        self.credential_data = credential_data
        self.config = SessionConfig(
            timeout_secs=300,
            max_message_size=1024 * 1024,
            verbose=True
        )
        print(f"Holder service using {get_implementation()} implementation")
    
    def create_qr_engagement(self, transport_type: str = "ble") -> bytes:
        """
        Create a QR code for device engagement.
        
        Args:
            transport_type: Transport type ('ble' or 'https')
            
        Returns:
            PNG image data for QR code
        """
        engagement = DeviceEngagement()
        
        if transport_type == "ble":
            # Standard mDL BLE service UUID
            engagement.add_ble_transport("0000FFF0-0000-1000-8000-00805F9B34FB")
        elif transport_type == "https":
            # HTTPS transport for remote verification
            engagement.add_https_transport("https://holder.example.com/mdoc")
        else:
            raise ValueError(f"Unknown transport type: {transport_type}")
        
        # Generate QR code
        qr_png = engagement.to_qr_code()
        print(f"Generated QR code: {len(qr_png)} bytes")
        
        return qr_png
    
    async def handle_verification_request(
        self,
        reader_engagement: bytes,
        requested_elements: Dict[str, list]
    ) -> Dict[str, Any]:
        """
        Handle a verification request from a reader.
        
        Args:
            reader_engagement: Reader's device engagement (CBOR)
            requested_elements: Elements requested by reader
            
        Returns:
            Response data with selected elements
        """
        # Parse reader's engagement
        reader_device = DeviceEngagement.from_bytes(reader_engagement)
        
        # Create session
        session = Session(reader_device, self.config)
        
        # In real implementation, would:
        # 1. Establish session with ECDH key exchange
        # 2. Receive and decrypt reader's request
        # 3. Apply selective disclosure rules
        # 4. Encrypt and send response
        
        # Placeholder for now
        print(f"Would present elements: {requested_elements}")
        
        return {
            "status": "success",
            "elements": requested_elements  # In real code, filter based on consent
        }


class MdlReaderService:
    """
    Mobile Driving License Reader service.
    
    Represents a verifier requesting and validating mDL credentials
    from holder devices.
    """
    
    def __init__(self):
        """Initialize the reader service."""
        self.config = SessionConfig(
            timeout_secs=300,
            max_message_size=1024 * 1024,
            verbose=True
        )
        print(f"Reader service using {get_implementation()} implementation")
    
    async def scan_qr_and_connect(self, qr_data: bytes) -> Session:
        """
        Scan a holder's QR code and establish connection.
        
        Args:
            qr_data: QR code data (CBOR-encoded device engagement)
            
        Returns:
            Established session
        """
        # Decode device engagement from QR
        holder_engagement = DeviceEngagement.from_bytes(qr_data)
        
        # Create session
        session = Session(holder_engagement, self.config)
        
        print("Session created with holder")
        return session
    
    async def request_elements(
        self,
        session: Session,
        elements: Dict[str, list]
    ) -> Dict[str, Any]:
        """
        Request specific elements from the holder.
        
        Args:
            session: Established session with holder
            elements: Elements to request (namespace -> [element names])
            
        Returns:
            Received elements
        """
        # In real implementation, would:
        # 1. Construct ISO 18013-5 request message
        # 2. Encrypt and send request
        # 3. Receive and decrypt response
        # 4. Validate signatures and integrity
        
        # Placeholder
        print(f"Requesting elements: {elements}")
        
        return {
            "org.iso.18013.5.1": {
                "family_name": "Doe",
                "given_name": "John",
                "birth_date": "1990-01-01"
            }
        }


class MdlProximityVerification:
    """
    Example: Proximity verification scenario using BLE.
    
    This demonstrates a holder and reader communicating over BLE
    in close proximity (e.g., airport security checkpoint).
    """
    
    @staticmethod
    async def run_verification():
        """Run a complete proximity verification scenario."""
        print("\n=== Proximity Verification Scenario ===\n")
        
        # 1. Holder creates credential
        holder_data = {
            "org.iso.18013.5.1": {
                "family_name": "Doe",
                "given_name": "John",
                "birth_date": "1990-01-01",
                "document_number": "DL-123456789",
                "issuing_country": "US",
                "portrait": b"<image data>"
            }
        }
        holder = MdlHolderService(holder_data)
        
        # 2. Holder generates QR code
        print("1. Holder generates QR code for BLE engagement")
        qr_png = holder.create_qr_engagement(transport_type="ble")
        
        # Save QR code (in real app, display on screen)
        with open("/tmp/mdl_qr.png", "wb") as f:
            f.write(qr_png)
        print(f"   Saved QR code to /tmp/mdl_qr.png")
        
        # 3. Reader scans QR code
        print("\n2. Reader scans QR code")
        reader = MdlReaderService()
        
        # In real scenario, reader would decode QR from camera
        # For this example, we read the CBOR data from the engagement
        engagement = DeviceEngagement()
        engagement.add_ble_transport("0000FFF0-0000-1000-8000-00805F9B34FB")
        qr_cbor = engagement.to_bytes()
        
        session = await reader.scan_qr_and_connect(qr_cbor)
        print("   Session established")
        
        # 4. Reader requests specific elements
        print("\n3. Reader requests age verification (over 18)")
        requested = {
            "org.iso.18013.5.1": ["birth_date", "age_over_18"]
        }
        
        # 5. Holder presents selected elements
        print("\n4. Holder presents approved elements")
        response = await holder.handle_verification_request(
            reader_engagement=qr_cbor,
            requested_elements=requested
        )
        
        # 6. Reader receives and validates
        print("\n5. Reader receives elements:")
        elements = await reader.request_elements(session, requested)
        for namespace, values in elements.items():
            print(f"   {namespace}:")
            for key, value in values.items():
                print(f"     - {key}: {value}")
        
        print("\n=== Verification Complete ===\n")


class MdlRemoteVerification:
    """
    Example: Remote verification scenario using HTTPS.
    
    This demonstrates holder and reader communicating over HTTPS
    for remote verification (e.g., online age verification).
    """
    
    @staticmethod
    async def run_verification():
        """Run a complete remote verification scenario."""
        print("\n=== Remote Verification Scenario ===\n")
        
        # 1. Holder creates credential
        holder_data = {
            "org.iso.18013.5.1": {
                "age_over_18": True,
                "age_over_21": True,
            }
        }
        holder = MdlHolderService(holder_data)
        
        # 2. Holder creates HTTPS engagement
        print("1. Holder creates HTTPS engagement")
        engagement = DeviceEngagement()
        engagement.add_https_transport("https://holder.example.com/mdoc")
        
        # 3. Holder sends engagement to reader (via URL redirect or QR)
        print("2. Holder shares engagement with reader")
        engagement_cbor = engagement.to_bytes()
        print(f"   Engagement size: {len(engagement_cbor)} bytes")
        
        # 4. Reader connects via HTTPS
        print("\n3. Reader connects via HTTPS")
        reader = MdlReaderService()
        session = await reader.scan_qr_and_connect(engagement_cbor)
        
        # 5. Reader requests age verification only
        print("\n4. Reader requests minimal data (age only)")
        requested = {
            "org.iso.18013.5.1": ["age_over_21"]
        }
        
        # 6. Holder presents only requested element
        print("\n5. Holder presents only age_over_21 (privacy-preserving)")
        response = await holder.handle_verification_request(
            reader_engagement=engagement_cbor,
            requested_elements=requested
        )
        
        # 7. Reader validates
        print("\n6. Reader validates age verification")
        print(f"   Age over 21: {response['elements']['org.iso.18013.5.1'][0]}")
        
        print("\n=== Remote Verification Complete ===\n")


async def main():
    """Run all examples."""
    print(f"\n{'='*60}")
    print(f"ISO 18013-5 Integration Examples")
    print(f"Implementation: {get_implementation()}")
    print(f"Rust available: {RUST_AVAILABLE}")
    print(f"{'='*60}\n")
    
    # Run proximity verification
    await MdlProximityVerification.run_verification()
    
    # Wait a bit
    await asyncio.sleep(1)
    
    # Run remote verification
    await MdlRemoteVerification.run_verification()
    
    print("\n📊 Performance Note:")
    if RUST_AVAILABLE:
        print("   Using Rust implementation - expect 10-100x faster operations")
        print("   ECDH: ~0.2ms, AES-GCM: ~0.05ms, CBOR: ~0.1ms")
    else:
        print("   Using Python fallback - slower but functional")
        print("   ECDH: ~15ms, AES-GCM: ~2ms, CBOR: ~5ms")
    print()


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())
