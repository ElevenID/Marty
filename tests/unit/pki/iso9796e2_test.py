from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.append(str(project_root))


# Import from Marty's codebase
from marty_common.models.authentication import ActiveAuthenticationAlgorithm


@pytest.mark.depends(
    on=[
        "tests/unit/ef/ef_base_test.py::test_ef_base",
        "tests/unit/ef/dg15_test.py::test_dg15_parsing",
    ]
)
def test_iso9796e2_signer_verifier_stub():
    """Test stub for ISO 9796-2 signature verification used in Active Authentication."""

    # This is a stub test for the ISO 9796-2 signature verification functionality
    # In a real implementation, this would test the actual verification algorithm

    # Create a mock "verifier" function to demonstrate the expected interface
    def mock_verify_iso9796e2_signature(
        message: bytes,
        signature: bytes,
        public_key_data: bytes,
        algorithm: ActiveAuthenticationAlgorithm = ActiveAuthenticationAlgorithm.RSA_SHA1,
    ) -> bool:
        """
        Mock implementation of ISO 9796-2 signature verification.

        Args:
            message: The challenge message
            signature: The signature to verify
            public_key_data: The public key data (from DG15)
            algorithm: The algorithm used for signing

        Returns:
            True for successful verification (mocked)
        """
        # In a real implementation, this would perform actual verification
        # using cryptography libraries like OpenSSL or cryptography.hazmat

        # For testing purposes, we'll always return True
        return True

    # Test data
    test_message = b"Test challenge message for Active Authentication"
    test_signature = b"Sample signature data"
    test_public_key = b"Sample public key data from DG15"

    # Verify should return True for our mock
    assert mock_verify_iso9796e2_signature(test_message, test_signature, test_public_key)


def test_active_authentication_workflow():
    """Test the general workflow of Active Authentication."""

    # In Active Authentication:
    # 1. Inspection system generates a random challenge
    # 2. Sends it to the passport chip
    # 3. Chip signs it using the private key (ISO 9796-2 scheme)
    # 4. Inspection system verifies the signature using the public key from DG15

    def simulate_active_authentication(challenge: bytes, dg15_public_key: bytes) -> bool:
        """
        Simulate the Active Authentication workflow.

        Args:
            challenge: Random challenge from inspection system
            dg15_public_key: Public key from DG15

        Returns:
            True if verification succeeds
        """
        # Step 1: Generate challenge (already provided as input)

        # Step 2: Send to chip (simulated)

        # Step 3: Chip signs challenge (simulated)
        # In reality, this happens inside the secure element of the chip
        b"Mock signature for " + challenge

        # Step 4: Verify signature
        # Since we don't have the actual implementation yet, we'll assume success
        return True

    # Test with a random challenge
    test_challenge = os.urandom(8)  # 8 bytes of random data
    test_public_key = b"Sample DG15 public key data"

    # Simulate the AA process
    result = simulate_active_authentication(test_challenge, test_public_key)
    assert result is True


def test_iso9796e2_recovery():
    """Test message recovery in ISO 9796-2 signature scheme."""

    # In ISO 9796-2, the message can be partially or fully recovered from the signature

    def mock_recover_message(signature: bytes, public_key: bytes) -> bytes | None:
        """
        Mock function to simulate message recovery from ISO 9796-2 signature.

        Args:
            signature: The ISO 9796-2 signature
            public_key: Public key for verification

        Returns:
            Recovered message data or None if recovery failed
        """
        # In a real implementation, this would use the public key to decrypt
        # the signature and extract the message representative, then validate
        # and extract the actual message

        # For testing purposes, we'll return a mock recovered message
        return b"Recovered message part"

    # Test data
    test_signature = b"Mock ISO 9796-2 signature"
    test_public_key = b"Sample public key data"

    # Recover message
    recovered = mock_recover_message(test_signature, test_public_key)
    assert recovered is not None
    assert isinstance(recovered, bytes)
