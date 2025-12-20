"""
Modern Trust Anchor gRPC Service with Unified Observability.

This service demonstrates the unified observability patterns integrated
with gRPC service implementation using the new configuration system.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict

# Add project root to path for imports
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Modern framework imports
from framework.grpc.unified_grpc_server import (
    UnifiedGrpcServer,
    ObservableGrpcServiceMixin
)
from framework.config_factory import create_service_config
from framework.observability.unified_observability import (
    MartyMetrics,
    trace_grpc_method
)

# gRPC imports
import grpc
from grpc import aio

# Import gRPC generated modules  
from marty_plugin.proto.trust_anchor_pb2 import (
    CertificateInfo,
    ExpiringCertificate,
    ExpiryCheckResponse,
    MasterListResponse,
    ServiceStats,
    ServiceStatusResponse,
    SyncResponse,
    TrustResponse,
    UploadMasterListResponse,
    VerificationResponse,
)
from marty_plugin.proto.trust_anchor_pb2_grpc import TrustAnchorServicer, add_TrustAnchorServicer_to_server


class ObservableTrustAnchorService(TrustAnchorServicer, ObservableGrpcServiceMixin):
    """
    Modern Trust Anchor gRPC service with unified observability.
    
    This service automatically includes metrics, tracing, and health checks
    through the ObservableGrpcServiceMixin.
    """
    
    def __init__(self, config_path: str = "config/services/trust_anchor.yaml"):
        """Initialize with unified configuration."""
        super().__init__()
        
        self.logger = logging.getLogger("marty.trust_anchor.grpc")
        
        # Load unified configuration
        self.config = create_service_config(config_path)
        
        # Business metrics will be set up by the mixin
        self.trust_metrics = {}
        
        self.logger.info("Observable Trust Anchor service initialized")
    
    def _setup_observability(self, config):
        """Override to add trust-specific metrics."""
        super()._setup_observability(config)
        
        # Setup trust-specific business metrics
        self.trust_metrics = MartyMetrics.certificate_validation_metrics(self.observability)
        self.pkd_metrics = MartyMetrics.pkd_sync_metrics(self.observability)
        
        # Register trust-specific health checks
        self._register_trust_health_checks()
        
        self.logger.info("Trust Anchor observability configured")
    
    def _register_trust_health_checks(self):
        """Register trust-specific health checks."""
        if self.observability:
            # Trust store health check
            self.observability.register_health_check(
                name="trust_store",
                check_func=self._check_trust_store_health,
                interval_seconds=60
            )
            
            # PKD connectivity health check
            self.observability.register_health_check(
                name="pkd_connectivity",
                check_func=self._check_pkd_health,
                interval_seconds=120
            )
    
    async def _check_trust_store_health(self):
        """Check trust store accessibility."""
        from framework.observability.monitoring import HealthStatus
        
        try:
            # Check if trust store path is accessible
            trust_config = self.config.trust_store.trust_anchor
            store_path = Path(trust_config.certificate_store_path)
            
            if store_path.exists() and store_path.is_dir():
                return HealthStatus.HEALTHY
            else:
                return HealthStatus.DEGRADED
                
        except Exception:
            return HealthStatus.UNHEALTHY
    
    async def _check_pkd_health(self):
        """Check PKD service connectivity."""
        from framework.observability.monitoring import HealthStatus
        
        try:
            pkd_config = self.config.trust_store.pkd
            if not pkd_config.enabled:
                return HealthStatus.HEALTHY  # PKD disabled is OK
            
            # In a real implementation, would test connectivity to PKD service
            # For now, return healthy as placeholder
            return HealthStatus.HEALTHY
            
        except Exception:
            return HealthStatus.DEGRADED
    
    # gRPC Service Methods with Observability
    
    @trace_grpc_method
    async def VerifyCertificate(self, request, context) -> VerificationResponse:
        """Verify a certificate using the trust store."""
        method_trace = self.trace_grpc_call("VerifyCertificate")
        
        @method_trace
        async def _verify_impl(request, context):
            self.logger.info("Certificate verification request: %s", request.certificate_id)
            
            try:
                # Extract certificate information for metrics
                cert_id = request.certificate_id
                cert_type = getattr(request, 'certificate_type', 'unknown')
                
                # Simulate certificate verification
                # In real implementation, this would use trust store validation
                is_valid = True  # Placeholder
                
                # Record business metrics
                result = "success" if is_valid else "failure"
                self.trust_metrics["validations_total"].labels(
                    result=result,
                    certificate_type=cert_type,
                    issuer_country="unknown"  # Would extract from certificate
                ).inc()
                
                # Record validation duration (would measure actual time)
                self.trust_metrics["validation_duration"].labels(
                    certificate_type=cert_type
                ).observe(0.05)  # Placeholder duration
                
                return VerificationResponse(
                    is_valid=is_valid,
                    certificate_id=cert_id,
                    message="Certificate verified successfully" if is_valid else "Certificate invalid"
                )
                
            except Exception as e:
                self.logger.error("Certificate verification failed: %s", e)
                
                # Record error metrics
                self.trust_metrics["validations_total"].labels(
                    result="error",
                    certificate_type="unknown",
                    issuer_country="unknown"
                ).inc()
                
                context.set_details(str(e))
                context.set_code(grpc.StatusCode.INTERNAL)
                return VerificationResponse(is_valid=False, message=str(e))
        
        return await _verify_impl(request, context)
    
    @trace_grpc_method
    async def GetTrustStore(self, request, context) -> TrustResponse:
        """Get trust store information."""
        method_trace = self.trace_grpc_call("GetTrustStore")
        
        @method_trace
        async def _get_trust_store_impl(request, context):
            try:
                trust_anchor_config = self.config.trust_store.trust_anchor
                
                return TrustResponse(
                    store_path=trust_anchor_config.certificate_store_path,
                    last_update=0,  # Would get from actual trust store
                    certificate_count=0  # Would get from actual trust store
                )
                
            except Exception as e:
                self.logger.error("Failed to get trust store: %s", e)
                context.set_details(str(e))
                context.set_code(grpc.StatusCode.INTERNAL)
                return TrustResponse()
        
        return await _get_trust_store_impl(request, context)
    
    @trace_grpc_method
    async def SyncMasterList(self, request, context) -> SyncResponse:
        """Sync master list using PKD configuration."""
        method_trace = self.trace_grpc_call("SyncMasterList")
        
        @method_trace
        async def _sync_impl(request, context):
            try:
                pkd_config = self.config.trust_store.pkd
                
                if not pkd_config.enabled:
                    return SyncResponse(
                        success=False,
                        message="PKD synchronization is disabled in configuration"
                    )
                
                self.logger.info("Syncing master list from PKD: %s", pkd_config.service_url)
                
                # Simulate PKD sync operation
                records_updated = 42  # Placeholder
                
                # Record PKD sync metrics
                self.pkd_metrics["sync_operations"].labels(
                    result="success",
                    sync_type="master_list"
                ).inc()
                
                self.pkd_metrics["sync_duration"].labels(
                    sync_type="master_list"
                ).observe(5.2)  # Placeholder duration
                
                self.pkd_metrics["records_processed"].labels(
                    sync_type="master_list"
                ).observe(records_updated)
                
                return SyncResponse(
                    success=True,
                    message="Master list synchronized successfully",
                    records_updated=records_updated
                )
                
            except Exception as e:
                self.logger.error("Master list sync failed: %s", e)
                
                # Record error metrics
                self.pkd_metrics["sync_operations"].labels(
                    result="error",
                    sync_type="master_list"
                ).inc()
                
                context.set_details(str(e))
                context.set_code(grpc.StatusCode.INTERNAL)
                return SyncResponse(success=False, message=str(e))
        
        return await _sync_impl(request, context)
    
    @trace_grpc_method
    async def GetServiceStatus(self, request, context) -> ServiceStatusResponse:
        """Get service status with observability info."""
        method_trace = self.trace_grpc_call("GetServiceStatus")
        
        @method_trace 
        async def _status_impl(request, context):
            try:
                # Get health status from observability manager
                health_status = await self.observability.get_health_status()
                
                # Determine overall health
                is_healthy = all(
                    status.get("status") in ["healthy", "HEALTHY"]
                    for status in health_status.values()
                )
                
                service_discovery = self.config.service_discovery
                service_name = self.config.service_name.replace("-", "_")
                
                return ServiceStatusResponse(
                    is_healthy=is_healthy,
                    service_name="trust-anchor",
                    version="2.0.0-observable",
                    uptime_seconds=0,  # Would track actual uptime
                    host=service_discovery.hosts.get(service_name, "trust-anchor"),
                    port=service_discovery.ports.get(service_name, 8080),
                    health_checks=health_status
                )
                
            except Exception as e:
                self.logger.error("Failed to get service status: %s", e)
                context.set_details(str(e))
                context.set_code(grpc.StatusCode.INTERNAL)
                return ServiceStatusResponse(is_healthy=False, message=str(e))
        
        return await _status_impl(request, context)


async def main():
    """Main function using unified observability gRPC server."""
    import signal
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Get config path from command line or use default
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/services/trust_anchor.yaml"
    
    # Create unified gRPC server
    server = UnifiedGrpcServer(config_path=config_path)
    
    # Add the observable trust anchor servicer
    server.add_servicer(
        ObservableTrustAnchorService,
        add_TrustAnchorServicer_to_server,
        config_path
    )
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        asyncio.create_task(server.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start the server with unified observability
        await server.serve()
    except Exception as e:
        logging.error("Server error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())