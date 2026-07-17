"""
Migration helper for transitioning from legacy to modern configuration.

This module provides utilities to help migrate services from the legacy
marty_common configuration system to the unified MMF configuration system.

Usage:
    # For services that can't be immediately migrated:
    from marty_common.config_migration import get_modern_config_for_service
    
    # Replace legacy config manager usage:
    config = get_modern_config_for_service("trust-anchor")
    port = config.service_discovery.ports.get("trust_anchor", 8080)
"""

from typing import Any, Dict, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import modern config, fall back gracefully
try:
    import sys
    framework_path = Path(__file__).parent.parent.parent / "marty-microservices-framework" / "src"
    sys.path.insert(0, str(framework_path))
    
    from framework.config_factory import create_service_config
    from framework.config import AppConfigManager
    MODERN_CONFIG_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Modern configuration not available: {e}")
    MODERN_CONFIG_AVAILABLE = False


def get_modern_config_for_service(service_name: str) -> Optional[Any]:
    """
    Get modern configuration for a service, creating a default config file if needed.
    
    Args:
        service_name: Name of the service (e.g., "trust-anchor", "document-signer")
        
    Returns:
        Modern configuration object or None if not available
    """
    if not MODERN_CONFIG_AVAILABLE:
        logger.error("Modern configuration system not available")
        return None
    
    try:
        # Convert service name to match config file naming
        config_file_name = service_name.replace("-", "_")
        config_path = f"config/services/{config_file_name}.yaml"
        
        # Check if config file exists, create from template if not
        config_file = Path(config_path)
        if not config_file.exists():
            logger.info(f"Creating default config file for {service_name}")
            create_default_service_config(service_name, config_path)
        
        # Load modern configuration
        return create_service_config(config_path)
        
    except Exception as e:
        logger.error(f"Failed to load modern config for {service_name}: {e}")
        return None


def create_default_service_config(service_name: str, config_path: str) -> None:
    """
    Create a default service configuration file based on the template.
    
    Args:
        service_name: Name of the service
        config_path: Path where to create the config file
    """
    # Service name transformations
    service_name_snake = service_name.replace("-", "_")
    service_name_upper = service_name_snake.upper()
    
    # Basic template for any service
    default_config = f"""# Auto-generated configuration for {service_name}
# Migrate to modern configuration patterns

# Database configuration - per service database
database:
  {service_name_snake}:
    host: "${{{service_name_upper}_DB_HOST:-localhost}}"
    port: ${{{service_name_upper}_DB_PORT:-5432}}
    database: "${{{service_name_upper}_DB_NAME:-marty_{service_name_snake}}}"
    username: "${{{service_name_upper}_DB_USER:-{service_name_snake}_user}}"
    password: "${{{service_name_upper}_DB_PASSWORD:-change_me_in_production}}"
    pool_size: 10
    max_overflow: 20

# Security configuration
security:
  grpc_tls:
    enabled: true
    server_cert: "${{TLS_SERVER_CERT:-/etc/tls/server/tls.crt}}"
    server_key: "${{TLS_SERVER_KEY:-/etc/tls/server/tls.key}}"
  auth:
    required: true
    jwt_enabled: true

# Service discovery
service_discovery:
  hosts:
    {service_name_snake}: "${{{service_name_upper}_HOST:-{service_name}}}"
  ports:
    {service_name_snake}: ${{{service_name_upper}_PORT:-8080}}

# Logging configuration
logging:
  level: "${{LOG_LEVEL:-INFO}}"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Monitoring
monitoring:
  enabled: true
  metrics_port: ${{METRICS_PORT:-9090}}

# Service-specific configuration
services:
  {service_name_snake}:
    max_concurrent_operations: 10
    operation_timeout_seconds: 30
"""

    # Add trust store config for trust-anchor service
    if "trust" in service_name or "anchor" in service_name:
        default_config += f"""
# Trust store configuration
trust_store:
  trust_anchor:
    certificate_store_path: "${{CERT_STORE_PATH:-/app/data/trust}}"
    update_interval_hours: ${{TRUST_UPDATE_INTERVAL:-24}}
    validation_timeout_seconds: ${{VALIDATION_TIMEOUT:-30}}
  pkd:
    service_url: "${{PKD_SERVICE_URL:-http://pkd-service:8089}}"
    enabled: ${{PKD_ENABLED:-true}}
"""

    # Add cryptographic config for signer services
    if "signer" in service_name or "sign" in service_name:
        default_config += f"""
# Cryptographic configuration
cryptographic:
  signing:
    algorithm: "rsa2048"
    key_id: "{service_name_snake}-default"
    key_directory: "${{KEY_DIRECTORY:-/app/data/keys}}"
  vault:
    url: "${{VAULT_ADDR:-https://vault.internal:8200}}"
"""

    # Create config directory if it doesn't exist
    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write config file
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(default_config)
    
    logger.info(f"Created default config file: {config_path}")


def migrate_legacy_config_usage(legacy_code: str) -> str:
    """
    Provide migration suggestions for legacy configuration code.
    
    Args:
        legacy_code: Code snippet using legacy configuration
        
    Returns:
        Suggested modern replacement
    """
    migrations = {
        # Legacy config manager patterns
        "get_config_manager(": "# Replace with: config = create_service_config('config/services/service.yaml')",
        "config_manager.get_env_int(": "# Replace with: config.service_discovery.ports.get(",
        "config_manager.get_env_path(": "# Replace with: Path(config.service_settings.get(",
        "config_manager.get_env_list(": "# Replace with: config.service_settings.get(",
        
        # Legacy Config class patterns  
        "Config()": "# Replace with: create_service_config('config/services/service.yaml')",
        "config.get_service(": "# Replace with: config.services.get(",
        "config.database(": "# Replace with: config.database.get_config(",
        
        # Environment variable patterns
        'os.environ.get("GRPC_PORT"': "# Replace with: config.service_discovery.ports.get('service_name'",
        'os.getenv("': "# Replace with config-based access or use ${VAR:-default} in YAML",
    }
    
    suggestions = []
    for old_pattern, suggestion in migrations.items():
        if old_pattern in legacy_code:
            suggestions.append(f"{old_pattern} -> {suggestion}")
    
    return "\n".join(suggestions) if suggestions else "No legacy patterns detected"


# Convenience functions for common migration patterns
def get_grpc_port(service_name: str, default: int = 8080) -> int:
    """Get gRPC port using modern config with fallback."""
    config = get_modern_config_for_service(service_name)
    if config and hasattr(config, 'service_discovery'):
        service_key = service_name.replace("-", "_")
        return config.service_discovery.ports.get(service_key, default)
    return default


def get_database_url(service_name: str) -> Optional[str]:
    """Get database URL using modern config with fallback."""
    config = get_modern_config_for_service(service_name)
    if config and hasattr(config, 'database'):
        service_key = service_name.replace("-", "_")
        db_config = config.database.get_config(service_key)
        if db_config:
            return f"postgresql://{db_config.username}:{db_config.password}@{db_config.host}:{db_config.port}/{db_config.database}"
    return None


def get_service_host(service_name: str, default: str = "localhost") -> str:
    """Get service host using modern config with fallback."""
    config = get_modern_config_for_service(service_name)
    if config and hasattr(config, 'service_discovery'):
        service_key = service_name.replace("-", "_")
        return config.service_discovery.hosts.get(service_key, default)
    return default