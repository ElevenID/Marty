"""Conformance smoke tests for the native ISO 18013 Python boundary."""

from __future__ import annotations

import pytest

from marty_plugin.iso18013.protocols import (
    ISO18013_5Protocol,
    simulate_offline_transaction,
)
from marty_plugin.iso18013_bridge import (
    DeviceEngagement,
    MdlRequest,
    MdlResponse,
    NativeOperationError,
    ResponseStatus,
    Session,
    SessionConfig,
    SessionState,
    transport_capabilities,
)


def _engagement() -> DeviceEngagement:
    engagement = DeviceEngagement()
    engagement.add_ble_transport("0000FFF0-0000-1000-8000-00805F9B34FB")
    engagement.add_nfc_transport()
    return engagement


class TestISO18013Protocol:
    def test_device_engagement_and_qr_are_native_round_trippable(self) -> None:
        engagement = _engagement()
        encoded = engagement.to_bytes()

        assert DeviceEngagement.from_bytes(encoded).to_bytes() == encoded
        qr_png = engagement.to_qr_code()
        assert qr_png.startswith(b"\x89PNG\r\n\x1a\n")

    @pytest.mark.parametrize("malformed", (b"", b"bad", b"\xa1"))
    def test_malformed_cbor_fails_closed(self, malformed: bytes) -> None:
        with pytest.raises(NativeOperationError):
            DeviceEngagement.from_bytes(malformed)

    def test_request_and_response_round_trip_through_rust(self) -> None:
        request = MdlRequest(
            data_elements={"org.iso.18013.5.1": ["family_name", "age_over_21"]}
        )
        parsed_request = MdlRequest.from_bytes(request.to_bytes())
        assert parsed_request.doc_type == "org.iso.18013.5.1.mDL"
        assert parsed_request.data_elements == {
            "org.iso.18013.5.1": ["family_name", "age_over_21"]
        }
        assert parsed_request.nonce

        response = MdlResponse(
            "org.iso.18013.5.1.mDL", b"native-response", ResponseStatus.Ok
        )
        parsed_response = MdlResponse.from_bytes(response.to_bytes())
        assert parsed_response.data == b"native-response"
        assert parsed_response.status == ResponseStatus.Ok

    @pytest.mark.asyncio
    async def test_session_establishment_and_encrypted_exchange(self) -> None:
        reader = Session(_engagement())
        holder = Session(_engagement())
        reader_key = await reader.public_key()
        holder_key = await holder.public_key()

        await reader.establish(holder_key)
        await holder.establish(reader_key)
        assert await reader.state() == SessionState.Established
        assert await holder.state() == SessionState.Established

        ciphertext = await reader.send_encrypted(b"requested-elements")
        assert ciphertext != b"requested-elements"
        assert await holder.receive_encrypted(ciphertext) == b"requested-elements"

    @pytest.mark.asyncio
    async def test_replay_and_authentication_failures_are_rejected(self) -> None:
        sender = Session(_engagement())
        receiver = Session(_engagement())
        sender_key = await sender.public_key()
        receiver_key = await receiver.public_key()
        await sender.establish(receiver_key)
        await receiver.establish(sender_key)

        ciphertext = await sender.send_encrypted(b"one-time")
        assert await receiver.receive_encrypted(ciphertext) == b"one-time"
        with pytest.raises(NativeOperationError):
            await receiver.receive_encrypted(ciphertext)
        with pytest.raises(NativeOperationError):
            await sender.receive_encrypted(b"not-authenticated")

    @pytest.mark.asyncio
    async def test_oversized_messages_and_terminated_sessions_are_rejected(
        self,
    ) -> None:
        config = SessionConfig(max_message_size=4)
        sender = Session(_engagement(), config)
        receiver = Session(_engagement(), config)
        sender_key = await sender.public_key()
        receiver_key = await receiver.public_key()
        await sender.establish(receiver_key)
        await receiver.establish(sender_key)

        with pytest.raises(NativeOperationError, match="exceeds"):
            await sender.send_encrypted(b"oversized")
        await sender.terminate()
        assert await sender.state() == SessionState.Terminated
        with pytest.raises(NativeOperationError):
            await sender.send_encrypted(b"ok")


class TestISO18013Applications:
    def test_python_protocol_simulator_is_retired(self) -> None:
        with pytest.raises(NativeOperationError):
            ISO18013_5Protocol()

    @pytest.mark.asyncio
    async def test_simulated_transaction_is_retired(self) -> None:
        with pytest.raises(NativeOperationError):
            await simulate_offline_transaction()


class TestNativeTransports:
    def test_transport_capability_diagnostics_are_explicit(self) -> None:
        capabilities = transport_capabilities()
        assert set(capabilities) == {"ble", "nfc", "https"}
        assert all(isinstance(value, bool) for value in capabilities.values())
