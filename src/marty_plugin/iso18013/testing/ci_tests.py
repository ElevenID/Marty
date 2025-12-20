"""
ISO/IEC 18013-5 Continuous Integration Test Suite

This module provides automated tests for CI/CD pipelines to validate
ISO 18013-5 protocol implementations across different scenarios.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ..apps.holder import ConsentLevel, HolderConfig, ISO18013HolderApp
from ..apps.reader import ISO18013ReaderApp, ReaderConfig, VerificationLevel
from ..core import DeviceEngagement, mDLRequest, mDLResponse
from ..protocols import ISO18013_5Protocol
from .test_vectors import MockmDLCredential, MockTransport, mDLSimulator, mDLTestVectorGenerator

logger = logging.getLogger(__name__)


class TestISO18013Protocol(unittest.TestCase):
    """Test ISO 18013-5 core protocol functionality"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.generator = mDLTestVectorGenerator(self.test_dir)
        self.simulator = mDLSimulator(self.test_dir)

        # Generate test vectors for testing
        self.generator.generate_all_vectors()
        self.simulator._load_test_vectors()

    def tearDown(self):
        """Clean up test environment"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_device_engagement_creation(self):
        """Test device engagement creation and QR generation"""
        # Test basic engagement
        engagement = DeviceEngagement(
            device_key=self.generator.holder_public_key,
            supported_transports=["ble", "nfc"],
            device_info={"name": "Test Wallet"},
        )

        # Verify structure
        self.assertIsNotNone(engagement.device_key)
        self.assertEqual(engagement.supported_transports, ["ble", "nfc"])
        self.assertEqual(engagement.device_info["name"], "Test Wallet")

        # Test CBOR encoding
        cbor_data = engagement.to_cbor()
        self.assertIsInstance(cbor_data, bytes)

        # Test QR content generation
        qr_content = engagement.to_qr_content()
        self.assertIsInstance(qr_content, str)
        self.assertTrue(qr_content.startswith("mdoc:"))

    def test_mdl_request_creation(self):
        """Test mDL request creation and validation"""
        request = mDLRequest(
            doc_requests={"org.iso.18013.5.1.mDL": ["family_name", "given_name", "birth_date"]},
            reader_auth={"reader_key": self.generator.reader_public_key, "reader_cert_chain": []},
        )

        # Verify structure
        self.assertIn("org.iso.18013.5.1.mDL", request.doc_requests)
        self.assertEqual(len(request.doc_requests["org.iso.18013.5.1.mDL"]), 3)
        self.assertIsNotNone(request.reader_auth["reader_key"])

        # Test CBOR encoding
        cbor_data = request.to_cbor()
        self.assertIsInstance(cbor_data, bytes)

    def test_mdl_response_creation(self):
        """Test mDL response creation with selective disclosure"""
        # Create test credential
        credential = MockmDLCredential()

        # Create response with selective elements
        elements = ["family_name", "given_name", "birth_date"]
        disclosed_data = credential.get_selective_disclosure(elements)

        response = mDLResponse(documents={"org.iso.18013.5.1.mDL": disclosed_data}, status="OK")

        # Verify structure
        self.assertEqual(response.status, "OK")
        self.assertIn("org.iso.18013.5.1.mDL", response.documents)

        # Verify selective disclosure
        disclosed = response.documents["org.iso.18013.5.1.mDL"]
        for element in elements:
            self.assertIn(element, disclosed)

        # Verify only requested elements are present
        self.assertEqual(len(disclosed), len(elements))

    def test_mock_transport_functionality(self):
        """Test mock transport for CI testing"""
        transport = MockTransport("test")

        # Test connection
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Test connect/disconnect
            connected = loop.run_until_complete(transport.connect())
            self.assertTrue(connected)
            self.assertTrue(transport.is_connected)

            # Test message sending
            test_message = b"test_message"
            sent = loop.run_until_complete(transport.send_message(test_message))
            self.assertTrue(sent)

            # Verify message in queue
            sent_messages = transport.get_sent_messages()
            self.assertEqual(len(sent_messages), 1)
            self.assertEqual(sent_messages[0]["message"], test_message)

            # Test response queuing and receiving
            response_message = b"response_message"
            transport.queue_response(response_message)

            received = loop.run_until_complete(transport.receive_message())
            self.assertEqual(received, response_message)

            # Test disconnect
            loop.run_until_complete(transport.disconnect())
            self.assertFalse(transport.is_connected)

        finally:
            loop.close()


class TestISO18013Applications(unittest.TestCase):
    """Test reader and holder reference applications"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()

        # Reader configuration
        self.reader_config = ReaderConfig(
            reader_id="test_reader",
            organization="Test Organization",
            supported_transports=["mock"],
            verification_level=VerificationLevel.BASIC,
            key_storage_path=os.path.join(self.test_dir, "reader_keys"),
        )

        # Holder configuration
        self.holder_config = HolderConfig(
            holder_id="test_holder",
            wallet_name="Test Wallet",
            consent_level=ConsentLevel.AUTOMATIC,
            key_storage_path=os.path.join(self.test_dir, "holder_keys"),
            credential_storage_path=os.path.join(self.test_dir, "credentials"),
        )

    def tearDown(self):
        """Clean up test environment"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_reader_app_initialization(self):
        """Test reader application initialization"""
        reader = ISO18013ReaderApp(self.reader_config)

        # Verify initialization
        self.assertEqual(reader.config.reader_id, "test_reader")
        self.assertIsNotNone(reader.reader_private_key)
        self.assertIsNotNone(reader.reader_public_key)
        self.assertEqual(len(reader.active_sessions), 0)

    def test_holder_app_initialization(self):
        """Test holder application initialization"""
        holder = ISO18013HolderApp(self.holder_config)

        # Verify initialization
        self.assertEqual(holder.config.holder_id, "test_holder")
        self.assertIsNotNone(holder.holder_private_key)
        self.assertIsNotNone(holder.holder_public_key)
        self.assertGreater(len(holder.credentials), 0)  # Demo credential should be created

    def test_qr_code_generation(self):
        """Test QR code generation by holder"""
        holder = ISO18013HolderApp(self.holder_config)

        # Generate QR code
        qr_content = holder.generate_engagement_qr()

        # Verify QR content
        self.assertIsInstance(qr_content, str)
        self.assertTrue(qr_content.startswith("mdoc:"))

        # Verify QR file was created
        qr_file = Path(holder.config.key_storage_path) / "device_engagement.png"
        self.assertTrue(qr_file.exists())

    @patch("src.iso18013.transport.create_transport")
    def test_reader_verification_flow(self, mock_create_transport):
        """Test complete reader verification flow"""
        # Setup mock transport
        mock_transport = MockTransport()
        mock_create_transport.return_value = mock_transport

        reader = ISO18013ReaderApp(self.reader_config)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Start reader
            loop.run_until_complete(reader.start_reader())

            # Initiate verification
            session_id = loop.run_until_complete(
                reader.initiate_verification(
                    "mock",
                    device_info={"address": "test_device"},
                    requested_elements=["family_name", "given_name"],
                )
            )

            # Verify session created
            self.assertIsNotNone(session_id)
            self.assertIn(session_id, reader.active_sessions)

            # Get session status
            status = reader.get_session_status(session_id)
            self.assertIsNotNone(status)
            self.assertEqual(status["transport_type"], "mock")

            # Stop reader
            loop.run_until_complete(reader.stop_reader())

        finally:
            loop.close()


class TestTestVectors(unittest.TestCase):
    """Test vector generation and validation"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.generator = mDLTestVectorGenerator(self.test_dir)

    def tearDown(self):
        """Clean up test environment"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_vector_generation(self):
        """Test test vector generation"""
        # Generate all vectors
        self.generator.generate_all_vectors()

        # Verify files were created
        expected_files = [
            "device_engagement.json",
            "mdl_requests.json",
            "mdl_responses.json",
            "qr_codes.json",
            "sessions.json",
            "complete_test_vectors.json",
            "test_summary.json",
        ]

        for filename in expected_files:
            file_path = Path(self.test_dir) / filename
            self.assertTrue(file_path.exists(), f"File not created: {filename}")

        # Verify content structure
        with open(Path(self.test_dir) / "test_summary.json") as f:
            summary = json.load(f)

        self.assertIn("test_vector_summary", summary)
        self.assertGreater(summary["test_vector_summary"]["total_files"], 0)

    def test_vector_content_validation(self):
        """Test generated vector content validation"""
        self.generator.generate_all_vectors()

        # Load and validate device engagement vectors
        with open(Path(self.test_dir) / "device_engagement.json") as f:
            engagement_vectors = json.load(f)

        self.assertIn("vectors", engagement_vectors)
        self.assertGreater(len(engagement_vectors["vectors"]), 0)

        # Validate first vector structure
        vector = engagement_vectors["vectors"][0]
        required_fields = [
            "name",
            "description",
            "engagement_cbor",
            "qr_content",
            "device_key_public",
            "expected_transports",
        ]

        for field in required_fields:
            self.assertIn(field, vector, f"Missing field: {field}")

    def test_mock_credential_creation(self):
        """Test mock credential creation"""
        credential = MockmDLCredential(
            document_number="TEST123", holder_name="John Test Doe", issuing_country="TS"
        )

        # Verify basic properties
        self.assertEqual(credential.document_number, "TEST123")
        self.assertEqual(credential.family_name, "John")
        self.assertEqual(credential.given_name, "Test Doe")
        self.assertEqual(credential.issuing_country, "TS")

        # Test CBOR conversion
        cbor_data = credential.to_cbor()
        self.assertIsInstance(cbor_data, dict)
        self.assertIn("family_name", cbor_data)
        self.assertIn("document_number", cbor_data)

        # Test selective disclosure
        elements = ["family_name", "birth_date"]
        disclosed = credential.get_selective_disclosure(elements)
        self.assertEqual(len(disclosed), 2)
        self.assertIn("family_name", disclosed)
        self.assertIn("birth_date", disclosed)


class TestSimulation(unittest.TestCase):
    """Test protocol simulation functionality"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.simulator = mDLSimulator(self.test_dir)

        # Generate test vectors for simulation
        generator = mDLTestVectorGenerator(self.test_dir)
        generator.generate_all_vectors()
        self.simulator._load_test_vectors()

    def tearDown(self):
        """Clean up test environment"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_ble_discovery_simulation(self):
        """Test BLE device discovery simulation"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            devices = loop.run_until_complete(self.simulator.simulate_ble_discovery())

            # Verify discovery results
            self.assertIsInstance(devices, list)
            self.assertGreater(len(devices), 0)

            # Verify device structure
            for device in devices:
                self.assertIn("name", device)
                self.assertIn("address", device)
                self.assertIn("mdl_capable", device)
                self.assertTrue(device["mdl_capable"])

        finally:
            loop.close()

    def test_nfc_detection_simulation(self):
        """Test NFC card detection simulation"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            card_info = loop.run_until_complete(self.simulator.simulate_nfc_detection())

            # Verify card info
            self.assertIsNotNone(card_info)
            self.assertIn("atr", card_info)
            self.assertIn("card_type", card_info)
            self.assertEqual(card_info["card_type"], "mDL")

        finally:
            loop.close()

    def test_qr_scan_simulation(self):
        """Test QR code scanning simulation"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            qr_content = loop.run_until_complete(self.simulator.simulate_qr_scan())

            # Verify QR content
            self.assertIsInstance(qr_content, str)
            self.assertTrue(qr_content.startswith("mdoc:"))

        finally:
            loop.close()

    def test_complete_transaction_simulation(self):
        """Test complete mDL transaction simulation"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                self.simulator.simulate_mdl_transaction(
                    transport_type="mock", requested_elements=["family_name", "birth_date"]
                )
            )

            # Verify transaction result
            self.assertIsInstance(result, dict)
            self.assertIn("transaction_id", result)
            self.assertIn("success", result)
            self.assertIn("steps", result)
            self.assertTrue(result["success"])

            # Verify transaction steps
            expected_steps = [
                "transport_connect",
                "device_engagement",
                "session_establishment",
                "mdl_request",
                "mdl_response",
                "verification",
            ]

            step_names = [step["step"] for step in result["steps"]]
            for expected_step in expected_steps:
                self.assertIn(expected_step, step_names)

        finally:
            loop.close()

    def test_scenario_execution(self):
        """Test predefined scenario execution"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(self.simulator.run_test_scenario("basic_verification"))

            # Verify scenario result
            self.assertIsInstance(result, dict)
            self.assertIn("scenario_name", result)
            self.assertIn("scenario_description", result)
            self.assertEqual(result["scenario_name"], "basic_verification")
            self.assertTrue(result["success"])

        finally:
            loop.close()


# Pytest fixtures for integration testing
@pytest.fixture
def test_environment():
    """Provide test environment with temporary directory"""
    test_dir = tempfile.mkdtemp()
    yield test_dir
    import shutil

    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def test_vectors(test_environment):
    """Generate and provide test vectors"""
    generator = mDLTestVectorGenerator(test_environment)
    generator.generate_all_vectors()
    return generator


@pytest.fixture
def simulator(test_environment):
    """Provide configured simulator"""
    return mDLSimulator(test_environment)


@pytest.fixture
def reader_app(test_environment):
    """Provide configured reader application"""
    config = ReaderConfig(
        reader_id="test_reader",
        organization="Test Org",
        supported_transports=["mock"],
        key_storage_path=os.path.join(test_environment, "reader_keys"),
    )
    return ISO18013ReaderApp(config)


@pytest.fixture
def holder_app(test_environment):
    """Provide configured holder application"""
    config = HolderConfig(
        holder_id="test_holder",
        consent_level=ConsentLevel.AUTOMATIC,
        key_storage_path=os.path.join(test_environment, "holder_keys"),
        credential_storage_path=os.path.join(test_environment, "credentials"),
    )
    return ISO18013HolderApp(config)


# Integration tests using pytest
@pytest.mark.asyncio
async def test_end_to_end_verification(reader_app, holder_app, simulator):
    """Test end-to-end verification flow"""
    # Start applications
    await reader_app.start_reader()
    await holder_app.start_holder()

    try:
        # Simulate device discovery
        devices = await simulator.simulate_ble_discovery()
        assert len(devices) > 0

        # Simulate QR scan
        qr_content = await simulator.simulate_qr_scan()
        assert qr_content.startswith("mdoc:")

        # Simulate transaction
        transaction = await simulator.simulate_mdl_transaction()
        assert transaction["success"]
        assert len(transaction["steps"]) == 6

    finally:
        await reader_app.stop_reader()
        await holder_app.stop_holder()


@pytest.mark.asyncio
async def test_protocol_compliance(test_vectors):
    """Test protocol compliance with test vectors"""
    # Load test vectors
    with open(Path(test_vectors.output_dir) / "complete_test_vectors.json") as f:
        vectors = json.load(f)

    # Test device engagement vectors
    for vector in vectors["device_engagement"]["vectors"]:
        assert "engagement_cbor" in vector
        assert "qr_content" in vector
        assert vector["qr_content"].startswith("mdoc:")

    # Test request vectors
    for vector in vectors["mdl_requests"]["vectors"]:
        assert "request_cbor" in vector
        assert "requested_elements" in vector
        assert len(vector["requested_elements"]) > 0

    # Test response vectors
    for vector in vectors["mdl_responses"]["vectors"]:
        assert "response_cbor" in vector
        assert "status" in vector


if __name__ == "__main__":
    # Run basic tests
    unittest.main(verbosity=2)
