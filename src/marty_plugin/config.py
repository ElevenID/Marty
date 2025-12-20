"""
Marty MMF Plugin Configuration

Configuration classes for integrating Marty services with the MMF framework.
"""

from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
import sys

# Add MMF framework to path
mmf_framework_path = Path(__file__).parent.parent.parent / "marty-microservices-framework" / "src"
if mmf_framework_path.exists():
    sys.path.insert(0, str(mmf_framework_path))

try:
    from framework.config.plugin_config import PluginConfigSection
except ImportError:
    # Fallback for when MMF is not available
    class PluginConfigSection(BaseModel):
        enabled: bool = True


class MartyTrustPKIConfig(PluginConfigSection):
    """Configuration for Marty Trust PKI services."""
    
    # Trust infrastructure URLs
    trust_anchor_url: str = Field(
        default="https://trust.example.com",
        description="Trust anchor service endpoint"
    )
    pkd_url: str = Field(
        default="https://pkd.example.com", 
        description="Public Key Directory service endpoint"
    )
    document_signer_url: str = Field(
        default="https://signer.example.com",
        description="Document signer service endpoint"
    )
    csca_service_url: str = Field(
        default="https://csca.example.com",
        description="CSCA (Country Signing CA) service endpoint"
    )
    
    # Cryptographic configuration
    signing_algorithms: List[str] = Field(
        default=["RSA-SHA256"],
        description="Supported signing algorithms"
    )
    
    # Security settings
    certificate_validation_enabled: bool = Field(
        default=True,
        description="Enable certificate validation"
    )
    require_mutual_tls: bool = Field(
        default=False,
        description="Require mutual TLS for connections"
    )
    
    # Trust store configuration
    trust_store_path: Optional[str] = Field(
        default=None,
        description="Path to trust store file"
    )
    
    # ICAO PKI compliance
    icao_compliance_mode: bool = Field(
        default=True,
        description="Enable ICAO PKI compliance mode"
    )
    
    # Service discovery
    service_registry_enabled: bool = Field(
        default=True,
        description="Enable service registry integration"
    )
    
    class Config:
        """Pydantic configuration."""
        env_prefix = "MARTY_"
        case_sensitive = False