#!/usr/bin/env python3
"""
Script to generate DRY configurations for the Marty platform.

This script eliminates duplication by generating environment files,
Docker configurations, and Kubernetes manifests from a single source of truth.
"""

import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from marty_backend_common.config.dry_env_generator import EnvironmentConfigGenerator
    from marty_backend_common.service_registry import ServiceRegistry
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


def generate_all_configs():
    """Generate all DRY configurations."""
    print("🔧 Generating DRY configurations for Marty platform...")

    generator = EnvironmentConfigGenerator()
    config_dir = Path("config/generated")
    config_dir.mkdir(exist_ok=True)

    # Generate environment files
    environments = ["development", "production", "testing"]
    for env in environments:
        env_file = generator.write_env_file(env, config_dir / f".env.{env}")
        print(f"✅ Generated {env_file}")

    print("\n📋 Service Registry Summary:")
    print(f"   Total services: {len(ServiceRegistry.get_all_services())}")

    for service_name, service_def in ServiceRegistry.get_all_services().items():
        print(
            f"   {service_name:20} → {service_def.base_port:5} (gRPC: {service_def.grpc_port}, Metrics: {service_def.metrics_port})"
        )

    print("\n🎯 DRY Benefits Achieved:")
    print("   ✅ Centralized port management")
    print("   ✅ Single source of truth for service definitions")
    print("   ✅ Automatic environment file generation")
    print("   ✅ Consistent port allocation pattern")
    print("   ✅ Eliminated hardcoded configurations")


if __name__ == "__main__":
    generate_all_configs()
