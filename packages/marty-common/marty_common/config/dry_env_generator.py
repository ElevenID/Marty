"""
DRY Environment Configuration Generator for Marty Platform.

This module generates environment-specific configurations using the centralized
service registry, eliminating duplication across environment files.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from marty_common.service_registry import ServiceDefinition, ServiceRegistry


class EnvironmentConfigGenerator:
    """Generate environment configurations using DRY principles."""

    # Base configuration templates
    BASE_SECURITY_CONFIG = {
        "grpc_tls": {
            "enabled": False,
            "mtls": False,
            "require_client_auth": False,
        },
        "auth": {
            "required": False,
            "jwt": {
                "enabled": False,
                "algorithm": "HS256",
            },
            "client_cert": {
                "enabled": False,
            },
        },
        "authz": {
            "enabled": False,
            "default_action": "allow",
        },
    }

    BASE_DATABASE_CONFIG = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 3600,
        "echo": False,
    }

    BASE_MONITORING_CONFIG = {
        "metrics": {
            "enabled": True,
            "port_offset": 1000,
            "path": "/metrics",
        },
        "health": {
            "enabled": True,
            "port_offset": 1,
            "paths": {
                "health": "/health",
                "liveness": "/health/live",
                "readiness": "/health/ready",
            },
        },
        "tracing": {
            "enabled": True,
            "jaeger_endpoint": "http://localhost:14268",
        },
    }

    @classmethod
    def generate_service_env_vars(cls, environment: str = "development") -> dict[str, str]:
        """Generate environment variables for all services."""
        env_vars = {}

        # Generate port configurations for all services
        for service_name, service_def in ServiceRegistry.get_all_services().items():
            service_upper = service_name.upper().replace("-", "_")

            # Base service ports
            env_vars[f"{service_upper}_PORT"] = str(service_def.base_port)
            env_vars[f"{service_upper}_GRPC_PORT"] = str(service_def.grpc_port)
            env_vars[f"{service_upper}_HEALTH_PORT"] = str(service_def.health_port)
            env_vars[f"{service_upper}_METRICS_PORT"] = str(service_def.metrics_port)

            # Service hosts (environment dependent)
            if environment == "development":
                env_vars[f"{service_upper}_HOST"] = "localhost"
            elif environment == "production":
                env_vars[f"{service_upper}_HOST"] = service_name
            elif environment.startswith("k8s"):
                namespace = environment.split(":")[-1] if ":" in environment else "marty"
                env_vars[f"{service_upper}_HOST"] = f"{service_name}.{namespace}.svc.cluster.local"

        # Common environment variables
        env_vars.update(cls._get_common_env_vars(environment))

        return env_vars

    @classmethod
    def _get_common_env_vars(cls, environment: str) -> dict[str, str]:
        """Get common environment variables."""
        common_vars = {
            "ENVIRONMENT": environment,
            "LOG_LEVEL": "INFO" if environment == "production" else "DEBUG",
            "PYTHONPATH": "/app",
            "PYTHONUNBUFFERED": "1",
        }

        # Environment-specific variables
        if environment == "development":
            common_vars.update(
                {
                    "DEBUG": "true",
                    "RELOAD": "true",
                    "EXTERNAL_SERVICES_MOCK": "true",
                }
            )
        elif environment == "production":
            common_vars.update(
                {
                    "DEBUG": "false",
                    "RELOAD": "false",
                    "EXTERNAL_SERVICES_MOCK": "false",
                    "SECURE_HEADERS": "true",
                }
            )
        elif environment.startswith("test"):
            common_vars.update(
                {
                    "DEBUG": "true",
                    "MOCK_MODE": "true",
                    "TEST_DATABASE_URL": "sqlite:///test.db",
                }
            )

        return common_vars

    @classmethod
    def generate_docker_compose_config(cls, environment: str = "development") -> dict[str, Any]:
        """Generate Docker Compose configuration for all services."""
        services = {}
        networks = {"marty-network": {"driver": "bridge"}}
        volumes = {}

        # Generate service configurations
        for service_name, service_def in ServiceRegistry.get_all_services().items():
            service_config = {
                "build": {"context": "..", "dockerfile": f"docker/{service_name}.Dockerfile"},
                "container_name": service_name,
                "environment": cls._get_service_environment(service_name, environment),
                "ports": cls._get_service_ports(service_def),
                "networks": ["marty-network"],
                "depends_on": cls._get_service_dependencies(service_name),
                "healthcheck": cls._get_service_healthcheck(service_def),
                "restart": "unless-stopped" if environment == "production" else "no",
            }

            # Add volumes if needed
            if service_name in ["postgres", "redis", "kafka"]:
                volume_name = f"marty_{service_name}_data"
                service_config["volumes"] = [f"{volume_name}:/var/lib/{service_name}/data"]
                volumes[volume_name] = None

            services[service_name] = service_config

        return {
            "version": "3.8",
            "networks": networks,
            "services": services,
            "volumes": volumes,
        }

    @classmethod
    def _get_service_environment(cls, service_name: str, environment: str) -> list[str]:
        """Get environment variables for a specific service."""
        env_vars = []

        # Service-specific environment
        env_vars.extend(
            [
                f"SERVICE_NAME={service_name}",
                f"ENVIRONMENT={environment}",
            ]
        )

        # Add common environment variables
        common_env = cls._get_common_env_vars(environment)
        env_vars.extend([f"{k}={v}" for k, v in common_env.items()])

        return env_vars

    @classmethod
    def _get_service_ports(cls, service_def: ServiceDefinition) -> list[str]:
        """Get port mappings for a service."""
        return [
            f"{service_def.base_port}:{service_def.base_port}",
            f"{service_def.health_port}:{service_def.health_port}",
            f"{service_def.metrics_port}:{service_def.metrics_port}",
        ]

    @classmethod
    def _get_service_dependencies(cls, service_name: str) -> list[str]:
        """Get service dependencies."""
        # Common dependencies
        dependencies = ["postgres"]

        # Service-specific dependencies
        if service_name in ["mdoc-engine", "mdl-engine", "dtc-engine"]:
            dependencies.extend(["trust-anchor", "pkd-service"])

        if service_name == "ui-app":
            dependencies.extend(
                [
                    "trust-svc",
                    "csca-service",
                    "document-signer",
                    "passport-engine",
                    "mdl-engine",
                    "mdoc-engine",
                ]
            )

        return dependencies

    @classmethod
    def _get_service_healthcheck(cls, service_def: ServiceDefinition) -> dict[str, Any]:
        """Get healthcheck configuration for a service."""
        return {
            "test": ["CMD-SHELL", f"curl -f {service_def.health_endpoint} || exit 1"],
            "interval": "30s",
            "timeout": "10s",
            "retries": 3,
            "start_period": "40s",
        }

    @classmethod
    def generate_k8s_service_manifests(cls, namespace: str = "marty") -> dict[str, dict[str, Any]]:
        """Generate Kubernetes service manifests."""
        manifests = {}

        for service_name, service_def in ServiceRegistry.get_all_services().items():
            manifest = {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": service_name,
                    "namespace": namespace,
                    "labels": {
                        "app": service_name,
                        "component": "marty-platform",
                    },
                    "annotations": {
                        "prometheus.io/scrape": "true",
                        "prometheus.io/port": str(service_def.metrics_port),
                        "prometheus.io/path": "/metrics",
                    },
                },
                "spec": {
                    "type": "ClusterIP",
                    "ports": [
                        {
                            "name": "http",
                            "port": service_def.base_port,
                            "targetPort": service_def.base_port,
                            "protocol": "TCP",
                        },
                        {
                            "name": "health",
                            "port": service_def.health_port,
                            "targetPort": service_def.health_port,
                            "protocol": "TCP",
                        },
                        {
                            "name": "metrics",
                            "port": service_def.metrics_port,
                            "targetPort": service_def.metrics_port,
                            "protocol": "TCP",
                        },
                    ],
                    "selector": {
                        "app": service_name,
                    },
                },
            }

            manifests[service_name] = manifest

        return manifests

    @classmethod
    def write_env_file(cls, environment: str, output_path: Path | None = None) -> Path:
        """Write environment file to disk."""
        if output_path is None:
            output_path = Path(f".env.{environment}")

        env_vars = cls.generate_service_env_vars(environment)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# Generated environment configuration for {environment}\n")
            f.write("# Generated by Marty DRY Environment Config\n\n")

            # Group variables by service
            service_vars = {}
            common_vars = {}

            for key, value in env_vars.items():
                found_service = False
                for service_name in ServiceRegistry.get_all_services().keys():
                    service_upper = service_name.upper().replace("-", "_")
                    if key.startswith(service_upper + "_"):
                        if service_name not in service_vars:
                            service_vars[service_name] = {}
                        service_vars[service_name][key] = value
                        found_service = True
                        break

                if not found_service:
                    common_vars[key] = value

            # Write common variables first
            if common_vars:
                f.write("# === Common Configuration ===\n")
                for key, value in sorted(common_vars.items()):
                    f.write(f"{key}={value}\n")
                f.write("\n")

            # Write service-specific variables
            for service_name in sorted(service_vars.keys()):
                f.write(f"# === {service_name.upper()} Service ===\n")
                for key, value in sorted(service_vars[service_name].items()):
                    f.write(f"{key}={value}\n")
                f.write("\n")

        return output_path


# CLI functionality for generating configurations
def main():
    """CLI for generating environment configurations."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate DRY environment configurations")
    parser.add_argument(
        "environment", choices=["development", "production", "testing", "k8s:dev", "k8s:prod"]
    )
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="Output directory")
    parser.add_argument("--format", choices=["env", "docker-compose", "k8s"], default="env")

    args = parser.parse_args()

    generator = EnvironmentConfigGenerator()

    if args.format == "env":
        output_file = generator.write_env_file(
            args.environment, args.output_dir / f".env.{args.environment}"
        )
        print(f"Generated environment file: {output_file}")

    elif args.format == "docker-compose":
        import yaml

        config = generator.generate_docker_compose_config(args.environment)
        output_file = args.output_dir / f"docker-compose.{args.environment}.yml"
        with open(output_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"Generated Docker Compose file: {output_file}")

    elif args.format == "k8s":
        import yaml

        namespace = args.environment.split(":")[-1] if ":" in args.environment else "marty"
        manifests = generator.generate_k8s_service_manifests(namespace)

        for service_name, manifest in manifests.items():
            output_file = args.output_dir / f"{service_name}-service.yaml"
            with open(output_file, "w", encoding="utf-8") as f:
                yaml.dump(manifest, f, default_flow_style=False)
        print(f"Generated {len(manifests)} Kubernetes service manifests")


if __name__ == "__main__":
    main()
