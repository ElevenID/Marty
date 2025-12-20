"""
Trust Services Configuration - Updated for Unified MMF Configuration

This is an example of how to migrate a Marty service to use the unified
Marty Microservices Framework configuration system.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Add framework path for imports
framework_path = Path(__file__).parent.parent.parent / "marty-microservices-framework" / "src"
sys.path.append(str(framework_path))

try:
    from framework.config import BaseServiceConfig, Environment
    from framework.marty_config_adapter import create_unified_config
    UNIFIED_CONFIG_AVAILABLE = True
except ImportError:
    UNIFIED_CONFIG_AVAILABLE = False
    print("Warning: Unified configuration not available, falling back to legacy config")


class TrustServiceUnifiedConfig:
    """
    Trust service configuration using the unified MMF configuration system.
    
    This class demonstrates how to migrate from Marty's legacy configuration
    to the unified system while maintaining backward compatibility.
    """
    
    def __init__(
        self, 
        service_name: str = "trust_anchor",
        environment: Optional[str] = None,
        config_path: Optional[Path] = None
    ):
        self.service_name = service_name
        self.environment = environment or os.getenv("ENV", "development")
        self.config_path = config_path or Path("config")
        
        # Load unified configuration
        self._config = self._load_unified_config()
        
    def _load_unified_config(self) -> Optional[BaseServiceConfig]:
        """Load configuration using the unified system."""
        if not UNIFIED_CONFIG_AVAILABLE:
            return None
            
        try:
            # Use the unified config that works with both Marty and MMF formats
            return create_unified_config(
                service_name=self.service_name,
                environment=self.environment,
                config_path=self.config_path
            )
        except Exception as e:
            print(f"Failed to load unified config: {e}")
            try:
                # Fallback to direct MMF ServiceConfig
                return BaseServiceConfig(
                    service_name=self.service_name,
                    environment=Environment(self.environment),
                    config_path=self.config_path
                )
            except Exception as e2:
                print(f"Failed to load MMF config: {e2}")
                return None
    
    @property 
    def database(self):
        """Get database configuration with fallback to environment variables."""
        if self._config:
            try:
                return self._config.database
            except Exception:
                pass
        
        # Fallback to environment variables (legacy behavior)
        from dataclasses import dataclass
        
        @dataclass
        class LegacyDatabaseConfig:
            host: str = os.getenv("TRUST_DB_HOST", "localhost")
            port: int = int(os.getenv("TRUST_DB_PORT", "5432"))
            database: str = os.getenv("TRUST_DB_NAME", "marty_trust")
            username: str = os.getenv("TRUST_DB_USER", "trust_service")
            password: str = os.getenv("TRUST_DB_PASSWORD", "change_me")
            pool_size: int = int(os.getenv("TRUST_DB_POOL_SIZE", "10"))
            
            @property
            def connection_url(self) -> str:
                return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        
        return LegacyDatabaseConfig()
    
    @property
    def security(self):
        """Get security configuration."""
        if self._config:
            try:
                return self._config.security
            except Exception:
                pass
        return None
    
    @property
    def trust_store(self):
        """Get trust store configuration (Marty-specific)."""
        if self._config:
            try:
                return self._config.trust_store
            except Exception:
                pass
        return None
    
    @property
    def cryptographic(self):
        """Get cryptographic configuration (Marty-specific)."""
        if self._config:
            try:
                return self._config.cryptographic
            except Exception:
                pass
        return None
    
    @property
    def service_discovery(self):
        """Get service discovery configuration."""
        if self._config:
            try:
                return self._config.service_discovery
            except Exception:
                pass
        return None
    
    @property
    def logging(self):
        """Get logging configuration."""
        if self._config:
            try:
                return self._config.logging
            except Exception:
                pass
        return None
    
    @property
    def monitoring(self):
        """Get monitoring configuration."""
        if self._config:
            try:
                return self._config.monitoring
            except Exception:
                pass
        return None
    
    # Legacy compatibility methods
    @property
    def kms_config(self):
        """Get KMS configuration with fallback to legacy implementation."""
        # Try to get from cryptographic config first
        crypto_config = self.cryptographic
        if crypto_config and crypto_config.vault.url:
            from dataclasses import dataclass
            
            @dataclass
            class UnifiedKMSConfig:
                provider: str = "vault"
                vault_url: str = crypto_config.vault.url
                auth_method: str = crypto_config.vault.auth_method
                key_path: str = "secret/signing-keys"
                
            return UnifiedKMSConfig()
        
        # Fallback to legacy environment-based config
        from dataclasses import dataclass
        
        @dataclass
        class LegacyKMSConfig:
            provider: str = os.getenv("KMS_PROVIDER", "aws")
            key_id: str = os.getenv("KMS_KEY_ID", "alias/marty-trust-signing")
            region: str = os.getenv("KMS_REGION", "us-east-1")
            signature_algorithm: str = "RSA_PKCS1_SHA_256"
            
        return LegacyKMSConfig()
    
    @property
    def pkd_config(self):
        """Get PKD configuration with fallback to legacy implementation."""
        # Try to get from trust store config first
        trust_config = self.trust_store
        if trust_config and trust_config.pkd.service_url:
            from dataclasses import dataclass
            
            @dataclass
            class UnifiedPKDConfig:
                service_url: str = trust_config.pkd.service_url
                enabled: bool = trust_config.pkd.enabled
                data_directory: str = os.getenv("PKD_DATA_DIR", "/app/data/pkd")
                update_interval_hours: int = trust_config.pkd.update_interval_hours
                
            return UnifiedPKDConfig()
        
        # Fallback to legacy environment-based config
        from dataclasses import dataclass
        
        @dataclass
        class LegacyPKDConfig:
            data_directory: str = os.getenv("PKD_DATA_DIR", "/app/data/pkd")
            synthetic_data_dir: str = os.getenv("SYNTHETIC_DATA_DIR", "/app/data/synthetic")
            master_list_max_age_hours: int = int(os.getenv("MASTER_LIST_MAX_AGE_HOURS", "24"))
            
        return LegacyPKDConfig()
    
    def get_service_url(self, service_name: str, use_tls: bool = None) -> str:
        """Get URL for another service using service discovery."""
        discovery_config = self.service_discovery
        if discovery_config:
            return discovery_config.get_service_url(service_name, use_tls or False)
        
        # Fallback to environment variables
        host = os.getenv(f"{service_name.upper()}_HOST", "localhost")
        port = os.getenv(f"{service_name.upper()}_PORT", "8080")
        protocol = "https" if use_tls else "http"
        return f"{protocol}://{host}:{port}"
    
    def print_config_summary(self):
        """Print configuration summary for debugging."""
        print(f"\\n=== Trust Service Configuration Summary ===")
        print(f"Service: {self.service_name}")
        print(f"Environment: {self.environment}")
        print(f"Config Path: {self.config_path}")
        print(f"Unified Config Available: {UNIFIED_CONFIG_AVAILABLE}")
        print(f"Unified Config Loaded: {self._config is not None}")
        
        # Database config
        db_config = self.database
        if db_config:
            print(f"Database: {getattr(db_config, 'host', 'unknown')}:{getattr(db_config, 'port', 'unknown')}")
            print(f"Database name: {getattr(db_config, 'database', 'unknown')}")
        
        # Security config
        security_config = self.security
        if security_config:
            print(f"TLS enabled: {getattr(security_config.tls, 'enabled', 'unknown')}")
        
        # Trust store config
        trust_config = self.trust_store
        if trust_config:
            print(f"Certificate store: {getattr(trust_config.trust_anchor, 'certificate_store_path', 'not configured')}")
            print(f"PKD URL: {getattr(trust_config.pkd, 'service_url', 'not configured')}")
        
        # KMS config
        kms_config = self.kms_config
        if kms_config:
            print(f"KMS Provider: {getattr(kms_config, 'provider', 'unknown')}")


# Factory function for easy instantiation
def create_trust_service_config(
    environment: Optional[str] = None,
    config_path: Optional[Path] = None
) -> TrustServiceUnifiedConfig:
    """
    Factory function to create trust service configuration.
    
    Args:
        environment: Environment name (development, production, etc.)
        config_path: Path to configuration directory
        
    Returns:
        TrustServiceUnifiedConfig instance
    """
    return TrustServiceUnifiedConfig(
        service_name="trust_anchor",
        environment=environment,
        config_path=config_path
    )


# Global config instance for backward compatibility
config = create_trust_service_config()


if __name__ == "__main__":
    # Example usage
    print("Trust Service Configuration Migration Example")
    
    # Test different environments
    for env in ["development", "testing", "production"]:
        print(f"\\n--- Testing {env} environment ---")
        test_config = create_trust_service_config(environment=env)
        test_config.print_config_summary()