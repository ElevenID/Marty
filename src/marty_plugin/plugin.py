"""
Marty MMF Plugin

Main plugin class that integrates Marty services with the MMF framework.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add MMF framework to path
try:
    from mmf.core.plugins import MMFPlugin, PluginContext, PluginMetadata
except ImportError:
    # Development mode - use local MMF
    mmf_path = Path(__file__).parent.parent.parent / "marty-microservices-framework"
    if mmf_path.exists():
        sys.path.insert(0, str(mmf_path))
        try:
            from mmf.core.plugins import MMFPlugin, PluginContext, PluginMetadata
        except ImportError as e:
             raise ImportError(f"MMF framework found but import failed: {e}. Please check structure.")
    else:
        raise ImportError("MMF framework not found. Please install marty-msf package.")

from .config import MartyTrustPKIConfig
from .services import (
    TrustAnchorService,
    PKDService,
    DocumentSignerService,
    CSCAService
)


class MartyPlugin(MMFPlugin):
    """
    Marty Trust PKI Plugin for MMF framework.
    
    This plugin provides Trust PKI services including:
    - Trust anchor management
    - PKD (Public Key Directory) services
    - Document signer verification
    - CSCA (Country Signing Certificate Authority) management
    """
    
    def __init__(self):
        """Initialize the Marty plugin."""
        self._metadata = PluginMetadata(
            name="marty",
            version="1.0.0",
            description="Marty Trust PKI services for ICAO compliance and document verification",
            author="Marty Team",
            dependencies=["cryptography", "asn1crypto", "pydantic"],
            tags=["trust", "pki", "icao", "document-verification"]
        )
        super().__init__()
        self.config = None
        self.services = {}
        
    @property
    def metadata(self) -> PluginMetadata:
        """Plugin metadata."""
        return self._metadata
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get plugin metadata."""
        return {
            "name": self.metadata.name,
            "version": self.metadata.version,
            "description": self.metadata.description,
            "author": self.metadata.author,
            "dependencies": self.metadata.dependencies,
            "services": [
                "trust_anchor",
                "pkd",
                "document_signer",
                "csca"
            ],
            "config_schema": "MartyTrustPKIConfig"
        }
    
    async def _initialize_plugin(self) -> None:
        """Initialize the Marty plugin with MMF context."""
        # Load configuration
        self.config = MartyTrustPKIConfig()
        
        # Initialize services
        await self._initialize_services()
    
    async def _initialize_services(self) -> None:
        """Initialize all Marty services."""
        try:
            # Initialize Trust Anchor Service
            self.services["trust_anchor"] = TrustAnchorService()
            
            # Initialize PKD Service
            self.services["pkd"] = PKDService()
            
            # Initialize Document Signer Service
            self.services["document_signer"] = DocumentSignerService()
            
            # Initialize CSCA Service
            self.services["csca"] = CSCAService()
            
            # Initialize services with configuration
            config_dict = self.config.model_dump() if self.config else {}
            for service_name, service in self.services.items():
                if hasattr(service, 'initialize'):
                    await service.initialize(config_dict)
                    
        except Exception as e:
            print(f"Error initializing Marty services: {e}")
            raise
    
    async def start(self) -> None:
        """Start the Marty plugin services."""
        print(f"Starting Marty plugin v{self.metadata.version}")
        
        # Start all services
        for service_name, service in self.services.items():
            try:
                if hasattr(service, 'start'):
                    await service.start()
                print(f"✅ Started {service_name} service")
            except Exception as e:
                print(f"❌ Failed to start {service_name} service: {e}")
                raise
        
        print("🎉 Marty plugin started successfully")
    
    async def stop(self) -> None:
        """Stop the Marty plugin services."""
        print("Stopping Marty plugin...")
        
        # Stop all services
        for service_name, service in self.services.items():
            try:
                if hasattr(service, 'stop'):
                    await service.stop()
                print(f"✅ Stopped {service_name} service")
            except Exception as e:
                print(f"❌ Error stopping {service_name} service: {e}")
        
        print("✅ Marty plugin stopped")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check the health of all plugin services."""
        service_health = {}
        overall_status = "healthy"
        
        for service_name, service in self.services.items():
            try:
                if hasattr(service, 'health_check'):
                    health = await service.health_check()
                    service_health[service_name] = health
                    if health.get("status") != "healthy":
                        overall_status = "unhealthy"
                else:
                    service_health[service_name] = {
                        "status": "healthy",
                        "message": "Service running (no health check method)"
                    }
            except Exception as e:
                service_health[service_name] = {
                    "status": "error",
                    "error": str(e)
                }
                overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "plugin": self.metadata.name,
            "version": self.metadata.version,
            "services": service_health
        }
    
    def get_services(self) -> List[str]:
        """Get list of available services."""
        return list(self.services.keys())
    
    def get_service(self, name: str) -> Optional[Any]:
        """Get a specific service by name."""
        return self.services.get(name)

    def _get_context(self) -> Optional[Any]:
        """Get the plugin context, trying different storage methods."""
        # Try context attribute first
        if hasattr(self, 'context'):
            return getattr(self, 'context', None)
        # Try private context attribute
        if hasattr(self, '_context'):
            return getattr(self, '_context', None)
        return None
