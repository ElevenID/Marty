from __future__ import annotations

import os
from typing import Any

import grpc


class GRPCClient:
    """Minimal gRPC client helper used by tests.

    Only implements what `DTCEngineService` imports/uses: a `.stub` attribute
    constructed from a provided stub class and host/port from environment or
    passed configuration.
    """

    def __init__(self, service_name: str, stub_class: Any, config: Any | None = None) -> None:
        host = os.getenv(f"{service_name.replace('-', '_').upper()}_HOST", "localhost")
        port = os.getenv(f"{service_name.replace('-', '_').upper()}_PORT", "50051")
        address = f"{host}:{port}"
        channel = grpc.insecure_channel(address)
        self.stub = stub_class(channel)
