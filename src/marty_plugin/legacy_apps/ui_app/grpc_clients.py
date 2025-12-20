"""Utilities for creating gRPC stubs with graceful fallbacks."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import grpc

from marty_plugin.proto import (
    document_signer_pb2_grpc,
    inspection_system_pb2_grpc,
    passport_engine_pb2_grpc,
    trust_anchor_pb2_grpc,
)
from marty_plugin.proto.v1 import csca_service_pb2_grpc, pkd_service_pb2_grpc

try:
    from marty_plugin.proto.v1 import mdl_engine_pb2, mdl_engine_pb2_grpc
except ImportError:  # pragma: no cover - mdl proto optional in some deployments
    mdl_engine_pb2 = None  # type: ignore
    mdl_engine_pb2_grpc = None  # type: ignore

from .config import UiSettings


class GrpcClientFactory:
    """Factory for short-lived gRPC stubs.

    Channels are created per-call to avoid sharing across asyncio workers in the
    FastAPI app. For UI-triggered workflows the overhead is acceptable.
    """

    def __init__(self, settings: UiSettings) -> None:
        self._settings = settings

    @contextmanager
    def passport_engine(self) -> Iterator[passport_engine_pb2_grpc.PassportEngineStub]:
        channel = grpc.insecure_channel(self._settings.passport_engine_target)
        try:
            yield passport_engine_pb2_grpc.PassportEngineStub(channel)
        finally:
            channel.close()

    @contextmanager
    def inspection_system(self) -> Iterator[inspection_system_pb2_grpc.InspectionSystemStub]:
        channel = grpc.insecure_channel(self._settings.inspection_system_target)
        try:
            yield inspection_system_pb2_grpc.InspectionSystemStub(channel)
        finally:
            channel.close()

    @contextmanager
    def mdl_engine(self) -> Iterator[mdl_engine_pb2_grpc.MDLEngineStub | None]:
        if mdl_engine_pb2_grpc is None:
            yield None
            return
        channel = grpc.insecure_channel(self._settings.mdl_engine_target)
        try:
            yield mdl_engine_pb2_grpc.MDLEngineStub(channel)
        finally:
            channel.close()

    @contextmanager
    def trust_anchor(self) -> Iterator[trust_anchor_pb2_grpc.TrustAnchorStub]:
        channel = grpc.insecure_channel(self._settings.trust_anchor_target)
        try:
            yield trust_anchor_pb2_grpc.TrustAnchorStub(channel)
        finally:
            channel.close()

    @contextmanager
    def document_signer(self) -> Iterator[document_signer_pb2_grpc.DocumentSignerStub]:
        channel = grpc.insecure_channel(self._settings.document_signer_target)
        try:
            yield document_signer_pb2_grpc.DocumentSignerStub(channel)
        finally:
            channel.close()

    @contextmanager
    def csca_service(self) -> Iterator[csca_service_pb2_grpc.CscaServiceStub]:
        channel = grpc.insecure_channel(self._settings.csca_service_target)
        try:
            yield csca_service_pb2_grpc.CscaServiceStub(channel)
        finally:
            channel.close()

    @contextmanager
    def pkd_service(self) -> Iterator[pkd_service_pb2_grpc.PKDServiceStub]:
        channel = grpc.insecure_channel(self._settings.pkd_service_target)
        try:
            yield pkd_service_pb2_grpc.PKDServiceStub(channel)
        finally:
            channel.close()


__all__ = ["GrpcClientFactory"]
