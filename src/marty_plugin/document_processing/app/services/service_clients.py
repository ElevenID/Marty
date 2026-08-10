"""
Service client interfaces for Document Processing API

This module provides interfaces to existing Marty services to reduce code duplication
and make the document processor act as an orchestration layer.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import grpc
from app.core.config import settings

from marty_plugin.native_backends import require_backend

logger = logging.getLogger(__name__)

# Service names
PASSPORT_ENGINE = "passport-engine"
INSPECTION_SYSTEM = "inspection-system"
DOCUMENT_SIGNER = "document-signer"

# Error messages
GRPC_UNAVAILABLE = "gRPC modules not available"


class ServiceClientError(Exception):
    """Base exception for service client errors"""

    def __init__(self, service_name: str, details: str | None = None) -> None:
        self.service_name = service_name
        self.details = details
        message = f"{service_name} service error"
        if details:
            message += f": {details}"
        super().__init__(message)


class PassportEngineClient(ABC):
    """Interface for passport processing operations"""

    @abstractmethod
    async def process_passport(self, passport_number: str) -> dict[str, Any]:
        """Process a passport and return metadata"""

    @abstractmethod
    async def extract_mrz(self, image_data: bytes) -> dict[str, Any] | None:
        """Extract MRZ data from passport image"""


class InspectionSystemClient(ABC):
    """Interface for document inspection operations"""

    @abstractmethod
    async def inspect_document(self, document_id: str) -> dict[str, Any]:
        """Inspect document for authenticity and validity"""

    @abstractmethod
    async def validate_mrz(self, mrz_data: dict[str, Any]) -> dict[str, Any]:
        """Validate MRZ data integrity and checksums"""


class DocumentSignerClient(ABC):
    """Interface for document signing and trust validation"""

    @abstractmethod
    async def validate_signature(self, document_data: dict[str, Any]) -> dict[str, Any]:
        """Validate document signature against trust store"""


class GrpcPassportEngineClient(PassportEngineClient):
    """gRPC-based passport engine client"""

    def __init__(self, host: str = "localhost", port: int = 8084) -> None:
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"

    async def process_passport(self, passport_number: str) -> dict[str, Any]:
        """Process passport using passport-engine service"""
        try:
            # Import here to handle potential grpc import issues gracefully
            from marty_plugin.proto.v1 import (
                passport_engine_pb2,
                passport_engine_pb2_grpc,
            )

            with grpc.insecure_channel(self.address) as channel:
                stub = passport_engine_pb2_grpc.PassportEngineStub(channel)
                request = passport_engine_pb2.PassportRequest(
                    passport_number=passport_number
                )
                response = stub.ProcessPassport(request)

                return {
                    "status": response.status,
                    "passport_number": passport_number,
                    "success": response.status == "SUCCESS",
                }
        except ImportError as e:
            logger.warning("gRPC modules not available for passport engine")
            raise ServiceClientError(PASSPORT_ENGINE, GRPC_UNAVAILABLE) from e
        except grpc.RpcError as e:
            logger.exception("Passport engine gRPC error")
            error_details = str(e)
            raise ServiceClientError(PASSPORT_ENGINE, error_details) from e

    async def extract_mrz(self, image_data: bytes) -> dict[str, Any] | None:
        """Extract MRZ from image using passport engine OCR capabilities"""
        # This would be implemented when passport-engine supports OCR endpoints
        logger.info("MRZ extraction via passport-engine not yet implemented")
        return None


class GrpcInspectionSystemClient(InspectionSystemClient):
    """gRPC-based inspection system client"""

    def __init__(self, host: str = "localhost", port: int = 8083) -> None:
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"

    async def inspect_document(self, document_id: str) -> dict[str, Any]:
        """Inspect document using inspection-system service"""
        try:
            from marty_plugin.proto.v1 import (
                inspection_system_pb2,
                inspection_system_pb2_grpc,
            )

            with grpc.insecure_channel(self.address) as channel:
                stub = inspection_system_pb2_grpc.InspectionSystemStub(channel)
                request = inspection_system_pb2.InspectRequest(item=document_id)
                response = stub.Inspect(request)

                return {
                    "result": response.result,
                    "valid": response.result.strip().upper() == "VALID"
                    or response.result.strip().upper().startswith("VALID:"),
                    "document_id": document_id,
                }
        except ImportError as e:
            logger.warning("gRPC modules not available for inspection system")
            raise ServiceClientError(INSPECTION_SYSTEM, GRPC_UNAVAILABLE) from e
        except grpc.RpcError as e:
            logger.exception("Inspection system gRPC error")
            error_details = str(e)
            raise ServiceClientError(INSPECTION_SYSTEM, error_details) from e

    async def validate_mrz(self, mrz_data: dict[str, Any]) -> dict[str, Any]:
        """Validate OCR-produced MRZ lines with the native Rust parser."""
        native = require_backend("marty_verification")
        lines = mrz_data.get("mrzLines") or mrz_data.get("mrz_lines")
        if not isinstance(lines, list) or not all(
            isinstance(line, str) for line in lines
        ):
            return {
                "valid": False,
                "checksums_valid": False,
                "error_code": "MRZ_LINES_MISSING",
            }
        try:
            parsed = native.parse_mrz(lines)
        except Exception as exc:
            return {
                "valid": False,
                "checksums_valid": False,
                "error_code": "MRZ_INVALID",
                "error": str(exc),
            }
        return {
            "valid": True,
            "checksums_valid": True,
            "parsed": parsed.to_dict(),
        }


class GrpcDocumentSignerClient(DocumentSignerClient):
    """gRPC-based document signer client"""

    def __init__(self, host: str = "localhost", port: int = 8082) -> None:
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"

    async def validate_signature(self, document_data: dict[str, Any]) -> dict[str, Any]:
        """Reject the legacy unstructured signature request contract."""
        del document_data
        raise ServiceClientError(
            DOCUMENT_SIGNER,
            "structured native signature verification is required",
        )


class MockPassportEngineClient(PassportEngineClient):
    """Retired compatibility class that cannot produce verification results."""

    async def process_passport(self, passport_number: str) -> dict[str, Any]:
        del passport_number
        raise ServiceClientError(PASSPORT_ENGINE, "mock backend is disabled")

    async def extract_mrz(self, _image_data: bytes) -> dict[str, Any] | None:
        raise ServiceClientError(PASSPORT_ENGINE, "mock backend is disabled")


class MockInspectionSystemClient(InspectionSystemClient):
    """Retired compatibility class that always fails closed."""

    async def inspect_document(self, document_id: str) -> dict[str, Any]:
        del document_id
        raise ServiceClientError(INSPECTION_SYSTEM, "mock backend is disabled")

    async def validate_mrz(self, _mrz_data: dict[str, Any]) -> dict[str, Any]:
        del _mrz_data
        raise ServiceClientError(INSPECTION_SYSTEM, "mock backend is disabled")


class MockDocumentSignerClient(DocumentSignerClient):
    """Retired compatibility class that always fails closed."""

    async def validate_signature(
        self, _document_data: dict[str, Any]
    ) -> dict[str, Any]:
        del _document_data
        raise ServiceClientError(DOCUMENT_SIGNER, "mock backend is disabled")


class ServiceClientFactory:
    """Factory that never substitutes successful mock verification."""

    def __init__(self) -> None:
        self.use_real_services = (
            settings.USE_REAL_SERVICES
            if hasattr(settings, "USE_REAL_SERVICES")
            else False
        )

    def create_passport_engine_client(self) -> PassportEngineClient:
        """Create passport engine client"""
        if self.use_real_services:
            return GrpcPassportEngineClient(
                host=settings.PASSPORT_ENGINE_HOST, port=settings.PASSPORT_ENGINE_PORT
            )
        return MockPassportEngineClient()

    def create_inspection_system_client(self) -> InspectionSystemClient:
        """Create inspection system client"""
        if self.use_real_services:
            return GrpcInspectionSystemClient(
                host=settings.INSPECTION_SYSTEM_HOST,
                port=settings.INSPECTION_SYSTEM_PORT,
            )
        return MockInspectionSystemClient()

    def create_document_signer_client(self) -> DocumentSignerClient:
        """Create document signer client"""
        if self.use_real_services:
            return GrpcDocumentSignerClient(
                host=settings.DOCUMENT_SIGNER_HOST, port=settings.DOCUMENT_SIGNER_PORT
            )
        return MockDocumentSignerClient()


# Global factory instance
service_factory = ServiceClientFactory()
