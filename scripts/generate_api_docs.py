#!/usr/bin/env python3
"""
API Documentation Generator for Marty Platform

This script automatically generates comprehensive API documentation from all FastAPI
applications in the Marty platform, creating both OpenAPI specs and static HTML docs.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration for all FastAPI apps in the platform
FASTAPI_APPS = {
    "pkd_service": {
        "module_path": "src/pkd_service/app/main.py",
        "description": "ICAO PKD API for Public Key Directory management",
        "port": 8001,
    },
    "document_processing": {
        "module_path": "src/document_processing/app/main.py",
        "description": "Document Processing MRZ API for document verification",
        "port": 8080,
    },
    "ui_app": {
        "module_path": "src/ui_app/app.py",
        "description": "Marty Platform Web UI",
        "port": 8000,
    },
}

OUTPUT_DIR = PROJECT_ROOT / "docs" / "api"
STATIC_DIR = OUTPUT_DIR / "static"


def setup_output_directories() -> None:
    """Create output directories for API documentation."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "openapi").mkdir(exist_ok=True)
    logger.info(f"Created output directories: {OUTPUT_DIR}")


def import_fastapi_app(module_path: str, app_var: str) -> FastAPI:
    """
    Dynamically import a FastAPI application.

    Args:
        module_path: Python module path (e.g., 'pkd_service.app.main')
        app_var: Variable name of the FastAPI app in the module

    Returns:
        FastAPI application instance
    """
    try:
        module = __import__(module_path, fromlist=[app_var])
        app = getattr(module, app_var)
        if not isinstance(app, FastAPI):
            raise ValueError(f"{app_var} is not a FastAPI instance")
        return app
    except Exception as e:
        logger.error(f"Failed to import {module_path}:{app_var} - {e}")
        raise


def generate_openapi_spec(
    app: FastAPI, service_name: str, config: dict[str, Any]
) -> dict[str, Any]:
    """
    Generate OpenAPI specification for a FastAPI app.

    Args:
        app: FastAPI application instance
        service_name: Name of the service
        config: Service configuration

    Returns:
        OpenAPI specification as dictionary
    """
    try:
        # Generate OpenAPI spec with enhanced metadata
        openapi_spec = get_openapi(
            title=app.title or f"{service_name.title()} API",
            version=app.version or "1.0.0",
            description=config.get("description", app.description or ""),
            routes=app.routes,
            servers=[
                {"url": f"http://localhost:{config['port']}", "description": "Development server"},
                {"url": "https://api.marty.platform", "description": "Production server"},
            ],
        )

        # Add additional metadata
        openapi_spec["info"]["contact"] = {
            "name": "Marty Platform Team",
            "url": "https://github.com/ElevenID/Marty",
        }

        openapi_spec["info"]["license"] = {
            "name": "Proprietary",
        }

        # Add security schemes if not present
        if "components" not in openapi_spec:
            openapi_spec["components"] = {}

        if "securitySchemes" not in openapi_spec["components"]:
            openapi_spec["components"]["securitySchemes"] = {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API key for authentication",
                }
            }

        logger.info(f"Generated OpenAPI spec for {service_name}")
        return openapi_spec

    except Exception as e:
        logger.error(f"Failed to generate OpenAPI spec for {service_name}: {e}")
        raise


def save_openapi_specs(specs: dict[str, dict[str, Any]]) -> None:
    """
    Save OpenAPI specifications to files.

    Args:
        specs: Dictionary mapping service names to OpenAPI specs
    """
    openapi_dir = OUTPUT_DIR / "openapi"

    # Save individual service specs
    for service_name, spec in specs.items():
        # Save as JSON
        json_path = openapi_dir / f"{service_name}_openapi.json"
        with open(json_path, "w") as f:
            json.dump(spec, f, indent=2)
        logger.info(f"Saved OpenAPI JSON spec: {json_path}")

        # Save as YAML
        yaml_path = openapi_dir / f"{service_name}_openapi.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(spec, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved OpenAPI YAML spec: {yaml_path}")

    # Create combined spec
    combined_spec = create_combined_spec(specs)
    combined_json_path = openapi_dir / "marty_platform_combined_openapi.json"
    combined_yaml_path = openapi_dir / "marty_platform_combined_openapi.yaml"

    with open(combined_json_path, "w") as f:
        json.dump(combined_spec, f, indent=2)

    with open(combined_yaml_path, "w") as f:
        yaml.dump(combined_spec, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Saved combined OpenAPI specs: {combined_json_path}, {combined_yaml_path}")


def create_combined_spec(specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """
    Create a combined OpenAPI specification for all services.

    Args:
        specs: Dictionary mapping service names to OpenAPI specs

    Returns:
        Combined OpenAPI specification
    """
    combined = {
        "openapi": "3.0.2",
        "info": {
            "title": "Marty Platform API",
            "description": "Comprehensive API documentation for the Marty enterprise document platform",
            "version": "1.0.0",
            "contact": {
                "name": "Marty Platform Team",
                "url": "https://github.com/ElevenID/Marty",
            },
            "license": {"name": "Proprietary"},
        },
        "servers": [
            {"url": "http://localhost", "description": "Development environment"},
            {"url": "https://api.marty.platform", "description": "Production environment"},
        ],
        "paths": {},
        "components": {"schemas": {}, "securitySchemes": {}},
        "tags": [],
    }

    service_tags = []

    for service_name, spec in specs.items():
        # Add service tag
        service_tag = {
            "name": service_name,
            "description": spec.get("info", {}).get("description", f"{service_name} service"),
        }
        service_tags.append(service_tag)

        # Merge paths with service prefix
        for path, path_spec in spec.get("paths", {}).items():
            prefixed_path = f"/{service_name}{path}"

            # Add service tag to all operations
            for method, operation in path_spec.items():
                if isinstance(operation, dict) and "tags" in operation:
                    operation["tags"] = [service_name] + operation.get("tags", [])
                elif isinstance(operation, dict):
                    operation["tags"] = [service_name]

            combined["paths"][prefixed_path] = path_spec

        # Merge components
        if "components" in spec:
            if "schemas" in spec["components"]:
                combined["components"]["schemas"].update(spec["components"]["schemas"])
            if "securitySchemes" in spec["components"]:
                combined["components"]["securitySchemes"].update(
                    spec["components"]["securitySchemes"]
                )

    combined["tags"] = service_tags
    return combined


def generate_html_docs() -> None:
    """Generate static HTML documentation using Redoc."""
    try:
        # Generate docs for each service
        openapi_dir = OUTPUT_DIR / "openapi"

        for service_name in FASTAPI_APPS.keys():
            json_spec_path = openapi_dir / f"{service_name}_openapi.json"
            if json_spec_path.exists():
                html_path = STATIC_DIR / f"{service_name}_docs.html"
                generate_redoc_html(json_spec_path, html_path, f"{service_name.title()} API")

        # Generate combined docs
        combined_spec_path = openapi_dir / "marty_platform_combined_openapi.json"
        if combined_spec_path.exists():
            combined_html_path = STATIC_DIR / "marty_platform_docs.html"
            generate_redoc_html(combined_spec_path, combined_html_path, "Marty Platform API")

        # Generate index page
        generate_index_page()

    except Exception as e:
        logger.error(f"Failed to generate HTML docs: {e}")
        raise


def generate_redoc_html(spec_path: Path, output_path: Path, title: str) -> None:
    """
    Generate Redoc HTML documentation from OpenAPI spec.

    Args:
        spec_path: Path to OpenAPI JSON specification
        output_path: Path for output HTML file
        title: Title for the documentation
    """
    html_template = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
        body {{ margin: 0; padding: 0; }}
    </style>
</head>
<body>
    <redoc spec-url="../openapi/{spec_path.name}"></redoc>
    <script src="https://cdn.jsdelivr.net/npm/redoc@2.1.0/bundles/redoc.standalone.js"></script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html_template)
    logger.info(f"Generated Redoc HTML: {output_path}")


def generate_index_page() -> None:
    """Generate an index page for all API documentation."""
    services_list = ""
    for service_name, config in FASTAPI_APPS.items():
        services_list += f"""
        <div class="service">
            <h3>{service_name.title()} API</h3>
            <p>{config['description']}</p>
            <p>
                <a href="static/{service_name}_docs.html">Documentation</a> |
                <a href="openapi/{service_name}_openapi.json">OpenAPI JSON</a> |
                <a href="openapi/{service_name}_openapi.yaml">OpenAPI YAML</a>
            </p>
        </div>"""

    index_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Marty Platform API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #2c3e50; }}
        .service {{ border: 1px solid #ddd; padding: 20px; margin: 20px 0; border-radius: 5px; }}
        .service h3 {{ color: #3498db; margin-top: 0; }}
        a {{ color: #3498db; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .combined {{ background-color: #f8f9fa; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Marty Platform API Documentation</h1>
        <p>Enterprise-grade microservices platform for secure digital identity document management.</p>

        <div class="service combined">
            <h3>🌟 Combined Platform API</h3>
            <p>Complete API documentation for all Marty services in one place.</p>
            <p>
                <a href="static/marty_platform_docs.html">📖 View Combined Documentation</a> |
                <a href="openapi/marty_platform_combined_openapi.json">📄 OpenAPI JSON</a> |
                <a href="openapi/marty_platform_combined_openapi.yaml">📄 OpenAPI YAML</a>
            </p>
        </div>

        <h2>Individual Services</h2>
        {services_list}

        <hr>
        <p><small>Generated automatically by the Marty Platform API documentation generator.</small></p>
    </div>
</body>
</html>"""

    index_path = OUTPUT_DIR / "index.html"
    with open(index_path, "w") as f:
        f.write(index_html)
    logger.info(f"Generated index page: {index_path}")


def main() -> None:
    """Main function to generate all API documentation."""
    try:
        logger.info("🚀 Starting API documentation generation for Marty Platform")

        # Setup output directories
        setup_output_directories()

        # Generate OpenAPI specs for all services
        specs = {}

        for service_name, config in FASTAPI_APPS.items():
            try:
                logger.info(f"Processing {service_name}...")
                app = import_fastapi_app(config["module"], config["app_var"])
                spec = generate_openapi_spec(app, service_name, config)
                specs[service_name] = spec
                logger.info(f"✅ Successfully processed {service_name}")
            except Exception as e:
                logger.warning(f"⚠️  Skipping {service_name} due to error: {e}")
                continue

        if not specs:
            logger.error("❌ No API specifications were generated successfully")
            sys.exit(1)

        # Save OpenAPI specifications
        save_openapi_specs(specs)

        # Generate HTML documentation
        generate_html_docs()

        logger.info("✅ API documentation generation completed successfully!")
        logger.info(f"📖 Documentation available at: {OUTPUT_DIR / 'index.html'}")

    except Exception as e:
        logger.error(f"❌ API documentation generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
