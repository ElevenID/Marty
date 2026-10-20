"""
MDoc Engine service implementation.

This module provides the gRPC service for managing Mobile Documents (MDocs),
including creation, signing, and verification of digital documents.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

import grpc

from marty_common.native_backends import load_native_backend

from marty_plugin.proto import (
    document_signer_pb2,  # type: ignore
    mdoc_engine_pb2,  # type: ignore
    mdoc_engine_pb2_grpc,  # type: ignore
    document_signer_pb2_grpc,  # type: ignore
)

try:
    import qrcode  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    qrcode = None  # type: ignore

# Type aliases for better readability
MDocStore = dict[str, Any]  # Type for mdoc_engine_pb2.MDocResponse
DocumentSignerStub = Optional[Any]  # Type for document_signer_stub


class MDocEngineServicer(mdoc_engine_pb2_grpc.MDocEngineServicer):  # type: ignore
    """
    gRPC service for managing Mobile Documents (MDocs).

    This service handles the creation, signing, and management of digital documents
    that can be stored on mobile devices and verified remotely.
    """

    def __init__(self, channels: dict[str, Any] | None = None, *,
                 verification_keys: dict[str, tuple[str, bytes]] | None = None) -> None:
        """
        Initialize the MDoc Engine service.

        Args:
            channels: Optional dictionary of gRPC channels to other services.
        """
        self._mdoc_store: MDocStore = {}
        self.verification_keys = dict(verification_keys or {})
        if any(not isinstance(signer, str) or not signer or not isinstance(profile, tuple)
               or len(profile) != 2 or not isinstance(profile[0], str)
               or not isinstance(profile[1], bytes) or not profile[1]
               for signer, profile in self.verification_keys.items()):
            raise ValueError("mDoc verification requires signer-version ids and public SPKI profiles")
        self.channels = channels or {}
        self.document_signer_stub = self._document_signer_stub()

    def _document_signer_stub(self) -> DocumentSignerStub:
        """Get the document signer stub from channels."""
        channel = self.channels.get("document_signer")
        if channel is None:
            return None
        return document_signer_pb2_grpc.DocumentSignerStub(channel)

    async def CreateMDoc(self, request: Any, context: grpc.ServicerContext) -> Any:
        """
        Create a new Mobile Document (MDoc).

        Args:
            request: The create MDoc request containing document details
            context: gRPC service context

        Returns:
            CreateMDocResponse with the new MDoc ID and status
        """
        mdoc_id = str(uuid.uuid4())
        created_now = datetime.now().isoformat()

        mdoc_resp = mdoc_engine_pb2.MDocResponse(  # type: ignore
            mdoc_id=mdoc_id,
            document_type=request.document_type,
            document_number=request.document_number,
            issuing_authority=request.issuing_authority,
            issue_date=request.issue_date,
            expiry_date=request.expiry_date,
            person_info=request.person_info,
            document_fields=list(request.document_fields),
            images=list(request.images),
            signature_info=mdoc_engine_pb2.SignatureInfo(is_valid=False),  # type: ignore
            status="PENDING_SIGNATURE",
            created_at=created_now,
        )
        self._mdoc_store[mdoc_id] = mdoc_resp

        return mdoc_engine_pb2.CreateMDocResponse(  # type: ignore
            mdoc_id=mdoc_id, status="SUCCESS"
        )

    async def GetMDoc(self, request: Any, context: grpc.ServicerContext) -> Any:
        """
        Retrieve an existing Mobile Document (MDoc).

        Args:
            request: The get MDoc request containing the MDoc ID
            context: gRPC service context

        Returns:
            MDocResponse with the document data or error if not found
        """
        mdoc = self._mdoc_store.get(request.mdoc_id)
        if not mdoc:
            await context.abort(grpc.StatusCode.NOT_FOUND, "MDoc not found")
            return mdoc_engine_pb2.MDocResponse(  # type: ignore
                mdoc_id="", status="NOT_FOUND", error_message="MDoc not found"
            )
        return mdoc

    async def SignMDoc(self, request: Any, context: grpc.ServicerContext) -> Any:
        """
        Sign a Mobile Document (MDoc) using the document signing service.

        Args:
            request: The sign MDoc request containing the MDoc ID
            context: gRPC service context

        Returns:
            SignMDocResponse with signing status and signature information
        """
        mdoc = self._mdoc_store.get(request.mdoc_id)
        if not mdoc:
            await context.abort(grpc.StatusCode.NOT_FOUND, "MDoc not found for signing")
            return mdoc_engine_pb2.SignMDocResponse(  # type: ignore
                success=False, error_message="MDoc not found for signing"
            )

        if mdoc.status == "ACTIVE":
            return mdoc_engine_pb2.SignMDocResponse(  # type: ignore
                success=False,
                error_message="MDoc already signed",
                signature_info=mdoc.signature_info,
            )

        if not self.document_signer_stub:
            await context.abort(grpc.StatusCode.INTERNAL, "Document signing service not available")
            return mdoc_engine_pb2.SignMDocResponse(  # type: ignore
                success=False, error_message="Document signing service not available"
            )

        if not self.verification_keys:
            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
            context.set_details("Public signer verification profiles are required")
            return mdoc_engine_pb2.SignMDocResponse(success=False, error_message="Signer verification is not configured")

        content = self._signed_content(mdoc)
        try:
            response = await self.document_signer_stub.SignDocument(
                document_signer_pb2.SignRequest(document_id=mdoc.mdoc_id, document_content=content)
            )
        except grpc.RpcError as rpc_err:
            await context.abort(rpc_err.code(), "Document signer unavailable")
            return mdoc_engine_pb2.SignMDocResponse(success=False, error_message="Document signer unavailable")

        try:
            if (not isinstance(response, document_signer_pb2.SignResponse) or not response.success
                    or not response.HasField("signature_info")
                    or (response.HasField("error") and response.error.code != 0)):
                raise ValueError("Invalid signer response")
            signature = response.signature_info
            if not signature.signature or not signature.signer_id or not signature.signature_date:
                raise ValueError("Incomplete signer response")
            if datetime.fromisoformat(signature.signature_date).tzinfo is None:
                raise ValueError("Signer timestamp must include a timezone")
            if not self._verify_signature(signature, content):
                raise ValueError("Signature verification failed")
            if self._signed_content(mdoc) != content or mdoc.status == "ACTIVE":
                raise ValueError("Document changed during remote signing")
            new_signature = mdoc_engine_pb2.SignatureInfo(
                signature_date=signature.signature_date,
                signer_id=signature.signer_id,
                signature=signature.signature,
                is_valid=True,
            )
            # Commit the transition only after recording a verified signature succeeds.
            mdoc.signature_info.CopyFrom(new_signature)
        except Exception:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Document signer response could not be verified or recorded")
            return mdoc_engine_pb2.SignMDocResponse(success=False, error_message="Signature verification or recording failed")
        mdoc.status = "ACTIVE"
        return mdoc_engine_pb2.SignMDocResponse(success=True, signature_info=mdoc.signature_info)

    @staticmethod
    def _signed_content(mdoc) -> bytes:
        """Bind every document field, excluding derived signature/lifecycle state."""
        unsigned = mdoc_engine_pb2.MDocResponse()
        unsigned.CopyFrom(mdoc)
        unsigned.ClearField("signature_info")
        unsigned.ClearField("status")
        return unsigned.SerializeToString(deterministic=True)

    def _verify_signature(self, signature, content: bytes) -> bool:
        profile = self.verification_keys.get(signature.signer_id)
        if profile is None or not signature.signature:
            return False
        algorithm, public_spki = profile
        native = load_native_backend("marty_verification", ("verify_signature",))
        return native.verify_signature(algorithm, public_spki, content, signature.signature) is True

    async def GenerateMDocQRCode(self, request, context):
        mdoc = self._mdoc_store.get(request.mdoc_id)
        if not mdoc:
            await context.abort(grpc.StatusCode.NOT_FOUND, "MDoc not found")
            return mdoc_engine_pb2.GenerateQRCodeResponse(
                qr_code=b"", error_message="MDoc not found"
            )

        payload = {
            "mdoc_id": mdoc.mdoc_id,
            "document_type": mdoc.document_type,
            "created_at": mdoc.created_at,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
        except Exception as exc:  # pragma: no cover - exercised by tests
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error generating QR code: {exc}")
            return mdoc_engine_pb2.GenerateQRCodeResponse(
                qr_code=b"", error_message=f"Internal error: {exc}"
            )

        # If qrcode is available, generate real image, else return JSON bytes
        if qrcode is not None:
            img = qrcode.make(data)
            import io

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qr_bytes = buf.getvalue()
        else:
            qr_bytes = data

        return mdoc_engine_pb2.GenerateQRCodeResponse(qr_code=qr_bytes, error_message="")

    # Explicitly raise not implemented for methods referenced by tests
    async def TransferMDocToDevice(self, request, context):  # pragma: no cover
        """
        Transfer mDoc to a device.

        Args:
            request: The transfer request containing mDoc ID, device ID, and transfer method
            context: gRPC service context

        Returns:
            TransferMDocResponse indicating success or failure
        """
        mdoc = self._mdoc_store.get(request.mdoc_id)
        if not mdoc:
            await context.abort(grpc.StatusCode.NOT_FOUND, "MDoc not found for transfer")
            return mdoc_engine_pb2.TransferMDocResponse(
                success=False, error_message="MDoc not found for transfer"
            )

        if mdoc.status != "ACTIVE":
            return mdoc_engine_pb2.TransferMDocResponse(
                success=False, error_message="MDoc must be signed before transfer"
            )

        # Simulate successful transfer
        # In a real implementation, this would handle BLE, NFC, or other transfer methods
        return mdoc_engine_pb2.TransferMDocResponse(
            success=True,
            transfer_id=f"transfer_{request.mdoc_id}_{request.device_id}",
            error_message="",
        )

    async def VerifyMDoc(self, request, context):  # pragma: no cover
        """
        Verify an mDoc using either QR code data or direct mDoc ID.

        Args:
            request: The verify request containing QR code data or mDoc ID
            context: gRPC service context

        Returns:
            VerifyMDocResponse with verification results
        """
        mdoc = None

        # Handle verification by mDoc ID (oneof field)
        if hasattr(request, "mdoc_id") and request.mdoc_id:
            mdoc = self._mdoc_store.get(request.mdoc_id)

        # Handle verification by QR code data (would require parsing QR code)
        elif hasattr(request, "qr_code_data") and request.qr_code_data:
            # In a real implementation, we would parse the QR code to extract mDoc ID
            # For now, return a generic response
            return mdoc_engine_pb2.VerifyMDocResponse(
                is_valid=False, error_message="QR code verification not fully implemented"
            )

        if not mdoc:
            await context.abort(grpc.StatusCode.NOT_FOUND, "MDoc not found for verification")
            return mdoc_engine_pb2.VerifyMDocResponse(
                is_valid=False, error_message="MDoc not found for verification"
            )

        if mdoc.status != "ACTIVE":
            return mdoc_engine_pb2.VerifyMDocResponse(
                is_valid=False, error_message="MDoc is not signed/active"
            )

        # A stored flag never substitutes for verification of the current document.
        try:
            is_signature_valid = self._verify_signature(mdoc.signature_info, self._signed_content(mdoc))
        except Exception:
            is_signature_valid = False

        verified_document = mdoc_engine_pb2.MDocResponse()
        verified_document.CopyFrom(mdoc)
        verified_document.signature_info.is_valid = is_signature_valid
        return mdoc_engine_pb2.VerifyMDocResponse(
            is_valid=is_signature_valid, mdoc_data=verified_document, error_message=""
        )

    async def CreateDocumentTypeTemplate(self, request, context):  # pragma: no cover
        """
        Create a new document type template.

        Args:
            request: The template creation request
            context: gRPC service context

        Returns:
            CreateTemplateResponse with template information
        """
        # In a real implementation, this would store templates in a database
        template_id = f"template_{request.document_type}_{len(request.required_fields)}"

        # Simulate template creation
        return mdoc_engine_pb2.CreateTemplateResponse(
            template_id=template_id, success=True, error_message=""
        )

    async def GetDocumentTemplates(self, request, context):  # pragma: no cover
        """
        Get available document type templates.

        Args:
            request: The get templates request containing optional document type filter
            context: gRPC service context

        Returns:
            GetTemplatesResponse with available templates
        """
        # In a real implementation, this would query a database for templates
        mock_templates = [
            mdoc_engine_pb2.DocumentTemplate(
                template_id="template_id_card_basic",
                template_name="Basic ID Card",
                document_type="ID_CARD",
                required_fields=[
                    mdoc_engine_pb2.DocumentField(
                        field_name="full_name", namespace="identity", is_mandatory=True
                    ),
                    mdoc_engine_pb2.DocumentField(
                        field_name="date_of_birth", namespace="identity", is_mandatory=True
                    ),
                    mdoc_engine_pb2.DocumentField(
                        field_name="address", namespace="identity", is_mandatory=True
                    ),
                ],
                optional_fields=[
                    mdoc_engine_pb2.DocumentField(
                        field_name="middle_name", namespace="identity", is_mandatory=False
                    ),
                    mdoc_engine_pb2.DocumentField(
                        field_name="phone_number", namespace="contact", is_mandatory=False
                    ),
                ],
                required_images=["PORTRAIT"],
            ),
            mdoc_engine_pb2.DocumentTemplate(
                template_id="template_driver_license_standard",
                template_name="Standard Driver License",
                document_type="DRIVER_LICENSE",
                required_fields=[
                    mdoc_engine_pb2.DocumentField(
                        field_name="full_name", namespace="identity", is_mandatory=True
                    ),
                    mdoc_engine_pb2.DocumentField(
                        field_name="date_of_birth", namespace="identity", is_mandatory=True
                    ),
                    mdoc_engine_pb2.DocumentField(
                        field_name="license_number",
                        namespace="driving_privileges",
                        is_mandatory=True,
                    ),
                    mdoc_engine_pb2.DocumentField(
                        field_name="expiry_date", namespace="identity", is_mandatory=True
                    ),
                ],
                optional_fields=[
                    mdoc_engine_pb2.DocumentField(
                        field_name="restrictions",
                        namespace="driving_privileges",
                        is_mandatory=False,
                    ),
                    mdoc_engine_pb2.DocumentField(
                        field_name="endorsements",
                        namespace="driving_privileges",
                        is_mandatory=False,
                    ),
                ],
                required_images=["PORTRAIT", "SIGNATURE"],
            ),
        ]

        # Filter by document type if specified
        if request.document_type:
            mock_templates = [t for t in mock_templates if t.document_type == request.document_type]

        return mdoc_engine_pb2.GetTemplatesResponse(templates=mock_templates)
