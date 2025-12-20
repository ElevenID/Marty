"""
CMC (Crew Member Certificate) service client for Document Processing API

This module provides a client interface to the CMC Engine gRPC service,
allowing the FastAPI document processing service to interact with CMC operations.
"""

from __future__ import annotations

import logging
from typing import Any

import grpc

logger = logging.getLogger(__name__)


class CMCServiceError(Exception):
    """Exception raised for CMC service errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class CMCServiceClient:
    """Client for interacting with the CMC Engine gRPC service."""

    def __init__(self, host: str = "localhost", port: int = 8088) -> None:
        """Initialize CMC service client.

        Args:
            host: CMC engine service host
            port: CMC engine service port
        """
        self.address = f"{host}:{port}"
        self.timeout = 30.0  # 30 second timeout for gRPC calls

    async def create_cmc(self, cmc_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new CMC certificate.

        Args:
            cmc_data: CMC creation data

        Returns:
            Dictionary with creation result

        Raises:
            CMCServiceError: If CMC creation fails
        """
        try:
            # Import here to handle potential grpc import issues gracefully
            from marty_plugin.proto import cmc_engine_pb2, cmc_engine_pb2_grpc

            async with grpc.aio.insecure_channel(self.address) as channel:
                stub = cmc_engine_pb2_grpc.CMCEngineStub(channel)

                # Build the request
                request = cmc_engine_pb2.CreateCMCRequest(
                    document_number=cmc_data["document_number"],
                    issuing_country=cmc_data["issuing_country"],
                    surname=cmc_data["surname"],
                    given_names=cmc_data["given_names"],
                    nationality=cmc_data["nationality"],
                    date_of_birth=cmc_data["date_of_birth"],
                    gender=cmc_data["gender"],
                    date_of_expiry=cmc_data["date_of_expiry"],
                    employer=cmc_data.get("employer", ""),
                    crew_id=cmc_data.get("crew_id", ""),
                    security_model=getattr(
                        cmc_engine_pb2.CMCSecurityModel, cmc_data.get("security_model", "CHIP_LDS")
                    ),
                    face_image=cmc_data.get("face_image", b""),
                    background_check_verified=cmc_data.get("background_check_verified", False),
                )

                # Make the gRPC call
                response = await stub.CreateCMC(request, timeout=self.timeout)

                return {
                    "success": response.success,
                    "cmc_id": response.cmc_id if response.success else None,
                    "td1_mrz": response.td1_mrz if response.success else None,
                    "security_model": response.security_model if response.success else None,
                    "error_message": response.error_message if not response.success else None,
                }

        except ImportError as e:
            logger.warning("gRPC modules not available for CMC engine")
            msg = "CMC service not available"
            raise CMCServiceError(msg, {"grpc_error": str(e)}) from e
        except grpc.RpcError as e:
            logger.exception("CMC engine gRPC error")
            msg = f"CMC creation failed: {e.details()}"
            raise CMCServiceError(msg, {"grpc_code": e.code()}) from e
        except Exception as e:
            logger.exception("Unexpected error calling CMC service")
            msg = f"CMC creation failed: {e!s}"
            raise CMCServiceError(msg) from e

    async def sign_cmc(self, cmc_id: str, signer_id: str | None = None) -> dict[str, Any]:
        """Sign a CMC certificate.

        Args:
            cmc_id: CMC ID to sign
            signer_id: Signer identification

        Returns:
            Dictionary with signing result

        Raises:
            CMCServiceError: If CMC signing fails
        """
        try:
            from marty_plugin.proto import cmc_engine_pb2, cmc_engine_pb2_grpc

            async with grpc.aio.insecure_channel(self.address) as channel:
                stub = cmc_engine_pb2_grpc.CMCEngineStub(channel)

                request = cmc_engine_pb2.SignCMCRequest(
                    cmc_id=cmc_id, signer_id=signer_id or "document-signer-default"
                )

                response = await stub.SignCMC(request, timeout=self.timeout)

                return {
                    "success": response.success,
                    "signature_info": (
                        {
                            "signature_date": response.signature_info.signature_date,
                            "signer_id": response.signature_info.signer_id,
                            "algorithm": getattr(response.signature_info, "algorithm", "ES256"),
                        }
                        if response.success and response.signature_info
                        else None
                    ),
                    "error_message": response.error_message if not response.success else None,
                }

        except ImportError as e:
            logger.warning("gRPC modules not available for CMC engine")
            msg = "CMC service not available"
            raise CMCServiceError(msg, {"grpc_error": str(e)}) from e
        except grpc.RpcError as e:
            logger.exception("CMC engine gRPC error")
            msg = f"CMC signing failed: {e.details()}"
            raise CMCServiceError(msg, {"grpc_code": e.code()}) from e
        except Exception as e:
            logger.exception("Unexpected error calling CMC service")
            msg = f"CMC signing failed: {e!s}"
            raise CMCServiceError(msg) from e

    async def verify_cmc(self, verification_data: dict[str, Any]) -> dict[str, Any]:
        """Verify a CMC certificate.

        Args:
            verification_data: Verification request data

        Returns:
            Dictionary with verification result

        Raises:
            CMCServiceError: If CMC verification fails
        """
        try:
            from marty_plugin.proto import cmc_engine_pb2, cmc_engine_pb2_grpc

            async with grpc.aio.insecure_channel(self.address) as channel:
                stub = cmc_engine_pb2_grpc.CMCEngineStub(channel)

                # Build the request based on provided data
                request = cmc_engine_pb2.VerifyCMCRequest(
                    check_revocation=verification_data.get("check_revocation", True),
                    validate_background_check=verification_data.get(
                        "validate_background_check", True
                    ),
                )

                # Set the verification data (one of these must be provided)
                if "td1_mrz" in verification_data:
                    request.td1_mrz = verification_data["td1_mrz"]
                elif "barcode_data" in verification_data:
                    request.barcode_data = verification_data["barcode_data"]
                elif "cmc_id" in verification_data:
                    request.cmc_id = verification_data["cmc_id"]
                else:
                    msg = "One of td1_mrz, barcode_data, or cmc_id must be provided"
                    raise CMCServiceError(msg)

                response = await stub.VerifyCMC(request, timeout=self.timeout)

                # Convert verification results
                verification_results = []
                if response.verification_results:
                    verification_results = [
                        {
                            "check_name": result.check_name,
                            "passed": result.passed,
                            "details": result.details,
                            "error_code": getattr(result, "error_code", None),
                        }
                        for result in response.verification_results
                    ]

                return {
                    "success": response.success,
                    "is_valid": response.is_valid if response.success else False,
                    "cmc_data": (
                        self._convert_cmc_to_dict(response.cmc)
                        if response.success and response.cmc
                        else None
                    ),
                    "verification_results": verification_results,
                    "error_message": response.error_message if not response.success else None,
                }

        except ImportError as e:
            logger.warning("gRPC modules not available for CMC engine")
            msg = "CMC service not available"
            raise CMCServiceError(msg, {"grpc_error": str(e)}) from e
        except grpc.RpcError as e:
            logger.exception("CMC engine gRPC error")
            error_msg = f"CMC verification failed: {e.details()}"
            raise CMCServiceError(error_msg, {"grpc_code": e.code()}) from e
        except Exception as e:
            logger.exception("Unexpected error calling CMC service")
            error_msg = f"CMC verification failed: {e!s}"
            raise CMCServiceError(error_msg) from e

    async def background_check(
        self, cmc_id: str, check_authority: str, check_reference: str | None = None
    ) -> dict[str, Any]:
        """Initiate or check background verification for CMC.

        Args:
            cmc_id: CMC ID for background check
            check_authority: Authority performing the check
            check_reference: Reference number for the check

        Returns:
            Dictionary with background check result

        Raises:
            CMCServiceError: If background check operation fails
        """
        try:
            from marty_plugin.proto import cmc_engine_pb2, cmc_engine_pb2_grpc

            async with grpc.aio.insecure_channel(self.address) as channel:
                stub = cmc_engine_pb2_grpc.CMCEngineStub(channel)

                request = cmc_engine_pb2.BackgroundCheckRequest(
                    cmc_id=cmc_id,
                    check_authority=check_authority,
                    check_reference=check_reference or f"BGC-{cmc_id[:8]}",
                )

                response = await stub.CheckBackgroundVerification(request, timeout=self.timeout)

                return {
                    "success": response.success,
                    "check_passed": response.check_passed if response.success else False,
                    "check_date": response.check_date if response.success else None,
                    "check_authority": response.check_authority if response.success else None,
                    "check_reference": response.check_reference if response.success else None,
                    "error_message": response.error_message if not response.success else None,
                }

        except ImportError as e:
            logger.warning("gRPC modules not available for CMC engine")
            msg = "CMC service not available"
            raise CMCServiceError(msg, {"grpc_error": str(e)}) from e
        except grpc.RpcError as e:
            logger.exception("CMC engine gRPC error")
            msg = f"Background check failed: {e.details()}"
            raise CMCServiceError(msg, {"grpc_code": e.code()}) from e
        except Exception as e:
            logger.exception("Unexpected error calling CMC service")
            msg = f"Background check failed: {e!s}"
            raise CMCServiceError(msg) from e

    async def update_visa_free_status(
        self, cmc_id: str, visa_free_eligible: bool, authority: str, reason: str
    ) -> dict[str, Any]:
        """Update visa-free entry eligibility status.

        Args:
            cmc_id: CMC ID for status update
            visa_free_eligible: Visa-free entry eligibility
            authority: Authority granting/revoking status
            reason: Reason for status change

        Returns:
            Dictionary with visa-free status update result

        Raises:
            CMCServiceError: If visa-free status update fails
        """
        try:
            from marty_plugin.proto import cmc_engine_pb2, cmc_engine_pb2_grpc

            async with grpc.aio.insecure_channel(self.address) as channel:
                stub = cmc_engine_pb2_grpc.CMCEngineStub(channel)

                request = cmc_engine_pb2.VisaFreeStatusRequest(
                    cmc_id=cmc_id,
                    visa_free_eligible=visa_free_eligible,
                    authority=authority,
                    reason=reason,
                )

                response = await stub.UpdateVisaFreeStatus(request, timeout=self.timeout)

                return {
                    "success": response.success,
                    "visa_free_eligible": (
                        response.visa_free_eligible if response.success else False
                    ),
                    "updated_at": response.updated_at if response.success else None,
                    "error_message": response.error_message if not response.success else None,
                }

        except ImportError as e:
            logger.warning("gRPC modules not available for CMC engine")
            msg = "CMC service not available"
            raise CMCServiceError(msg, {"grpc_error": str(e)}) from e
        except grpc.RpcError as e:
            logger.exception("CMC engine gRPC error")
            msg = f"Visa-free status update failed: {e.details()}"
            raise CMCServiceError(msg, {"grpc_code": e.code()}) from e
        except Exception as e:
            logger.exception("Unexpected error calling CMC service")
            msg = f"Visa-free status update failed: {e!s}"
            raise CMCServiceError(msg) from e

    def _convert_cmc_to_dict(self, cmc_proto) -> dict[str, Any]:
        """Convert gRPC CMC response to dictionary.

        Args:
            cmc_proto: gRPC CMC certificate object

        Returns:
            Dictionary representation of CMC data
        """
        if not cmc_proto:
            return {}

        return {
            "cmc_id": getattr(cmc_proto, "cmc_id", ""),
            "document_number": (
                getattr(cmc_proto.cmc_data, "document_number", "")
                if hasattr(cmc_proto, "cmc_data")
                else ""
            ),
            "surname": (
                getattr(cmc_proto.cmc_data, "surname", "") if hasattr(cmc_proto, "cmc_data") else ""
            ),
            "given_names": (
                getattr(cmc_proto.cmc_data, "given_names", "")
                if hasattr(cmc_proto, "cmc_data")
                else ""
            ),
            "nationality": (
                getattr(cmc_proto.cmc_data, "nationality", "")
                if hasattr(cmc_proto, "cmc_data")
                else ""
            ),
            "security_model": (
                getattr(cmc_proto.cmc_data, "security_model", "")
                if hasattr(cmc_proto, "cmc_data")
                else ""
            ),
            "background_check_verified": (
                getattr(cmc_proto.cmc_data, "background_check_verified", False)
                if hasattr(cmc_proto, "cmc_data")
                else False
            ),
            "visa_free_entry_eligible": getattr(cmc_proto, "visa_free_entry_eligible", False),
            "td1_mrz": getattr(cmc_proto, "td1_mrz", ""),
        }


def get_cmc_service_client() -> CMCServiceClient:
    """Get CMC service client instance.

    Returns:
        CMC service client
    """
    # In a production environment, these would come from configuration
    host = "localhost"  # Could be from environment variable
    port = 8088  # CMC engine service port

    return CMCServiceClient(host=host, port=port)
