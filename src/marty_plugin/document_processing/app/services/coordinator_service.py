"""
Coordination service for document processing

This service acts as a coordinator that delegates work to specialized services
rather than doing heavy lifting itself.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.models.doc_models_clean import (
    CheckResult,
    Container,
    ContainerList,
    ContainerType,
    MRZResult,
    ProcessingStatus,
    ProcessRequest,
    ProcessResponse,
    RfidLocation,
    Status,
    TransactionInfo,
)
from app.services.service_clients import service_factory

logger = logging.getLogger(__name__)

# Error messages
UNSUPPORTED_SCENARIO_MSG = "Unsupported scenario"
NO_IMAGE_DATA_MSG = "No image data provided"
URI_NOT_IMPLEMENTED_MSG = "ImageUri processing not yet implemented"


class DocumentProcessingCoordinator:
    """Coordinates document processing by delegating to specialized services"""

    def __init__(self) -> None:
        # Initialize service clients via factory
        self.passport_engine = service_factory.create_passport_engine_client()
        self.inspection_system = service_factory.create_inspection_system_client()
        self.document_signer = service_factory.create_document_signer_client()

        logger.info("Document processing coordinator initialized")

    async def process_request(self, request: ProcessRequest) -> ProcessResponse:
        """Process a document processing request by coordinating services"""
        start_time = time.time()

        # Validate scenario
        if request.processParam.scenario not in settings.SUPPORTED_SCENARIOS:
            scenario = request.processParam.scenario
            error_msg = f"{UNSUPPORTED_SCENARIO_MSG}: {scenario}"
            raise ValueError(error_msg)

        # Generate transaction info
        transaction_info = self._create_transaction_info()

        # Process images
        containers = []
        for idx, image_request in enumerate(request.images):
            container = await self._process_single_image(image_request, idx)
            if container:
                containers.append(container)

        # Calculate elapsed time
        elapsed_time = int((time.time() - start_time) * 1000)  # Convert to milliseconds

        # Create container list
        container_list = ContainerList(Count=len(containers), List=containers)

        # Create and return response
        return ProcessResponse(
            transactionInfo=transaction_info,
            elapsedTime=elapsed_time,
            containerList=container_list,
            ChipPage=RfidLocation.NO_CHIP,
            CoreLibResultCode=0,
            ProcessingFinished=ProcessingStatus.FINISHED,
            morePagesAvailable=0,
            passBackObject=None,
            metadata={"processed_images": len(request.images), "orchestrated": True},
        )

    async def _process_single_image(self, image_request: Any, index: int) -> Container | None:
        """Process a single image using coordinated services"""
        try:
            # Extract image data
            if not image_request.ImageData:
                if image_request.ImageUri:
                    raise NotImplementedError(URI_NOT_IMPLEMENTED_MSG)
                raise ValueError(NO_IMAGE_DATA_MSG)

            # For now, use fallback MRZ extraction
            # Future enhancement: route to different engines based on document type
            mrz_result = await self._extract_mrz_generic(image_request.ImageData)

            # Validate MRZ if extracted
            if mrz_result:
                validation_result = await self.inspection_system.validate_mrz(
                    mrz_result.__dict__ if hasattr(mrz_result, "__dict__") else {}
                )
                logger.info("MRZ validation result: %s", validation_result)

            # Create status
            status = Status(
                overallStatus=CheckResult.POSITIVE if mrz_result else CheckResult.NEGATIVE,
                optical=CheckResult.POSITIVE if mrz_result else CheckResult.NEGATIVE,
                portrait=CheckResult.NOT_PERFORMED,
                rfid=CheckResult.NOT_PERFORMED,
                stopList=CheckResult.NOT_PERFORMED,
            )

            # Create and return container
            return Container(
                type=ContainerType.MRZ_CONTAINER,
                list_idx=index,
                page_idx=image_request.pageIdx or 0,
                light=getattr(image_request.light, "value", 1) if image_request.light else 1,
                result_type=1,  # MRZ result type
                Status=status,
                mrzResult=mrz_result,
            )

        except (ValueError, NotImplementedError):
            # Re-raise these specific exceptions
            raise
        except Exception:
            logger.exception("Error processing image %d", index)
            # Return error container
            status = Status(
                overallStatus=CheckResult.NEGATIVE,
                optical=CheckResult.NEGATIVE,
                portrait=CheckResult.NOT_PERFORMED,
                rfid=CheckResult.NOT_PERFORMED,
                stopList=CheckResult.NOT_PERFORMED,
            )

            return Container(
                type=ContainerType.MRZ_CONTAINER,
                list_idx=index,
                page_idx=image_request.pageIdx or 0,
                result_type=1,
                Status=status,
                mrzResult=None,
            )

    async def _extract_mrz_generic(self, image_data: str) -> MRZResult | None:
        """Extract MRZ using generic/fallback methods"""
        try:
            # Delegate to the original MRZ processing logic
            # This maintains backward compatibility while adding orchestration
            from .mrz_service import ImageProcessor, MRZProcessingService

            processor = ImageProcessor()
            image = processor.decode_base64_image(image_data)
            text_lines = processor.extract_text_from_image(image)

            if text_lines:
                service = MRZProcessingService()
                # Access the protected method for now - in the future this could be public
                return service._process_mrz_lines(text_lines)

        except ImportError:
            logger.warning("MRZ service not available for generic extraction")
        except Exception:
            logger.exception("Generic MRZ extraction failed")

        return None

    def _create_transaction_info(self) -> TransactionInfo:
        """Create transaction information"""
        return TransactionInfo(
            requestId=str(uuid4()),
            createdAt=datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            coreVersion=settings.CORE_VERSION,
            computerName="doc-processing-orchestrator",
            userName="doc-api",
        )


def request_looks_like_passport(image_request: Any) -> bool:
    """Heuristic to determine if image request looks like a passport"""
    # Simple heuristics - could be enhanced
    if hasattr(image_request, "metadata"):
        metadata = getattr(image_request, "metadata", {})
        if isinstance(metadata, dict):
            doc_type = metadata.get("document_type", "").lower()
            return "passport" in doc_type

    # Default to assuming it could be a passport
    return True
