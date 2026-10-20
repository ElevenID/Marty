"""Configuration management for trust and PKD services.

Provides centralized configuration for:
- Database connections
- PKD service endpoints
- Security policies
- Monitoring settings
- Deployment parameters
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, validator


class DatabaseConfig(BaseModel):
    """Database configuration."""

    host: str = Field(..., description="Database host")
    port: int = Field(5432, description="Database port")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Database username")
    password: str = Field(..., description="Database password")
    ssl_mode: str = Field("require", description="SSL mode")
    pool_size: int = Field(10, description="Connection pool size")
    max_overflow: int = Field(20, description="Max pool overflow")
    pool_timeout: int = Field(30, description="Pool timeout seconds")

    @property
    def connection_string(self) -> str:
        """Get SQLAlchemy connection string."""
        return (
            f"postgresql+asyncpg://{self.username}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}?sslmode={self.ssl_mode}"
        )


class SecurityConfig(BaseModel):
    """Security configuration."""

    encryption_key: str = Field(..., description="Encryption key for private keys")
    jwt_secret: str = Field(..., description="JWT signing secret")
    api_keys: dict[str, str] = Field(default_factory=dict, description="API key mappings")
    cors_origins: list[str] = Field(default_factory=list, description="CORS allowed origins")
    rate_limit_requests: int = Field(100, description="Rate limit requests per minute")
    rate_limit_window: int = Field(60, description="Rate limit window seconds")

    @validator("encryption_key", "jwt_secret")
    def validate_secrets(self, v: str) -> str:
        """Validate secret length."""
        if len(v) < 32:
            msg = "Secrets must be at least 32 characters"
            raise ValueError(msg)
        return v


class PKDConfig(BaseModel):
    """PKD service configuration."""

    base_url: str = Field(..., description="PKD service base URL")
    api_version: str = Field("v1", description="API version")
    timeout_seconds: int = Field(30, description="Request timeout")
    retry_attempts: int = Field(3, description="Retry attempts")
    retry_delay: int = Field(5, description="Retry delay seconds")
    cache_ttl: int = Field(3600, description="Cache TTL seconds")

    @property
    def endpoints(self) -> dict[str, str]:
        """Get API endpoints."""
        base = f"{self.base_url}/api/{self.api_version}/pkd"
        return {
            "vds_nc_keys_country": f"{base}/vds-nc-keys/{{country}}",
            "vds_nc_keys_all": f"{base}/vds-nc-keys/all",
            "vds_nc_key_by_kid": f"{base}/vds-nc-keys/key/{{kid}}",
            "trust_store": f"{base}/trust-store/{{country}}",
            "revocation_list": f"{base}/vds-nc-keys/{{country}}/revocation-list",
            "health": f"{base}/health",
        }


class MonitoringConfig(BaseModel):
    """Monitoring configuration."""

    enable_metrics: bool = Field(True, description="Enable Prometheus metrics")
    metrics_port: int = Field(8080, description="Metrics server port")
    enable_tracing: bool = Field(True, description="Enable distributed tracing")
    jaeger_endpoint: str = Field("", description="Jaeger endpoint URL")
    log_level: str = Field("INFO", description="Log level")
    log_format: str = Field("json", description="Log format (json/text)")

    @validator("log_level")
    def validate_log_level(self, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            msg = f"Log level must be one of: {valid_levels}"
            raise ValueError(msg)
        return v.upper()


class TrustConfig(BaseModel):
    """Trust management configuration."""

    policy: str = Field("fail_closed", description="Trust policy")
    refresh_interval: int = Field(86400, description="Trust list refresh interval seconds")
    warning_threshold: int = Field(24, description="Stale warning threshold hours")
    critical_threshold: int = Field(48, description="Stale critical threshold hours")
    cache_directory: str = Field("/var/cache/marty/trust", description="Trust cache directory")
    backup_directory: str = Field("/var/backup/marty/trust", description="Trust backup directory")

    @validator("policy")
    def validate_policy(self, v: str) -> str:
        """Validate trust policy."""
        valid_policies = ["fail_closed", "fail_open", "selective"]
        if v not in valid_policies:
            msg = f"Trust policy must be one of: {valid_policies}"
            raise ValueError(msg)
        return v


class KeyRotationConfig(BaseModel):
    """Key rotation configuration."""

    rotation_warning_days: int = Field(30, description="Key rotation warning days")
    overlap_days: int = Field(30, description="Key overlap period days")
    auto_rotation: bool = Field(False, description="Enable automatic rotation")
    rotation_schedule: str = Field("0 2 * * 0", description="Rotation cron schedule")
    backup_generations: int = Field(5, description="Keep N backup generations")


@dataclass
class DeploymentConfig:
    """Deployment configuration."""

    environment: str  # "development", "staging", "production"
    cluster_name: str
    namespace: str
    replica_count: int = 3
    resources: dict[str, Any] = field(default_factory=dict)
    health_check_path: str = "/health"
    readiness_check_path: str = "/ready"

    def __post_init__(self) -> None:
        """Set default resources based on environment."""
        if not self.resources:
            if self.environment == "production":
                self.resources = {
                    "requests": {"cpu": "500m", "memory": "1Gi"},
                    "limits": {"cpu": "2000m", "memory": "4Gi"},
                }
            elif self.environment == "staging":
                self.resources = {
                    "requests": {"cpu": "250m", "memory": "512Mi"},
                    "limits": {"cpu": "1000m", "memory": "2Gi"},
                }
            else:  # development
                self.resources = {
                    "requests": {"cpu": "100m", "memory": "256Mi"},
                    "limits": {"cpu": "500m", "memory": "1Gi"},
                }


class ServiceConfig(BaseModel):
    """Complete service configuration."""

    database: DatabaseConfig
    security: SecurityConfig
    pkd: PKDConfig
    monitoring: MonitoringConfig
    trust: TrustConfig
    key_rotation: KeyRotationConfig
    deployment: DeploymentConfig | None = None

    @classmethod
    def from_file(cls, config_path: Path | str) -> ServiceConfig:
        """Load configuration from YAML file."""
        config_path = Path(config_path)

        if not config_path.exists():
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)

        with open(config_path) as f:
            config_data = yaml.safe_load(f)

        # Convert deployment config to dataclass
        if "deployment" in config_data:
            deployment_data = config_data.pop("deployment")
            config_data["deployment"] = DeploymentConfig(**deployment_data)

        return cls(**config_data)

    @classmethod
    def from_env(cls) -> ServiceConfig:
        """Load configuration from environment variables."""
        return cls(
            database=DatabaseConfig(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=os.getenv("DB_NAME", "marty"),
                username=os.getenv("DB_USER", "marty"),
                password=os.getenv("DB_PASSWORD", ""),
            ),
            security=SecurityConfig(
                encryption_key=os.getenv("ENCRYPTION_KEY", ""),
                jwt_secret=os.getenv("JWT_SECRET", ""),
                cors_origins=(
                    os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
                ),
            ),
            pkd=PKDConfig(
                base_url=os.getenv("PKD_BASE_URL", "http://localhost:8000"),
            ),
            monitoring=MonitoringConfig(
                enable_metrics=os.getenv("ENABLE_METRICS", "true").lower() == "true",
                jaeger_endpoint=os.getenv("JAEGER_ENDPOINT", ""),
                log_level=os.getenv("LOG_LEVEL", "INFO"),
            ),
            trust=TrustConfig(
                policy=os.getenv("TRUST_POLICY", "fail_closed"),
                cache_directory=os.getenv("TRUST_CACHE_DIR", "/var/cache/marty/trust"),
            ),
            key_rotation=KeyRotationConfig(
                auto_rotation=os.getenv("AUTO_ROTATION", "false").lower() == "true",
            ),
        )

    def save_to_file(self, config_path: Path | str) -> None:
        """Save configuration to YAML file."""
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and handle deployment dataclass
        config_dict = self.dict()
        if self.deployment:
            config_dict["deployment"] = {
                "environment": self.deployment.environment,
                "cluster_name": self.deployment.cluster_name,
                "namespace": self.deployment.namespace,
                "replica_count": self.deployment.replica_count,
                "resources": self.deployment.resources,
                "health_check_path": self.deployment.health_check_path,
                "readiness_check_path": self.deployment.readiness_check_path,
            }

        with open(config_path, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)


def get_config() -> ServiceConfig:
    """Get configuration from file or environment.

    Priority:
    1. MARTY_CONFIG_FILE environment variable
    2. ./config/production.yaml (if in production)
    3. ./config/development.yaml (default)
    4. Environment variables (fallback)
    """
    config_file = os.getenv("MARTY_CONFIG_FILE")

    if config_file:
        return ServiceConfig.from_file(config_file)

    # Try standard config locations
    environment = os.getenv("ENVIRONMENT", "development")
    config_path = Path(f"config/{environment}.yaml")

    if config_path.exists():
        return ServiceConfig.from_file(config_path)

    # Fallback to environment variables
    return ServiceConfig.from_env()
