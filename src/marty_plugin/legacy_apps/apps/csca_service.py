"""Dedicated entrypoint for the CSCA gRPC microservice."""

from __future__ import annotations

from apps.runtime import SERVICE_DEFINITIONS, serve_service

SERVICE_NAME = "csca-service"


def main() -> None:
    """Start the CSCA service."""
    serve_service(SERVICE_DEFINITIONS[SERVICE_NAME])


if __name__ == "__main__":
    main()
