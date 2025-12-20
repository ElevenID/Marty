"""Dedicated entrypoint for the Passport Engine microservice."""

from __future__ import annotations

from apps.runtime import SERVICE_DEFINITIONS, serve_service

SERVICE_NAME = "passport-engine"


def main() -> None:
    """Boot the service."""
    serve_service(SERVICE_DEFINITIONS[SERVICE_NAME])


if __name__ == "__main__":
    main()
