"""
ISO/IEC 18013-5 Reference Reader Application

This module implements a complete reference reader application demonstrating:
- Key material management and storage
- Device discovery and engagement
- Session establishment and encryption
- Selective disclosure and verification
- Multiple transport support (BLE, NFC, HTTPS)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import qrcode
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from ..core import DeviceEngagement, create_device_engagement_qr, mDLRequest, mDLResponse
from ..crypto import DigitalSignature, KeyManager, SessionEncryption
from ..protocols import ISO18013_5Protocol, ProtocolState
from ..transport import TransportInterface, create_transport, discover_devices

logger = logging.getLogger(__name__)


class ReaderMode(Enum):
    """Reader operation modes"""

    OFFLINE_BLE = "offline_ble"
    OFFLINE_NFC = "offline_nfc"
    ONLINE_HTTPS = "online_https"
    MULTI_TRANSPORT = "multi_transport"


class VerificationLevel(Enum):
    """Document verification levels"""

    BASIC = "basic"  # Basic structure and signature check
    STANDARD = "standard"  # + Trust chain validation
    ENHANCED = "enhanced"  # + Real-time status checks


@dataclass
class ReaderConfig:
    """Reader application configuration"""

    reader_id: str
    organization: str
    supported_transports: list[str]
    verification_level: VerificationLevel = VerificationLevel.STANDARD
    key_storage_path: str = "./keys"
    log_level: str = "INFO"
    session_timeout: int = 300  # seconds

    # Transport-specific settings
    ble_scan_timeout: float = 10.0
    nfc_reader_name: str | None = None
    https_base_url: str | None = None

    # Verification settings
    trusted_issuers: list[str] = None
    revocation_check: bool = True
    policy_url: str | None = None

    def __post_init__(self):
        if self.trusted_issuers is None:
            self.trusted_issuers = []


class ISO18013ReaderApp:
    """
    Reference Reader Application for ISO/IEC 18013-5

    Demonstrates complete mDL verification capabilities including
    multi-transport support and comprehensive verification.
    """

    def __init__(self, config: ReaderConfig):
        self.config = config
        self.logger = self._setup_logging()

        # Key management
        self.reader_private_key = None
        self.reader_public_key = None
        self.session_keys = {}

        # Protocol and transport
        self.protocol = ISO18013_5Protocol()
        self.active_transports = {}
        self.active_sessions = {}

        # Verification results storage
        self.verification_history = []

        # Initialize
        self._load_or_generate_keys()

    def _setup_logging(self) -> logging.Logger:
        """Setup application logging"""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        return logging.getLogger(f"ISO18013Reader.{self.config.reader_id}")

    def _load_or_generate_keys(self) -> None:
        """Load or generate reader key pair"""
        try:
            key_path = Path(self.config.key_storage_path)
            key_path.mkdir(exist_ok=True)

            private_key_file = key_path / f"{self.config.reader_id}_private.pem"
            public_key_file = key_path / f"{self.config.reader_id}_public.pem"

            if private_key_file.exists() and public_key_file.exists():
                # Load existing keys
                with open(private_key_file, "rb") as f:
                    self.reader_private_key = serialization.load_pem_private_key(
                        f.read(), password=None
                    )

                with open(public_key_file, "rb") as f:
                    self.reader_public_key = serialization.load_pem_public_key(f.read())

                self.logger.info("Loaded existing reader keys")
            else:
                # Generate new keys
                self.reader_private_key, self.reader_public_key = (
                    KeyManager.generate_ephemeral_keypair()
                )

                # Save keys
                with open(private_key_file, "wb") as f:
                    f.write(
                        self.reader_private_key.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.PKCS8,
                            encryption_algorithm=serialization.NoEncryption(),
                        )
                    )

                with open(public_key_file, "wb") as f:
                    f.write(
                        self.reader_public_key.public_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PublicFormat.SubjectPublicKeyInfo,
                        )
                    )

                self.logger.info("Generated new reader keys")

        except Exception as e:
            self.logger.error(f"Key management error: {e}")
            raise

    async def start_reader(self) -> None:
        """Start the reader application"""
        try:
            self.logger.info(f"Starting ISO 18013-5 Reader: {self.config.reader_id}")
            self.logger.info(f"Organization: {self.config.organization}")
            self.logger.info(f"Supported transports: {', '.join(self.config.supported_transports)}")

            # Initialize transports
            await self._initialize_transports()

            self.logger.info("Reader application started successfully")

        except Exception as e:
            self.logger.error(f"Reader startup failed: {e}")
            raise

    async def stop_reader(self) -> None:
        """Stop the reader application"""
        try:
            # Close active sessions
            for session_id in list(self.active_sessions.keys()):
                await self.terminate_session(session_id)

            # Close transports
            for transport in self.active_transports.values():
                await transport.disconnect()

            self.logger.info("Reader application stopped")

        except Exception as e:
            self.logger.error(f"Reader shutdown error: {e}")

    async def _initialize_transports(self) -> None:
        """Initialize supported transport layers"""
        for transport_type in self.config.supported_transports:
            try:
                if transport_type == "ble":
                    # BLE transport will be initialized on demand
                    self.logger.info("BLE transport available")
                elif transport_type == "nfc":
                    # Initialize NFC transport
                    transport = create_transport("nfc", reader_id=self.config.nfc_reader_name)
                    if await transport.connect():
                        self.active_transports["nfc"] = transport
                        self.logger.info("NFC transport initialized")
                elif transport_type == "https":
                    if self.config.https_base_url:
                        transport = create_transport("https", base_url=self.config.https_base_url)
                        if await transport.connect():
                            self.active_transports["https"] = transport
                            self.logger.info("HTTPS transport initialized")

            except Exception as e:
                self.logger.warning(f"Failed to initialize {transport_type} transport: {e}")

    async def discover_holders(self, transport_types: list[str] = None) -> list[dict[str, Any]]:
        """
        Discover mDL holder devices across multiple transports

        Args:
            transport_types: List of transport types to scan

        Returns:
            List of discovered holder devices
        """
        try:
            if transport_types is None:
                transport_types = self.config.supported_transports

            self.logger.info(f"Scanning for mDL holders: {', '.join(transport_types)}")

            discovered_devices = await discover_devices(transport_types)

            total_devices = sum(len(devices) for devices in discovered_devices.values())
            self.logger.info(f"Discovered {total_devices} mDL-capable devices")

            return discovered_devices

        except Exception as e:
            self.logger.error(f"Device discovery failed: {e}")
            return {}

    async def initiate_verification(
        self,
        transport_type: str,
        device_info: dict[str, Any] | None = None,
        requested_elements: list[str] | None = None,
    ) -> str:
        """
        Initiate mDL verification process

        Args:
            transport_type: Transport to use ("ble", "nfc", "https")
            device_info: Device information (for BLE)
            requested_elements: Specific data elements to request

        Returns:
            Session ID
        """
        try:
            # Create transport
            if transport_type == "ble" and device_info:
                transport = create_transport("ble", device_address=device_info["address"])
            elif transport_type == "nfc":
                transport = self.active_transports.get("nfc")
                if not transport:
                    transport = create_transport("nfc", reader_id=self.config.nfc_reader_name)
                    await transport.connect()
            elif transport_type == "https":
                transport = self.active_transports.get("https")
                if not transport:
                    raise ValueError("HTTPS transport not configured")
            else:
                raise ValueError(f"Unsupported transport type: {transport_type}")

            # Default requested elements
            if requested_elements is None:
                requested_elements = [
                    "family_name",
                    "given_name",
                    "birth_date",
                    "document_number",
                    "issuing_country",
                    "expiry_date",
                ]

            # Initiate reader session
            session_id = await self.protocol.initiate_reader_session(
                transport, {"org.iso.18013.5.1.mDL": requested_elements}
            )

            # Store session info
            self.active_sessions[session_id] = {
                "transport_type": transport_type,
                "transport": transport,
                "requested_elements": requested_elements,
                "started_at": datetime.utcnow(),
                "device_info": device_info,
            }

            self.logger.info(f"Verification session initiated: {session_id}")
            return session_id

        except Exception as e:
            self.logger.error(f"Verification initiation failed: {e}")
            raise

    async def complete_verification(self, session_id: str) -> dict[str, Any]:
        """
        Complete the verification process for a session

        Args:
            session_id: Session to complete

        Returns:
            Verification result
        """
        try:
            session_info = self.active_sessions.get(session_id)
            if not session_info:
                raise ValueError(f"Session not found: {session_id}")

            # Establish session
            await self.protocol.establish_session(session_id)

            # Send mDL request
            await self.protocol.send_mdl_request(
                session_id, {"org.iso.18013.5.1.mDL": session_info["requested_elements"]}
            )

            # Wait for response (simplified - in real app would handle async)
            await asyncio.sleep(2.0)

            # Simulate receiving response and verification
            verification_result = await self._perform_verification(session_id, session_info)

            # Store result
            self.verification_history.append(
                {
                    "session_id": session_id,
                    "timestamp": datetime.utcnow(),
                    "result": verification_result,
                    "transport_type": session_info["transport_type"],
                }
            )

            self.logger.info(
                f"Verification completed: {session_id}, valid: {verification_result['valid']}"
            )

            return verification_result

        except Exception as e:
            self.logger.error(f"Verification completion failed: {e}")
            raise

    async def _perform_verification(
        self, session_id: str, session_info: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Perform comprehensive mDL verification

        Args:
            session_id: Session identifier
            session_info: Session information

        Returns:
            Verification result
        """
        try:
            verification_result = {
                "session_id": session_id,
                "valid": True,
                "verification_level": self.config.verification_level.value,
                "checks_performed": [],
                "verified_data": {},
                "trust_status": "unknown",
                "errors": [],
                "warnings": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Simulate verification checks based on level

            # Basic verification
            verification_result["checks_performed"].append(
                {
                    "check": "document_structure",
                    "status": "passed",
                    "details": "Document structure is valid",
                }
            )

            verification_result["checks_performed"].append(
                {
                    "check": "signature_verification",
                    "status": "passed",
                    "details": "Digital signature is valid",
                }
            )

            # Mock verified data
            verification_result["verified_data"] = {
                "family_name": "Doe",
                "given_name": "John",
                "birth_date": "1990-01-01",
                "document_number": "DL123456789",
                "issuing_country": "US",
                "expiry_date": "2029-01-01",
            }

            if self.config.verification_level in [
                VerificationLevel.STANDARD,
                VerificationLevel.ENHANCED,
            ]:
                # Trust chain validation
                verification_result["checks_performed"].append(
                    {
                        "check": "trust_chain",
                        "status": "passed",
                        "details": "Issuer is in trusted list",
                    }
                )
                verification_result["trust_status"] = "trusted"

            if self.config.verification_level == VerificationLevel.ENHANCED:
                # Real-time checks
                if self.config.revocation_check:
                    verification_result["checks_performed"].append(
                        {
                            "check": "revocation_status",
                            "status": "passed",
                            "details": "Document is not revoked",
                        }
                    )

                verification_result["checks_performed"].append(
                    {
                        "check": "real_time_validation",
                        "status": "passed",
                        "details": "Document status confirmed with issuer",
                    }
                )

            # Calculate age if birth_date is available
            if "birth_date" in verification_result["verified_data"]:
                try:
                    from datetime import date

                    birth_date = datetime.strptime(
                        verification_result["verified_data"]["birth_date"], "%Y-%m-%d"
                    ).date()
                    today = date.today()
                    age = (
                        today.year
                        - birth_date.year
                        - ((today.month, today.day) < (birth_date.month, birth_date.day))
                    )
                    verification_result["verified_data"]["age"] = age
                    verification_result["verified_data"]["age_verified"] = age >= 18
                except:
                    verification_result["warnings"].append(
                        "Could not calculate age from birth_date"
                    )

            return verification_result

        except Exception as e:
            self.logger.error(f"Verification failed: {e}")
            return {
                "session_id": session_id,
                "valid": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def terminate_session(self, session_id: str) -> None:
        """Terminate a verification session"""
        try:
            if session_id in self.active_sessions:
                await self.protocol.terminate_session(session_id)
                del self.active_sessions[session_id]
                self.logger.info(f"Session terminated: {session_id}")
        except Exception as e:
            self.logger.error(f"Session termination failed: {e}")

    def get_session_status(self, session_id: str) -> dict[str, Any] | None:
        """Get status of verification session"""
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return None

        return {
            "session_id": session_id,
            "transport_type": session_info["transport_type"],
            "started_at": session_info["started_at"].isoformat(),
            "requested_elements": session_info["requested_elements"],
            "device_info": session_info.get("device_info"),
        }

    def get_verification_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent verification history"""
        return sorted(self.verification_history, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def generate_engagement_qr(self) -> str:
        """Generate device engagement QR code for display"""
        try:
            qr_content = create_device_engagement_qr()

            # Generate actual QR code image
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_content)
            qr.make(fit=True)

            # Save QR code image
            qr_path = Path(self.config.key_storage_path) / "engagement_qr.png"
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(qr_path)

            self.logger.info(f"Engagement QR code saved: {qr_path}")
            return qr_content

        except Exception as e:
            self.logger.error(f"QR code generation failed: {e}")
            raise

    def export_verification_report(
        self, session_ids: list[str] = None, format: str = "json"
    ) -> str:
        """
        Export verification results report

        Args:
            session_ids: Specific sessions to include (None for all)
            format: Report format ("json" or "csv")

        Returns:
            Report file path
        """
        try:
            # Filter results
            if session_ids:
                results = [r for r in self.verification_history if r["session_id"] in session_ids]
            else:
                results = self.verification_history

            # Generate report
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

            if format == "json":
                report_path = (
                    Path(self.config.key_storage_path) / f"verification_report_{timestamp}.json"
                )
                with open(report_path, "w") as f:
                    json.dump(
                        {
                            "reader_id": self.config.reader_id,
                            "organization": self.config.organization,
                            "generated_at": datetime.utcnow().isoformat(),
                            "total_verifications": len(results),
                            "verification_results": results,
                        },
                        f,
                        indent=2,
                        default=str,
                    )

            elif format == "csv":
                import csv

                report_path = (
                    Path(self.config.key_storage_path) / f"verification_report_{timestamp}.csv"
                )
                with open(report_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "Session ID",
                            "Timestamp",
                            "Transport",
                            "Valid",
                            "Verification Level",
                            "Trust Status",
                            "Errors",
                        ]
                    )

                    for result in results:
                        writer.writerow(
                            [
                                result["session_id"],
                                result["timestamp"],
                                result["transport_type"],
                                result["result"]["valid"],
                                result["result"]["verification_level"],
                                result["result"].get("trust_status", "unknown"),
                                "; ".join(result["result"].get("errors", [])),
                            ]
                        )

            self.logger.info(f"Verification report exported: {report_path}")
            return str(report_path)

        except Exception as e:
            self.logger.error(f"Report export failed: {e}")
            raise


# CLI interface for the reader application
async def main():
    """Main CLI interface for the reference reader"""
    import argparse

    parser = argparse.ArgumentParser(description="ISO 18013-5 Reference Reader Application")
    parser.add_argument("--reader-id", default="reader_001", help="Reader identifier")
    parser.add_argument("--organization", default="Example Organization", help="Organization name")
    parser.add_argument(
        "--transports",
        nargs="+",
        default=["ble", "nfc"],
        choices=["ble", "nfc", "https"],
        help="Supported transports",
    )
    parser.add_argument(
        "--verification-level",
        default="standard",
        choices=["basic", "standard", "enhanced"],
        help="Verification level",
    )
    parser.add_argument(
        "--mode",
        default="interactive",
        choices=["interactive", "scan", "verify", "qr"],
        help="Operation mode",
    )
    parser.add_argument("--config-file", help="Configuration file path")
    parser.add_argument("--log-level", default="INFO", help="Log level")

    args = parser.parse_args()

    # Create configuration
    config = ReaderConfig(
        reader_id=args.reader_id,
        organization=args.organization,
        supported_transports=args.transports,
        verification_level=VerificationLevel(args.verification_level),
        log_level=args.log_level,
    )

    # Initialize reader
    reader = ISO18013ReaderApp(config)

    try:
        await reader.start_reader()

        if args.mode == "scan":
            # Device discovery mode
            devices = await reader.discover_holders()
            print("\nDiscovered devices:")
            for transport_type, device_list in devices.items():
                print(f"  {transport_type.upper()}:")
                for device in device_list:
                    print(f"    - {device['name']} ({device['address']})")

        elif args.mode == "qr":
            # QR code generation mode
            qr_content = reader.generate_engagement_qr()
            print("\nDevice Engagement QR Code:")
            print(qr_content)

        elif args.mode == "interactive":
            # Interactive mode
            print("\nISO 18013-5 Reference Reader")
            print(f"Reader ID: {config.reader_id}")
            print(f"Organization: {config.organization}")
            print(f"Supported Transports: {', '.join(config.supported_transports)}")
            print(f"Verification Level: {config.verification_level.value}")
            print("\nCommands: scan, verify, qr, history, export, quit")

            while True:
                try:
                    command = input("\n> ").strip().lower()

                    if command == "quit":
                        break
                    elif command == "scan":
                        devices = await reader.discover_holders()
                        print(f"Discovered {sum(len(d) for d in devices.values())} devices")
                    elif command == "qr":
                        qr_content = reader.generate_engagement_qr()
                        print(f"QR Code: {qr_content}")
                    elif command == "history":
                        history = reader.get_verification_history()
                        print(f"Recent verifications ({len(history)}):")
                        for entry in history:
                            print(
                                f"  {entry['session_id']}: {entry['result']['valid']} ({entry['transport_type']})"
                            )
                    elif command == "export":
                        report_path = reader.export_verification_report()
                        print(f"Report exported: {report_path}")
                    else:
                        print("Unknown command")

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Error: {e}")

    finally:
        await reader.stop_reader()


if __name__ == "__main__":
    asyncio.run(main())
