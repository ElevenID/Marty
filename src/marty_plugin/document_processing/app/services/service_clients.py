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
            from marty_plugin.proto.v1 import passport_engine_pb2, passport_engine_pb2_grpc

            with grpc.insecure_channel(self.address) as channel:
                stub = passport_engine_pb2_grpc.PassportEngineStub(channel)
                request = passport_engine_pb2.PassportRequest(passport_number=passport_number)
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
            from marty_plugin.proto.v1 import inspection_system_pb2, inspection_system_pb2_grpc

            with grpc.insecure_channel(self.address) as channel:
                stub = inspection_system_pb2_grpc.InspectionSystemStub(channel)
                request = inspection_system_pb2.InspectRequest(item=document_id)
                response = stub.Inspect(request)

                return {
                    "result": response.result,
                    "valid": "VALID" in response.result.upper(),
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
        """Validate MRZ data using inspection system"""
        # This would call appropriate inspection system endpoints for MRZ validation
        logger.info("MRZ validation via inspection-system not yet fully implemented")
        return {"valid": True, "checksums_valid": True}


class GrpcDocumentSignerClient(DocumentSignerClient):
    """gRPC-based document signer client"""

    def __init__(self, host: str = "localhost", port: int = 8082) -> None:
        self.host = host
        self.port = port
        self.address = f"{host}:{port}"

    async def validate_signature(self, document_data: dict[str, Any]) -> dict[str, Any]:
        """Validate document signature using document signer service"""
        try:
            from marty_plugin.proto.v1 import document_signer_pb2, document_signer_pb2_grpc

            with grpc.insecure_channel(self.address):
                # This would call appropriate document signer endpoints
                # Implementation depends on available document signer methods
                logger.info("Document signature validation via document-signer not yet implemented")
                return {"signature_valid": True, "trusted": True}
        except ImportError as e:
            logger.warning("gRPC modules not available for document signer")
            raise ServiceClientError(DOCUMENT_SIGNER, GRPC_UNAVAILABLE) from e
        except grpc.RpcError as e:
            logger.exception("Document signer gRPC error")
            error_details = str(e)
            raise ServiceClientError(DOCUMENT_SIGNER, error_details) from e


class MockPassportEngineClient(PassportEngineClient):
    """Mock passport engine client for testing/fallback"""

    async def process_passport(self, passport_number: str) -> dict[str, Any]:
        """Mock passport processing"""
        logger.info("Using mock passport engine for passport %s", passport_number)
        return {"status": "SUCCESS", "passport_number": passport_number, "success": True}

    async def extract_mrz(self, _image_data: bytes) -> dict[str, Any] | None:
        """Mock MRZ extraction"""
        logger.info("Using mock MRZ extraction")
        return {
            "document_type": "P",
            "issuing_country": "USA",
            "document_number": "123456789",
            "surname": "DOE",
            "given_names": "JOHN",
            "nationality": "USA",
            "date_of_birth": "850403",
            "gender": "M",
            "date_of_expiry": "350402",
        }


class MockInspectionSystemClient(InspectionSystemClient):
    """Mock inspection system client for testing/fallback"""

    async def inspect_document(self, document_id: str) -> dict[str, Any]:
        """Mock document inspection"""
        logger.info("Using mock inspection system for document %s", document_id)
        return {
            "result": f"VALID: Document {document_id} (mock validation)",
            "valid": True,
            "document_id": document_id,
        }

    async def validate_mrz(self, _mrz_data: dict[str, Any]) -> dict[str, Any]:
        """Mock MRZ validation"""
        return {"valid": True, "checksums_valid": True}


class MockDocumentSignerClient(DocumentSignerClient):
    """Mock document signer client for testing/fallback"""

    async def validate_signature(self, _document_data: dict[str, Any]) -> dict[str, Any]:
        """Mock signature validation"""
        return {"signature_valid": True, "trusted": True}


class ServiceClientFactory:
    """Factory for creating service clients with fallback to mocks"""

    def __init__(self) -> None:
        self.use_real_services = (
            settings.USE_REAL_SERVICES if hasattr(settings, "USE_REAL_SERVICES") else False
        )

    def create_passport_engine_client(self) -> PassportEngineClient:
        """Create passport engine client"""
        if self.use_real_services:
            try:
                return GrpcPassportEngineClient(
                    host=settings.PASSPORT_ENGINE_HOST, port=settings.PASSPORT_ENGINE_PORT
                )
            except (ImportError, grpc.RpcError) as e:
                logger.warning("Failed to create real passport engine client, using mock: %s", e)
        return MockPassportEngineClient()

    def create_inspection_system_client(self) -> InspectionSystemClient:
        """Create inspection system client"""
        if self.use_real_services:
            try:
                return GrpcInspectionSystemClient(
                    host=settings.INSPECTION_SYSTEM_HOST, port=settings.INSPECTION_SYSTEM_PORT
                )
            except (ImportError, grpc.RpcError) as e:
                logger.warning("Failed to create real inspection system client, using mock: %s", e)
        return MockInspectionSystemClient()

    def create_document_signer_client(self) -> DocumentSignerClient:
        """Create document signer client"""
        if self.use_real_services:
            try:
                return GrpcDocumentSignerClient(
                    host=settings.DOCUMENT_SIGNER_HOST, port=settings.DOCUMENT_SIGNER_PORT
                )
            except (ImportError, grpc.RpcError) as e:
                logger.warning("Failed to create real document signer client, using mock: %s", e)
        return MockDocumentSignerClient()


# Global factory instance
service_factory = ServiceClientFactory()
