"""Retained evidence orchestration uses an injected test provider, never local custody."""

import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from marty_common.crypto.evidence_signing import (
    EvidenceChain,
    EvidenceSigner,
    EvidenceVerifier,
    VerificationOutcome,
)
from marty_common.crypto.kms_provider import (
    KMSManager,
    KMSProvider,
    KMSProviderInterface,
    create_kms_manager,
)
from marty_common.native_backends import NativeOperationError


def _manager():
    # This double exercises orchestration only; provider custody is qualified elsewhere.
    state = {"fail": False, "calls": 0}

    async def sign(identity, data, algorithm):
        state["calls"] += 1
        await asyncio.sleep(0)
        if state["fail"]:
            raise RuntimeError("controlled provider failure")
        return hashlib.sha256(data).digest()

    async def public_key(identity):
        return b"test-public-key"

    provider = SimpleNamespace(
        provider_type=KMSProvider.HASHICORP_VAULT, sign=sign, get_public_key=public_key
    )
    return KMSManager(provider), state


async def _append(signer, subject="fixture"):
    return await signer.sign_verification_outcome(
        subject, "test-provider", VerificationOutcome.VALID, {"test": True}
    )


def test_local_provider_options_are_removed():
    import marty_common.crypto.kms_provider as module

    for name in ("SOFTWARE_HSM", "FILE_BASED"):
        assert not hasattr(KMSProvider, name)
    for name in ("SoftwareHSMProvider", "FileBasedProvider"):
        assert not hasattr(module, name)
    with pytest.raises(NativeOperationError, match="explicit managed provider identity"):
        create_kms_manager("software_hsm")


def test_manager_requires_explicit_remote_provider_identity():
    assert "provider_type" in KMSProviderInterface.__abstractmethods__
    for provider in (
        SimpleNamespace(),
        SimpleNamespace(provider_type="software_hsm"),
    ):
        with pytest.raises(
            NativeOperationError, match="explicit managed provider identity"
        ):
            KMSManager(provider)
    with pytest.raises(NotImplementedError, match="Managed adapter"):
        create_kms_manager(KMSProvider.AWS_KMS)


@pytest.mark.asyncio
async def test_two_entry_chain_preserves_signed_content_and_provider_audit_identity(monkeypatch):
    monkeypatch.setattr(
        "marty_common.crypto.evidence_signing.verify_signature",
        lambda data, signature, public_key, algorithm: signature == hashlib.sha256(data).digest(),
    )
    manager, state = _manager()
    signer = EvidenceSigner(manager, "test-service")
    first = await _append(signer, "first")
    second = await _append(signer, "second")
    assert first.evidence.metadata.chain_hash is None
    assert second.evidence.metadata.chain_hash == first.evidence_hash
    assert signer.evidence_chain.verify_chain_integrity()
    assert await signer.verify_evidence_signature(second)
    assert await EvidenceVerifier(manager).verify_evidence_chain(
        signer.evidence_chain, expected_head_hash=signer.evidence_chain.head_hash
    )
    assert state["calls"] == 2
    assert {entry.provider for entry in manager.audit_logs} == {
        KMSProvider.HASHICORP_VAULT
    }
    second.evidence.details["test"] = False
    assert not signer.evidence_chain.verify_chain_integrity()
    assert not await signer.verify_evidence_signature(second)
    assert not await EvidenceVerifier(manager).verify_evidence(second)


@pytest.mark.asyncio
async def test_concurrent_append_binds_each_signed_predecessor(monkeypatch):
    monkeypatch.setattr(
        "marty_common.crypto.evidence_signing.verify_signature",
        lambda data, signature, public_key, algorithm: signature == hashlib.sha256(data).digest(),
    )
    manager, _ = _manager()
    signer = EvidenceSigner(manager, "concurrent-test")
    await asyncio.gather(*(_append(signer, str(i)) for i in range(4)))
    assert len(signer.evidence_chain.entries) == 4
    assert signer.evidence_chain.verify_chain_integrity()
    assert await EvidenceVerifier(manager).verify_evidence_chain(
        signer.evidence_chain, expected_head_hash=signer.evidence_chain.head_hash
    )


@pytest.mark.asyncio
async def test_provider_failure_does_not_advance_or_mutate_chain():
    manager, state = _manager()
    signer = EvidenceSigner(manager, "failure-test")
    first = await _append(signer)
    state["fail"] = True
    with pytest.raises(RuntimeError, match="controlled provider failure"):
        await _append(signer)
    assert signer.evidence_chain.entries == [first]
    assert signer.evidence_chain.head_hash == first.evidence_hash
    assert signer.evidence_chain.verify_chain_integrity()
    assert manager.audit_logs[-1].success is False
    state["fail"] = False
    await _append(signer)
    assert signer.evidence_chain.verify_chain_integrity()


@pytest.mark.asyncio
async def test_invalid_append_and_truncation_cannot_report_an_intact_chain():
    manager, _ = _manager()
    signer = EvidenceSigner(manager)
    first = await _append(signer)
    second = await _append(signer)
    authenticated_head = signer.evidence_chain.head_hash
    assert authenticated_head == second.evidence_hash
    assert json.loads(signer.export_evidence_chain())["chain_metadata"]["head_hash"] == authenticated_head
    invalid = copy.deepcopy(second)
    invalid.evidence.metadata.chain_hash = "wrong-predecessor"
    with pytest.raises(ValueError, match="predecessor"):
        signer.evidence_chain.add_evidence(invalid)
    assert signer.evidence_chain.entries == [first, second]
    signer.evidence_chain.entries.pop()
    assert not signer.evidence_chain.verify_chain_integrity()
    reconstructed_prefix = EvidenceChain()
    reconstructed_prefix.add_evidence(first)
    assert reconstructed_prefix.verify_chain_integrity()
    assert not await EvidenceVerifier(manager).verify_evidence_chain(
        reconstructed_prefix, expected_head_hash=authenticated_head
    )
