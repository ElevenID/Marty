"""
ISO/IEC 18013-5 Reference Holder Application (Wallet)

This module implements a complete reference holder application demonstrating:
- Device engagement and QR code generation
- Consent management and user prompts
- Credential presentation and selective disclosure
- Multiple transport support (BLE, NFC, HTTPS)
- Secure element integration (simulated)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import qrcode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ..core import DeviceEngagement, SelectiveDisclosure, mDLRequest, mDLResponse
from ..crypto import DigitalSignature, KeyManager, SessionEncryption
from ..online import ConsentRequest, ConsentResponse, ISO18013_7Holder
from ..protocols import ISO18013_5Protocol, ProtocolState
from ..transport import TransportInterface, create_transport

logger = logging.getLogger(__name__)


class HolderMode(Enum):
    """Holder operation modes"""

    PASSIVE_BLE = "passive_ble"  # Advertise and wait for connections
    PASSIVE_NFC = "passive_nfc"  # Card emulation mode
    ACTIVE_HTTPS = "active_https"  # Active online presentation
    QR_ENGAGEMENT = "qr_engagement"  # Display QR for reader scanning


class ConsentLevel(Enum):
    """Consent interaction levels"""

    AUTOMATIC = "automatic"  # Pre-approved requests
    PROMPT_ONLY = "prompt_only"  # Simple yes/no prompts
    DETAILED = "detailed"  # Show specific data elements
    SECURE_ENTRY = "secure_entry"  # Require PIN/biometric


@dataclass
class mDLCredential:
    """mDL credential container"""

    document_number: str
    issuing_country: str
    issuing_authority: str
    family_name: str
    given_name: str
    birth_date: str
    expiry_date: str
    portrait: bytes | None = None
    signature: bytes | None = None

    # Additional elements
    issuing_date: str | None = None
    driving_privileges: list[dict[str, Any]] | None = None
    administrative_number: str | None = None
    sex: str | None = None
    height: str | None = None
    weight: str | None = None
    eye_color: str | None = None
    hair_color: str | None = None
    nationality: str | None = None
    resident_address: str | None = None

    def to_cbor(self) -> dict[str, Any]:
        """Convert to CBOR representation"""
        data = {
            "family_name": self.family_name,
            "given_name": self.given_name,
            "birth_date": self.birth_date,
            "document_number": self.document_number,
            "issuing_country": self.issuing_country,
            "issuing_authority": self.issuing_authority,
            "expiry_date": self.expiry_date,
        }

        # Add optional elements if present
        optional_fields = [
            "issuing_date",
            "administrative_number",
            "sex",
            "height",
            "weight",
            "eye_color",
            "hair_color",
            "nationality",
            "resident_address",
        ]

        for field in optional_fields:
            value = getattr(self, field)
            if value is not None:
                data[field] = value

        if self.driving_privileges:
            data["driving_privileges"] = self.driving_privileges

        if self.portrait:
            data["portrait"] = self.portrait

        return data


@dataclass
class HolderConfig:
    """Holder application configuration"""

    holder_id: str
    wallet_name: str = "ISO 18013 Reference Wallet"
    consent_level: ConsentLevel = ConsentLevel.DETAILED
    key_storage_path: str = "./wallet_keys"
    credential_storage_path: str = "./credentials"
    log_level: str = "INFO"

    # Transport settings
    ble_device_name: str = "mDL Wallet"
    ble_advertise_timeout: float = 60.0
    nfc_card_name: str = "mDL Card"

    # Security settings
    pin_required: bool = True
    biometric_enabled: bool = False
    auto_consent_trusted: list[str] = None
    session_timeout: int = 300

    # Privacy settings
    minimize_disclosure: bool = True
    audit_presentations: bool = True

    def __post_init__(self):
        if self.auto_consent_trusted is None:
            self.auto_consent_trusted = []


class ConsentManager:
    """Manages user consent for data presentation"""

    def __init__(self, config: HolderConfig):
        self.config = config
        self.logger = logging.getLogger(f"ConsentManager.{config.holder_id}")

        # Consent cache for trusted readers
        self.consent_cache = {}
        self.presentation_audit = []

    async def request_consent(
        self, reader_info: dict[str, Any], requested_elements: dict[str, list[str]], session_id: str
    ) -> ConsentResponse:
        """
        Request user consent for data presentation

        Args:
            reader_info: Reader identification and trust info
            requested_elements: Requested data elements by namespace
            session_id: Session identifier

        Returns:
            Consent response with approved elements
        """
        try:
            reader_id = reader_info.get("reader_id", "unknown")
            reader_org = reader_info.get("organization", "unknown")

            self.logger.info(f"Consent request from {reader_org} ({reader_id})")

            # Check if reader is in trusted list
            if reader_id in self.config.auto_consent_trusted:
                self.logger.info("Reader is trusted, auto-approving")
                return ConsentResponse(
                    approved=True,
                    approved_elements=requested_elements,
                    consent_level="trusted",
                    timestamp=datetime.utcnow(),
                )

            # Handle different consent levels
            if self.config.consent_level == ConsentLevel.AUTOMATIC:
                return ConsentResponse(
                    approved=True,
                    approved_elements=requested_elements,
                    consent_level="automatic",
                    timestamp=datetime.utcnow(),
                )

            elif self.config.consent_level == ConsentLevel.PROMPT_ONLY:
                return await self._prompt_basic_consent(reader_info, requested_elements)

            elif self.config.consent_level == ConsentLevel.DETAILED:
                return await self._prompt_detailed_consent(reader_info, requested_elements)

            elif self.config.consent_level == ConsentLevel.SECURE_ENTRY:
                # Require PIN/biometric first
                if not await self._verify_secure_entry():
                    return ConsentResponse(
                        approved=False, error="Authentication required", timestamp=datetime.utcnow()
                    )
                return await self._prompt_detailed_consent(reader_info, requested_elements)

        except Exception as e:
            self.logger.error(f"Consent request failed: {e}")
            return ConsentResponse(
                approved=False, error=f"Consent failed: {e}", timestamp=datetime.utcnow()
            )

    async def _prompt_basic_consent(
        self, reader_info: dict[str, Any], requested_elements: dict[str, list[str]]
    ) -> ConsentResponse:
        """Basic consent prompt"""
        try:
            print("\n📱 mDL Presentation Request")
            print(f"Reader: {reader_info.get('organization', 'Unknown')}")
            print(f"Reader ID: {reader_info.get('reader_id', 'Unknown')}")

            # Count total elements
            total_elements = sum(len(elements) for elements in requested_elements.values())
            print(f"Requesting {total_elements} data elements from your mDL")

            response = input("Share your mDL information? (y/n): ").strip().lower()

            if response in ["y", "yes"]:
                return ConsentResponse(
                    approved=True,
                    approved_elements=requested_elements,
                    consent_level="basic",
                    timestamp=datetime.utcnow(),
                )
            else:
                return ConsentResponse(
                    approved=False, consent_level="basic", timestamp=datetime.utcnow()
                )

        except Exception as e:
            return ConsentResponse(
                approved=False, error=f"Consent prompt failed: {e}", timestamp=datetime.utcnow()
            )

    async def _prompt_detailed_consent(
        self, reader_info: dict[str, Any], requested_elements: dict[str, list[str]]
    ) -> ConsentResponse:
        """Detailed consent prompt with element selection"""
        try:
            print("\n📱 mDL Presentation Request")
            print(f"Reader: {reader_info.get('organization', 'Unknown')}")
            print(f"Reader ID: {reader_info.get('reader_id', 'Unknown')}")
            print(f"Trust Level: {reader_info.get('trust_level', 'Unverified')}")

            approved_elements = {}

            for namespace, elements in requested_elements.items():
                print(f"\nNamespace: {namespace}")
                print("Requested data elements:")

                namespace_approved = []
                for i, element in enumerate(elements, 1):
                    element_name = element.replace("_", " ").title()
                    print(f"  {i}. {element_name}")

                print(f"\nApprove all elements for {namespace}? (y/n/s for selective): ", end="")
                response = input().strip().lower()

                if response in ["y", "yes"]:
                    namespace_approved = elements
                elif response == "s":
                    # Selective approval
                    print("Select elements to approve (comma-separated numbers):", end=" ")
                    try:
                        selected = input().strip()
                        if selected:
                            indices = [int(x.strip()) - 1 for x in selected.split(",")]
                            namespace_approved = [
                                elements[i] for i in indices if 0 <= i < len(elements)
                            ]
                    except:
                        print("Invalid selection, skipping namespace")
                        continue
                else:
                    print("Namespace denied")
                    continue

                if namespace_approved:
                    approved_elements[namespace] = namespace_approved

            if approved_elements:
                print(f"\nApproved {sum(len(e) for e in approved_elements.values())} data elements")
                return ConsentResponse(
                    approved=True,
                    approved_elements=approved_elements,
                    consent_level="detailed",
                    timestamp=datetime.utcnow(),
                )
            else:
                print("No elements approved")
                return ConsentResponse(
                    approved=False, consent_level="detailed", timestamp=datetime.utcnow()
                )

        except Exception as e:
            return ConsentResponse(
                approved=False, error=f"Detailed consent failed: {e}", timestamp=datetime.utcnow()
            )

    async def _verify_secure_entry(self) -> bool:
        """Verify PIN or biometric authentication"""
        try:
            if self.config.pin_required:
                print("\n🔐 Security Verification Required")
                pin = input("Enter your wallet PIN: ").strip()
                # Simplified PIN check (in real app would be properly hashed/secured)
                return pin == "123456"  # Demo PIN

            return True

        except Exception as e:
            self.logger.error(f"Secure entry verification failed: {e}")
            return False

    def audit_presentation(
        self, reader_info: dict[str, Any], presented_elements: dict[str, list[str]], session_id: str
    ) -> None:
        """Audit credential presentation"""
        if self.config.audit_presentations:
            audit_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "reader_id": reader_info.get("reader_id"),
                "reader_org": reader_info.get("organization"),
                "session_id": session_id,
                "presented_elements": presented_elements,
                "element_count": sum(len(elements) for elements in presented_elements.values()),
            }

            self.presentation_audit.append(audit_entry)
            self.logger.info(f"Presentation audited: {session_id}")


class ISO18013HolderApp:
    """
    Reference Holder Application (Wallet) for ISO/IEC 18013-5

    Demonstrates complete mDL holder capabilities including credential storage,
    consent management, and multi-transport presentation.
    """

    def __init__(self, config: HolderConfig):
        self.config = config
        self.logger = self._setup_logging()

        # Key management
        self.holder_private_key = None
        self.holder_public_key = None

        # Credential storage
        self.credentials = {}

        # Protocol and transport
        self.protocol = ISO18013_5Protocol()
        self.online_holder = None
        self.active_transports = {}
        self.active_sessions = {}

        # Consent management
        self.consent_manager = ConsentManager(config)

        # Initialize
        self._load_or_generate_keys()
        self._load_credentials()

    def _setup_logging(self) -> logging.Logger:
        """Setup application logging"""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        return logging.getLogger(f"ISO18013Holder.{self.config.holder_id}")

    def _load_or_generate_keys(self) -> None:
        """Load or generate holder key pair"""
        try:
            key_path = Path(self.config.key_storage_path)
            key_path.mkdir(exist_ok=True)

            private_key_file = key_path / f"{self.config.holder_id}_private.pem"
            public_key_file = key_path / f"{self.config.holder_id}_public.pem"

            if private_key_file.exists() and public_key_file.exists():
                # Load existing keys
                with open(private_key_file, "rb") as f:
                    self.holder_private_key = serialization.load_pem_private_key(
                        f.read(), password=None
                    )

                with open(public_key_file, "rb") as f:
                    self.holder_public_key = serialization.load_pem_public_key(f.read())

                self.logger.info("Loaded existing holder keys")
            else:
                # Generate new keys
                self.holder_private_key, self.holder_public_key = (
                    KeyManager.generate_ephemeral_keypair()
                )

                # Save keys
                with open(private_key_file, "wb") as f:
                    f.write(
                        self.holder_private_key.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.PKCS8,
                            encryption_algorithm=serialization.NoEncryption(),
                        )
                    )

                with open(public_key_file, "wb") as f:
                    f.write(
                        self.holder_public_key.public_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PublicFormat.SubjectPublicKeyInfo,
                        )
                    )

                self.logger.info("Generated new holder keys")

        except Exception as e:
            self.logger.error(f"Key management error: {e}")
            raise

    def _load_credentials(self) -> None:
        """Load stored credentials"""
        try:
            cred_path = Path(self.config.credential_storage_path)
            cred_path.mkdir(exist_ok=True)

            cred_file = cred_path / f"{self.config.holder_id}_credentials.json"

            if cred_file.exists():
                with open(cred_file) as f:
                    cred_data = json.load(f)

                for doc_type, cred_dict in cred_data.items():
                    self.credentials[doc_type] = mDLCredential(**cred_dict)

                self.logger.info(f"Loaded {len(self.credentials)} credentials")
            else:
                # Create demo credential
                self._create_demo_credential()

        except Exception as e:
            self.logger.error(f"Credential loading error: {e}")
            self._create_demo_credential()

    def _create_demo_credential(self) -> None:
        """Create a demo mDL credential for testing"""
        try:
            demo_credential = mDLCredential(
                document_number="DL123456789",
                issuing_country="US",
                issuing_authority="Department of Motor Vehicles",
                family_name="Doe",
                given_name="John",
                birth_date="1990-01-01",
                expiry_date="2029-01-01",
                issuing_date="2019-01-01",
                sex="M",
                height="180 cm",
                weight="75 kg",
                eye_color="Brown",
                hair_color="Black",
                nationality="US",
                resident_address="123 Main St, Anytown, ST 12345",
                driving_privileges=[
                    {
                        "vehicle_category_code": "A",
                        "issue_date": "2019-01-01",
                        "expiry_date": "2029-01-01",
                    },
                    {
                        "vehicle_category_code": "B",
                        "issue_date": "2019-01-01",
                        "expiry_date": "2029-01-01",
                    },
                ],
            )

            self.credentials["org.iso.18013.5.1.mDL"] = demo_credential
            self._save_credentials()

            self.logger.info("Created demo mDL credential")

        except Exception as e:
            self.logger.error(f"Demo credential creation failed: {e}")

    def _save_credentials(self) -> None:
        """Save credentials to storage"""
        try:
            cred_path = Path(self.config.credential_storage_path)
            cred_file = cred_path / f"{self.config.holder_id}_credentials.json"

            # Convert credentials to JSON-serializable format
            cred_data = {}
            for doc_type, credential in self.credentials.items():
                cred_dict = credential.__dict__.copy()
                # Handle bytes fields
                if "portrait" in cred_dict and cred_dict["portrait"]:
                    cred_dict["portrait"] = cred_dict["portrait"].hex()
                if "signature" in cred_dict and cred_dict["signature"]:
                    cred_dict["signature"] = cred_dict["signature"].hex()

                cred_data[doc_type] = cred_dict

            with open(cred_file, "w") as f:
                json.dump(cred_data, f, indent=2)

            self.logger.info("Credentials saved")

        except Exception as e:
            self.logger.error(f"Credential saving failed: {e}")

    async def start_holder(self) -> None:
        """Start the holder application"""
        try:
            self.logger.info(f"Starting ISO 18013-5 Holder: {self.config.holder_id}")
            self.logger.info(f"Wallet: {self.config.wallet_name}")
            self.logger.info(f"Credentials: {len(self.credentials)} loaded")

            # Initialize online holder if needed
            self.online_holder = ISO18013_7Holder(
                holder_id=self.config.holder_id, credentials=self.credentials
            )

            self.logger.info("Holder application started successfully")

        except Exception as e:
            self.logger.error(f"Holder startup failed: {e}")
            raise

    async def stop_holder(self) -> None:
        """Stop the holder application"""
        try:
            # Close active sessions
            for session_id in list(self.active_sessions.keys()):
                await self.terminate_session(session_id)

            # Close transports
            for transport in self.active_transports.values():
                await transport.disconnect()

            self.logger.info("Holder application stopped")

        except Exception as e:
            self.logger.error(f"Holder shutdown error: {e}")

    async def start_passive_mode(self, transport_type: str) -> str:
        """
        Start passive mode (advertising/waiting for readers)

        Args:
            transport_type: Transport to use ("ble", "nfc")

        Returns:
            Session ID or engagement data
        """
        try:
            if transport_type == "ble":
                # Start BLE advertising
                from ..transport.ble_real import BLEPeripheralServer

                peripheral = BLEPeripheralServer(
                    device_name=self.config.ble_device_name, holder_app=self
                )

                await peripheral.start_advertising()
                self.active_transports["ble"] = peripheral

                self.logger.info(f"BLE advertising started: {self.config.ble_device_name}")
                return f"ble_advertising_{int(time.time())}"

            elif transport_type == "nfc":
                # Start NFC card emulation
                from ..transport.nfc_real import NFCCardEmulator

                emulator = NFCCardEmulator(card_name=self.config.nfc_card_name, holder_app=self)

                await emulator.start_emulation()
                self.active_transports["nfc"] = emulator

                self.logger.info(f"NFC card emulation started: {self.config.nfc_card_name}")
                return f"nfc_emulation_{int(time.time())}"

            else:
                raise ValueError(f"Unsupported passive transport: {transport_type}")

        except Exception as e:
            self.logger.error(f"Passive mode startup failed: {e}")
            raise

    def generate_engagement_qr(self) -> str:
        """Generate device engagement QR code"""
        try:
            # Create device engagement
            engagement = DeviceEngagement(
                device_key=self.holder_public_key,
                supported_transports=["ble", "nfc"],
                device_info={
                    "name": self.config.ble_device_name,
                    "holder_id": self.config.holder_id,
                },
            )

            qr_content = engagement.to_qr_content()

            # Generate QR code image
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_content)
            qr.make(fit=True)

            # Save QR code
            qr_path = Path(self.config.key_storage_path) / "device_engagement.png"
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(qr_path)

            self.logger.info(f"Device engagement QR saved: {qr_path}")
            return qr_content

        except Exception as e:
            self.logger.error(f"QR generation failed: {e}")
            raise

    async def handle_presentation_request(
        self, session_id: str, reader_info: dict[str, Any], requested_elements: dict[str, list[str]]
    ) -> bool:
        """
        Handle mDL presentation request from reader

        Args:
            session_id: Session identifier
            reader_info: Reader information
            requested_elements: Requested data elements

        Returns:
            True if presentation was approved and sent
        """
        try:
            self.logger.info(f"Presentation request: {session_id}")

            # Request user consent
            consent = await self.consent_manager.request_consent(
                reader_info, requested_elements, session_id
            )

            if not consent.approved:
                self.logger.info("Presentation denied by user")
                return False

            # Create selective disclosure
            response_data = {}

            for namespace, elements in consent.approved_elements.items():
                if namespace in self.credentials:
                    credential = self.credentials[namespace]
                    credential_data = credential.to_cbor()

                    # Apply selective disclosure
                    disclosed_data = {}
                    for element in elements:
                        if element in credential_data:
                            disclosed_data[element] = credential_data[element]

                    response_data[namespace] = disclosed_data

            # Create and send mDL response
            response = mDLResponse(documents=response_data, status="OK")

            # Send response through protocol
            await self.protocol.send_mdl_response(session_id, response)

            # Audit the presentation
            self.consent_manager.audit_presentation(
                reader_info, consent.approved_elements, session_id
            )

            self.logger.info(f"Presentation completed: {session_id}")
            return True

        except Exception as e:
            self.logger.error(f"Presentation handling failed: {e}")
            return False

    async def terminate_session(self, session_id: str) -> None:
        """Terminate a presentation session"""
        try:
            if session_id in self.active_sessions:
                await self.protocol.terminate_session(session_id)
                del self.active_sessions[session_id]
                self.logger.info(f"Session terminated: {session_id}")
        except Exception as e:
            self.logger.error(f"Session termination failed: {e}")

    def get_credentials_info(self) -> list[dict[str, Any]]:
        """Get information about stored credentials"""
        info = []
        for doc_type, credential in self.credentials.items():
            info.append(
                {
                    "document_type": doc_type,
                    "document_number": credential.document_number,
                    "issuing_country": credential.issuing_country,
                    "issuing_authority": credential.issuing_authority,
                    "holder_name": f"{credential.given_name} {credential.family_name}",
                    "expiry_date": credential.expiry_date,
                    "status": "valid",  # Would check actual status in real app
                }
            )
        return info

    def get_presentation_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent presentation history"""
        return sorted(
            self.consent_manager.presentation_audit, key=lambda x: x["timestamp"], reverse=True
        )[:limit]

    def add_credential(self, doc_type: str, credential_data: dict[str, Any]) -> None:
        """Add a new credential to the wallet"""
        try:
            credential = mDLCredential(**credential_data)
            self.credentials[doc_type] = credential
            self._save_credentials()

            self.logger.info(f"Credential added: {doc_type}")

        except Exception as e:
            self.logger.error(f"Credential addition failed: {e}")
            raise

    def remove_credential(self, doc_type: str) -> bool:
        """Remove a credential from the wallet"""
        try:
            if doc_type in self.credentials:
                del self.credentials[doc_type]
                self._save_credentials()
                self.logger.info(f"Credential removed: {doc_type}")
                return True
            return False

        except Exception as e:
            self.logger.error(f"Credential removal failed: {e}")
            return False


# CLI interface for the holder application
async def main():
    """Main CLI interface for the reference holder"""
    import argparse

    parser = argparse.ArgumentParser(description="ISO 18013-5 Reference Holder Application")
    parser.add_argument("--holder-id", default="holder_001", help="Holder identifier")
    parser.add_argument("--wallet-name", default="ISO 18013 Reference Wallet", help="Wallet name")
    parser.add_argument(
        "--consent-level",
        default="detailed",
        choices=["automatic", "prompt_only", "detailed", "secure_entry"],
        help="Consent interaction level",
    )
    parser.add_argument(
        "--mode",
        default="interactive",
        choices=["interactive", "passive_ble", "passive_nfc", "qr", "credentials"],
        help="Operation mode",
    )
    parser.add_argument("--log-level", default="INFO", help="Log level")

    args = parser.parse_args()

    # Create configuration
    config = HolderConfig(
        holder_id=args.holder_id,
        wallet_name=args.wallet_name,
        consent_level=ConsentLevel(args.consent_level),
        log_level=args.log_level,
    )

    # Initialize holder
    holder = ISO18013HolderApp(config)

    try:
        await holder.start_holder()

        if args.mode == "passive_ble":
            # BLE advertising mode
            session_id = await holder.start_passive_mode("ble")
            print(f"BLE advertising started: {session_id}")
            print("Waiting for reader connections... (Ctrl+C to stop)")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping BLE advertising")

        elif args.mode == "passive_nfc":
            # NFC card emulation mode
            session_id = await holder.start_passive_mode("nfc")
            print(f"NFC card emulation started: {session_id}")
            print("Waiting for reader connections... (Ctrl+C to stop)")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping NFC emulation")

        elif args.mode == "qr":
            # QR code generation mode
            qr_content = holder.generate_engagement_qr()
            print("\nDevice Engagement QR Code:")
            print(qr_content)
            print("\nScan this QR code with a reader to initiate mDL presentation")

        elif args.mode == "credentials":
            # Credential management mode
            credentials = holder.get_credentials_info()
            print(f"\nStored Credentials ({len(credentials)}):")
            for cred in credentials:
                print(
                    f"  - {cred['document_type']}: {cred['holder_name']} ({cred['document_number']})"
                )
                print(f"    Issuer: {cred['issuing_authority']}, {cred['issuing_country']}")
                print(f"    Expires: {cred['expiry_date']}, Status: {cred['status']}")

        elif args.mode == "interactive":
            # Interactive mode
            print("\nISO 18013-5 Reference Holder (Wallet)")
            print(f"Holder ID: {config.holder_id}")
            print(f"Wallet: {config.wallet_name}")
            print(f"Consent Level: {config.consent_level.value}")
            print(f"Credentials: {len(holder.credentials)}")
            print("\nCommands: qr, ble, nfc, credentials, history, quit")

            while True:
                try:
                    command = input("\n> ").strip().lower()

                    if command == "quit":
                        break
                    elif command == "qr":
                        qr_content = holder.generate_engagement_qr()
                        print(f"QR Code: {qr_content}")
                    elif command == "ble":
                        session_id = await holder.start_passive_mode("ble")
                        print(f"BLE advertising: {session_id}")
                    elif command == "nfc":
                        session_id = await holder.start_passive_mode("nfc")
                        print(f"NFC emulation: {session_id}")
                    elif command == "credentials":
                        credentials = holder.get_credentials_info()
                        print(f"Credentials ({len(credentials)}):")
                        for cred in credentials:
                            print(f"  {cred['document_type']}: {cred['holder_name']}")
                    elif command == "history":
                        history = holder.get_presentation_history()
                        print(f"Recent presentations ({len(history)}):")
                        for entry in history:
                            print(
                                f"  {entry['timestamp']}: {entry['reader_org']} ({entry['element_count']} elements)"
                            )
                    else:
                        print("Unknown command")

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Error: {e}")

    finally:
        await holder.stop_holder()


if __name__ == "__main__":
    asyncio.run(main())
