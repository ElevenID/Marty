"""
Modern Trust Anchor Service using Unified MMF Configuration.

This service demonstrates how to use trust store and PKD configuration
patterns with the unified configuration system.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

# Add framework path
# framework_path = Path(__file__).parent.parent.parent / "marty-microservices-framework" / "src"
# sys.path.append(str(framework_path))

from marty_msf.framework.config import BaseServiceConfig, Environment
from marty_msf.framework.config_factory import create_service_config
from marty_msf.framework.observability.unified_observability import (
    create_observability_manager, 
    MartyMetrics,
    trace_grpc_method
)

if TYPE_CHECKING:
    from marty_plugin.common.grpc_types import ServiceDependencies

import grpc


class ModernTrustAnchor:
    """
    Modern Trust Anchor Service using unified MMF configuration.
    
    This service demonstrates how to use trust store and PKD configuration
    patterns with the unified configuration system.
    """
    
    def __init__(
        self,
        service_name: str = "trust_anchor",
        environment: Optional[str] = None,
        config_path: Optional[Path] = None,
        dependencies: Optional[ServiceDependencies] = None,
    ):
        self.logger = logging.getLogger(__name__)
        
        # Load modern unified configuration
        self.config = create_service_config(
            service_name=service_name,
            environment=environment or "development",
            config_path=config_path or Path("config")
        )
        
        # Set up dependencies
        self.dependencies = dependencies
        
        # Initialize observability
        self.observability = create_observability_manager(self.config)
        
        # Setup business metrics
        self.metrics = MartyMetrics.certificate_validation_metrics(self.observability)
        self.pkd_metrics = MartyMetrics.pkd_sync_metrics(self.observability)
        
        # Initialize service with configuration
        self._initialize_service()
    
    def _initialize_service(self) -> None:
        """Initialize the service using unified configuration."""
        self.logger.info("Initializing Modern Trust Anchor with unified configuration")
        
        # Configure database
        self._configure_database()
        
        # Configure trust store
        self._configure_trust_store()
        
        # Configure PKD integration
        self._configure_pkd()
        
        # Configure service discovery
        self._configure_service_discovery()
        
        # Configure monitoring
        self._configure_monitoring()
        
        # Configure resilience patterns
        self._configure_resilience()
        
        self.logger.info("Modern Trust Anchor initialization complete")
    
    def _configure_database(self) -> None:
        """Configure database connection using unified config."""
        db_config = self.config.database
        
        self.logger.info(
            f"Database configured: {db_config.host}:{db_config.port}/{db_config.database}"
        )
        
        # Store database configuration for use by managers
        self._db_config = {
            "connection_url": db_config.connection_url,
            "pool_size": db_config.pool_size,
            "max_overflow": db_config.max_overflow,
            "pool_timeout": db_config.pool_timeout,
        }
    
    def _configure_trust_store(self) -> None:
        """Configure trust store using unified config."""
        trust_config = self.config.trust_store.trust_anchor
        
        self._trust_store_config = {
            "certificate_store_path": trust_config.certificate_store_path,
            "update_interval_hours": trust_config.update_interval_hours,
            "validation_timeout_seconds": trust_config.validation_timeout_seconds,
            "enable_online_verification": trust_config.enable_online_verification,
        }
        
        self.logger.info(
            f"Trust store configured: path={trust_config.certificate_store_path}, "
            f"update_interval={trust_config.update_interval_hours}h"
        )
        
        # Validate trust store path exists
        store_path = Path(trust_config.certificate_store_path)
        if not store_path.exists():
            self.logger.warning(
                f"Trust store path does not exist: {store_path}. "
                "Service will create it on first use."
            )
    
    def _configure_pkd(self) -> None:
        """Configure PKD integration using unified config."""
        pkd_config = self.config.trust_store.pkd
        
        self._pkd_config = {
            "service_url": pkd_config.service_url,
            "enabled": pkd_config.enabled,
            "update_interval_hours": pkd_config.update_interval_hours,
            "max_retries": pkd_config.max_retries,
            "timeout_seconds": pkd_config.timeout_seconds,
        }
        
        if pkd_config.enabled:
            self.logger.info(
                f"PKD integration enabled: url={pkd_config.service_url}, "
                f"update_interval={pkd_config.update_interval_hours}h"
            )
        else:
            self.logger.info("PKD integration disabled")
    
    def _configure_service_discovery(self) -> None:
        """Configure service discovery using unified config."""
        discovery_config = self.config.service_discovery
        
        self._service_urls = {}
        for service_name, host in discovery_config.hosts.items():
            port = discovery_config.ports.get(service_name, 8080)
            # Use TLS if security is enabled
            use_tls = self.config.security.tls.enabled
            protocol = "https" if use_tls else "http"
            self._service_urls[service_name] = f"{protocol}://{host}:{port}"
        
        self.logger.info(
            f"Service discovery configured: {len(self._service_urls)} services"
        )
        
        # Configure service mesh if enabled
        if discovery_config.enable_service_mesh:
            self.logger.info(
                f"Service mesh enabled in namespace: {discovery_config.service_mesh_namespace}"
            )
    
    def _configure_monitoring(self) -> None:
        """Configure monitoring using unified config."""
        monitoring_config = self.config.monitoring
        
        if monitoring_config.enabled:
            self._metrics_config = {
                "metrics_port": monitoring_config.metrics_port,
                "health_check_port": monitoring_config.health_check_port,
                "prometheus_enabled": monitoring_config.prometheus_enabled,
                "tracing_enabled": monitoring_config.tracing_enabled,
                "jaeger_endpoint": monitoring_config.jaeger_endpoint,
                "service_name": monitoring_config.service_name,
            }
            
            self.logger.info(
                f"Monitoring configured: metrics_port={monitoring_config.metrics_port}, "
                f"tracing={monitoring_config.tracing_enabled}"
            )
    
    def _configure_resilience(self) -> None:
        """Configure resilience patterns using unified config."""
        resilience_config = self.config.resilience
        
        self._circuit_breaker_config = {
            "failure_threshold": resilience_config.circuit_breaker.failure_threshold,
            "recovery_timeout": resilience_config.circuit_breaker.recovery_timeout,
            "half_open_max_calls": resilience_config.circuit_breaker.half_open_max_calls,
        }
        
        self._retry_config = {
            "max_attempts": resilience_config.retry_policy.max_attempts,
            "backoff_multiplier": resilience_config.retry_policy.backoff_multiplier,
            "max_delay_seconds": resilience_config.retry_policy.max_delay_seconds,
        }
        
        self.logger.info(
            f"Resilience configured: circuit_breaker_threshold="
            f"{resilience_config.circuit_breaker.failure_threshold}, "
            f"retry_attempts={resilience_config.retry_policy.max_attempts}"
        )
    
    def get_trust_store_path(self) -> str:
        """Get the configured trust store path."""
        return self._trust_store_config["certificate_store_path"]
    
    def get_pkd_service_url(self) -> Optional[str]:
        """Get the PKD service URL if PKD is enabled."""
        if self._pkd_config["enabled"]:
            return self._pkd_config["service_url"]
        return None
    
    def is_online_verification_enabled(self) -> bool:
        """Check if online verification is enabled."""
        return self._trust_store_config["enable_online_verification"]
    
    def get_service_config_summary(self) -> dict[str, Any]:
        """Get a summary of the service configuration for debugging."""
        return {
            "service_name": self.config.service_name,
            "environment": self.config.environment.value,
            "database": {
                "host": self.config.database.host,
                "port": self.config.database.port,
                "database": self.config.database.database,
            },
            "security": {
                "tls_enabled": self.config.security.tls.enabled,
                "mtls_enabled": self.config.security.tls.mtls,
                "auth_required": self.config.security.auth.required,
            },
            "trust_store": {
                "certificate_store_path": self._trust_store_config["certificate_store_path"],
                "update_interval_hours": self._trust_store_config["update_interval_hours"],
                "online_verification": self._trust_store_config["enable_online_verification"],
            },
            "pkd": {
                "enabled": self._pkd_config["enabled"],
                "service_url": self._pkd_config["service_url"],
                "update_interval_hours": self._pkd_config["update_interval_hours"],
            },
            "monitoring": {
                "enabled": self.config.monitoring.enabled,
                "metrics_port": self.config.monitoring.metrics_port,
                "tracing_enabled": self.config.monitoring.tracing_enabled,
            },
            "service_discovery": {
                "service_count": len(self._service_urls),
                "service_mesh_enabled": self.config.service_discovery.enable_service_mesh,
            }
        }
    
    def print_configuration_summary(self) -> None:
        """Print a detailed configuration summary."""
        summary = self.get_service_config_summary()
        
        print("\\n" + "="*60)
        print("MODERN TRUST ANCHOR CONFIGURATION SUMMARY")
        print("="*60)
        
        print(f"Service Name: {summary['service_name']}")
        print(f"Environment: {summary['environment']}")
        
        print("\\nDatabase Configuration:")
        db = summary['database']
        print(f"  Host: {db['host']}:{db['port']}")
        print(f"  Database: {db['database']}")
        
        print("\\nSecurity Configuration:")
        sec = summary['security']
        print(f"  TLS Enabled: {sec['tls_enabled']}")
        print(f"  mTLS Enabled: {sec['mtls_enabled']}")
        print(f"  Auth Required: {sec['auth_required']}")
        
        print("\\nTrust Store Configuration:")
        trust = summary['trust_store']
        print(f"  Certificate Store Path: {trust['certificate_store_path']}")
        print(f"  Update Interval: {trust['update_interval_hours']} hours")
        print(f"  Online Verification: {trust['online_verification']}")
        
        print("\\nPKD Configuration:")
        pkd = summary['pkd']
        print(f"  Enabled: {pkd['enabled']}")
        if pkd['enabled']:
            print(f"  Service URL: {pkd['service_url']}")
            print(f"  Update Interval: {pkd['update_interval_hours']} hours")
        
        print("\\nMonitoring Configuration:")
        mon = summary['monitoring']
        print(f"  Enabled: {mon['enabled']}")
        print(f"  Metrics Port: {mon['metrics_port']}")
        print(f"  Tracing Enabled: {mon['tracing_enabled']}")
        
        print("\\nService Discovery:")
        sd = summary['service_discovery']
        print(f"  Services Configured: {sd['service_count']}")
        print(f"  Service Mesh: {sd['service_mesh_enabled']}")
        
        print("="*60)
    
    # Trust operations
    def validate_certificate_chain(self, certificate_chain: list[str]) -> bool:
        """Validate a certificate chain against the trust store."""
        with self.observability.trace_operation(
            "validate_certificate_chain",
            certificate_count=len(certificate_chain)
        ) as span:
            
            self.logger.info(
                "Validating certificate chain with %d certificates", 
                len(certificate_chain)
            )
            
            try:
                # Implementation would use the configured trust store path
                trust_store_path = self.get_trust_store_path()
                self.logger.debug("Using trust store: %s", trust_store_path)
                
                # Record validation attempt
                if self.metrics and "validations_total" in self.metrics:
                    # Determine certificate type (placeholder logic)
                    cert_type = "unknown"
                    if certificate_chain:
                        cert_type = "eMRTD"  # Default assumption for Marty
                    
                    # Placeholder for actual validation logic
                    is_valid = True  # Would be actual validation result
                    
                    # Record metrics
                    result = "success" if is_valid else "failure"
                    self.metrics["validations_total"].labels(
                        result=result,
                        certificate_type=cert_type,
                        issuer_country="unknown"  # Would extract from cert
                    ).inc()
                    
                    # Record trust chain length
                    if "trust_chain_length" in self.metrics:
                        self.metrics["trust_chain_length"].labels(
                            certificate_type=cert_type
                        ).observe(len(certificate_chain))
                
                if span:
                    span.set_attribute("validation.result", "success")
                    span.set_attribute("validation.certificate_type", cert_type)
                
                return True
                
            except Exception as e:
                # Record validation failure
                if self.metrics and "validations_total" in self.metrics:
                    self.metrics["validations_total"].labels(
                        result="error",
                        certificate_type="unknown",
                        issuer_country="unknown"
                    ).inc()
                
                if span:
                    span.set_attribute("validation.result", "error")
                    span.set_attribute("validation.error", str(e))
                
                self.logger.error("Certificate validation failed: %s", e)
                return False
    
    def sync_with_pkd(self) -> bool:
        """Synchronize certificates with PKD service."""
        if not self._pkd_config["enabled"]:
            self.logger.warning("PKD sync requested but PKD is disabled")
            return False
        
        with self.observability.trace_operation("pkd_sync") as span:
            pkd_url = self.get_pkd_service_url()
            self.logger.info("Synchronizing with PKD at: %s", pkd_url)
            
            try:
                # Implementation would use the configured PKD settings
                # Including retry policy and timeout configuration
                
                # Record sync attempt 
                if self.pkd_metrics and "sync_operations" in self.pkd_metrics:
                    start_time = time.time()
                    
                    # Placeholder for actual sync logic
                    records_processed = 150  # Would be actual count
                    
                    # Record success metrics
                    self.pkd_metrics["sync_operations"].labels(
                        result="success",
                        sync_type="full"
                    ).inc()
                    
                    duration = time.time() - start_time
                    self.pkd_metrics["sync_duration"].labels(
                        sync_type="full"
                    ).observe(duration)
                    
                    self.pkd_metrics["records_processed"].labels(
                        sync_type="full"
                    ).observe(records_processed)
                
                if span:
                    span.set_attribute("pkd.sync_type", "full")
                    span.set_attribute("pkd.records_processed", records_processed)
                    span.set_attribute("pkd.url", pkd_url)
                
                return True
                
            except Exception as e:
                # Record sync failure
                if self.pkd_metrics and "sync_operations" in self.pkd_metrics:
                    self.pkd_metrics["sync_operations"].labels(
                        result="error",
                        sync_type="full"
                    ).inc()
                
                if span:
                    span.set_attribute("pkd.sync_error", str(e))
                
                self.logger.error("PKD sync failed: %s", e)
                return False
    
    def update_trust_store(self) -> bool:
        """Update the trust store with latest certificates."""
        self.logger.info("Updating trust store")
        
        trust_store_path = self.get_trust_store_path()
        update_interval = self._trust_store_config["update_interval_hours"]
        
        self.logger.debug(
            f"Trust store path: {trust_store_path}, "
            f"update interval: {update_interval} hours"
        )
        
        # Implementation would check last update time and update if needed
        # Placeholder for actual update logic
        return True


def create_modern_trust_anchor(
    environment: Optional[str] = None,
    config_path: Optional[Path] = None,
    dependencies: Optional[ServiceDependencies] = None,
) -> ModernTrustAnchor:
    """
    Factory function to create a modern trust anchor service.
    
    Args:
        environment: Environment name (development, testing, production)
        config_path: Path to configuration directory  
        dependencies: Service dependencies
        
    Returns:
        ModernTrustAnchor instance
    """
    return ModernTrustAnchor(
        service_name="trust_anchor",
        environment=environment,
        config_path=config_path,
        dependencies=dependencies,
    )


if __name__ == "__main__":
    # Example usage - create and configure the service
    print("Modern Trust Anchor Configuration Example")
    
    try:
        # Test different environments
        for env in ["development", "testing", "production"]:
            print(f"\\n--- Testing {env.upper()} Environment ---")
            
            trust_anchor = ModernTrustAnchor(
                service_name="trust_anchor",
                environment=env,
                config_path=Path("config"),
            )
            
            trust_anchor.print_configuration_summary()
            
            # Test some operations
            print(f"\\nTrust Store Path: {trust_anchor.get_trust_store_path()}")
            print(f"PKD Service URL: {trust_anchor.get_pkd_service_url()}")
            print(f"Online Verification: {trust_anchor.is_online_verification_enabled()}")
            
    except Exception as e:
        print(f"Configuration test failed: {e}")
        print("Ensure config files exist and framework is properly set up")