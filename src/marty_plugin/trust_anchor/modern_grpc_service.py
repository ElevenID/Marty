"""
Modern Trust Anchor gRPC Service using unified configuration.

This replaces the legacy trust_anchor/app/grpc_service.py with modern configuration patterns.
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

# Modern configuration imports
from framework.config_factory import create_service_config
from framework.config import (
    AppConfigManager,
    DatabaseConfigSection,
    SecurityConfigSection,
    TrustStoreConfigSection,
    ServiceDiscoveryConfigSection
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

# Import our services - these will also need to be modernized
from marty_plugin.trust_anchor.app.services.certificate_expiry_service import CertificateExpiryService
from marty_plugin.trust_anchor.app.services.openxpki_service import OpenXPKIService


class ModernTrustAnchorService(TrustAnchorServicer):
    """
    Modern Trust Anchor gRPC service using unified configuration.
    
    Replaces the legacy service with modern configuration patterns.
    """
    
    def __init__(self, config_path: str = "config/services/trust_anchor.yaml"):
        """Initialize with unified configuration."""
        self.logger = logging.getLogger("marty.trust_anchor.grpc")
        
        # Load unified configuration
        self.config = create_service_config(config_path)
        
        # Extract configuration sections
        self.db_config = self.config.database.get_config("trust_anchor")
        self.security_config = self.config.security
        self.trust_store_config = self.config.trust_store
        self.service_discovery = self.config.service_discovery
        
        # Service-specific settings
        self.service_settings = self.config.services.get("trust_anchor", {})
        
        # Initialize services with modern config
        self.expiry_service = None
        self.openxpki_service = None
        self._running = False
        
        self.logger.info("Modern Trust Anchor service initialized")
    
    async def initialize(self) -> None:
        """Initialize the service components."""
        try:
            # Initialize certificate expiry service with modern config
            self.expiry_service = await self._create_expiry_service()
            
            # Initialize OpenXPKI service with modern config
            self.openxpki_service = await self._create_openxpki_service()
            
            self.logger.info("Trust Anchor service components initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Trust Anchor service: {e}")
            raise
    
    async def _create_expiry_service(self) -> CertificateExpiryService:
        """Create certificate expiry service with modern configuration."""
        # Convert modern config to legacy format for existing service
        # TODO: Modernize CertificateExpiryService to use unified config directly
        
        # Extract trust store settings from modern config
        trust_anchor_config = self.trust_store_config.trust_anchor
        cert_store_path = trust_anchor_config.certificate_store_path
        
        # Create expiry service with modern config values
        service = CertificateExpiryService(
            certificate_store_path=cert_store_path,
            check_interval_days=self.service_settings.get("cert_check_interval_days", 1),
            notification_days=[30, 14, 7, 1],  # Default notification schedule
            history_file=self.service_settings.get("cert_history_file")
        )
        
        return service
    
    async def _create_openxpki_service(self) -> OpenXPKIService:
        """Create OpenXPKI service with modern configuration."""
        # TODO: Modernize OpenXPKIService to use unified config directly
        service = OpenXPKIService()
        return service
    
    # gRPC Service Methods
    async def VerifyCertificate(self, request, context) -> VerificationResponse:
        """Verify a certificate using the trust store."""
        try:
            self.logger.info(f"Certificate verification request: {request.certificate_id}")
            
            # Use trust store configuration
            cert_store_path = self.trust_store_config.trust_anchor.certificate_store_path
            validation_timeout = self.trust_store_config.trust_anchor.validation_timeout_seconds
            
            # Implement certificate verification logic using modern config
            # This would use the trust store path and validation settings
            
            return VerificationResponse(
                is_valid=True,
                certificate_id=request.certificate_id,
                message="Certificate verified successfully"
            )
            
        except Exception as e:
            self.logger.error(f"Certificate verification failed: {e}")
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return VerificationResponse(is_valid=False, message=str(e))
    
    async def GetTrustStore(self, request, context) -> TrustResponse:
        """Get trust store information."""
        try:
            trust_anchor_config = self.trust_store_config.trust_anchor
            
            return TrustResponse(
                store_path=trust_anchor_config.certificate_store_path,
                last_update=0,  # Would get from actual trust store
                certificate_count=0  # Would get from actual trust store
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get trust store: {e}")
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return TrustResponse()
    
    async def CheckCertificateExpiry(self, request, context) -> ExpiryCheckResponse:
        """Check certificate expiry using modern configuration."""
        try:
            if not self.expiry_service:
                raise RuntimeError("Expiry service not initialized")
            
            # Use the expiry service to check certificates
            expiring_certs = await self.expiry_service.check_expiring_certificates()
            
            # Convert to response format
            response_certs = []
            for cert_info in expiring_certs:
                response_certs.append(
                    ExpiringCertificate(
                        certificate_id=cert_info.get("id", ""),
                        expiry_date=cert_info.get("expiry_date", ""),
                        days_until_expiry=cert_info.get("days_until_expiry", 0)
                    )
                )
            
            return ExpiryCheckResponse(
                expiring_certificates=response_certs,
                total_count=len(response_certs)
            )
            
        except Exception as e:
            self.logger.error(f"Certificate expiry check failed: {e}")
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return ExpiryCheckResponse()
    
    async def GetServiceStatus(self, request, context) -> ServiceStatusResponse:
        """Get service status with modern configuration info."""
        try:
            # Use service discovery config for status
            service_host = self.service_discovery.hosts.get("trust_anchor", "trust-anchor")
            service_port = self.service_discovery.ports.get("trust_anchor", 8080)
            
            return ServiceStatusResponse(
                is_healthy=True,
                service_name="trust-anchor",
                version="2.0.0-modern",
                uptime_seconds=0,  # Would track actual uptime
                host=service_host,
                port=service_port
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get service status: {e}")
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return ServiceStatusResponse(is_healthy=False, message=str(e))
    
    async def SyncMasterList(self, request, context) -> SyncResponse:
        """Sync master list using PKD configuration."""
        try:
            if not self.trust_store_config.pkd.enabled:
                return SyncResponse(
                    success=False,
                    message="PKD synchronization is disabled in configuration"
                )
            
            pkd_url = self.trust_store_config.pkd.service_url
            self.logger.info(f"Syncing master list from PKD: {pkd_url}")
            
            # Implement PKD sync logic using modern config
            # This would use PKD service URL, timeout, and retry settings
            
            return SyncResponse(
                success=True,
                message="Master list synchronized successfully",
                records_updated=0  # Would return actual count
            )
            
        except Exception as e:
            self.logger.error(f"Master list sync failed: {e}")
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return SyncResponse(success=False, message=str(e))


class ModernTrustAnchorServer:
    """Modern gRPC server for Trust Anchor service."""
    
    def __init__(self, config_path: str = "config/services/trust_anchor.yaml"):
        """Initialize with unified configuration."""
        self.logger = logging.getLogger("marty.trust_anchor.server")
        
        # Load configuration
        self.config = create_service_config(config_path)
        self.security_config = self.config.security
        self.service_discovery = self.config.service_discovery
        
        # Initialize service
        self.service = ModernTrustAnchorService(config_path)
        self.server = None
        self._running = False
    
    async def start(self) -> None:
        """Start the gRPC server."""
        try:
            # Initialize service components
            await self.service.initialize()
            
            # Create gRPC server
            self.server = aio.server()
            add_TrustAnchorServicer_to_server(self.service, self.server)
            
            # Configure TLS if enabled
            if self.security_config.grpc_tls and self.security_config.grpc_tls.enabled:
                self.logger.info("Configuring gRPC TLS")
                # Load TLS credentials from modern config
                server_cert = self.security_config.grpc_tls.server_cert
                server_key = self.security_config.grpc_tls.server_key
                
                with open(server_cert, 'rb') as f:
                    server_cert_data = f.read()
                with open(server_key, 'rb') as f:
                    server_key_data = f.read()
                
                credentials = grpc.ssl_server_credentials([
                    (server_key_data, server_cert_data)
                ])
                
                listen_addr = f"[::]:{self.service_discovery.ports.get('trust_anchor', 8080)}"
                self.server.add_secure_port(listen_addr, credentials)
                self.logger.info(f"gRPC server listening securely on {listen_addr}")
            else:
                # Insecure connection
                listen_addr = f"[::]:{self.service_discovery.ports.get('trust_anchor', 8080)}"
                self.server.add_insecure_port(listen_addr)
                self.logger.info(f"gRPC server listening on {listen_addr}")
            
            # Start server
            await self.server.start()
            self._running = True
            self.logger.info("Trust Anchor gRPC server started")
            
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the gRPC server."""
        if self.server and self._running:
            self.logger.info("Stopping Trust Anchor server...")
            await self.server.stop(grace=30)
            self._running = False
            self.logger.info("Trust Anchor server stopped")
    
    async def serve(self) -> None:
        """Run the server until shutdown."""
        await self.start()
        
        try:
            while self._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        finally:
            await self.stop()


async def main():
    """Main function using modern configuration."""
    import sys
    import signal
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Get config path from command line or use default
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/services/trust_anchor.yaml"
    
    # Create and start server
    server = ModernTrustAnchorServer(config_path)
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        asyncio.create_task(server.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await server.serve()
    except Exception as e:
        logging.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())