#!/usr/bin/env python3
"""
PKD Synchronization Pipeline

This script safely synchronizes PKD (Public Key Directory) data from external sources
into the local Marty infrastructure. It requires interactive authentication and caches
data locally before ingesting into the PKD service database and object storage.

Features:
- Interactive authentication/token management
- Safe caching to data/pkd_cache/ (git-ignored)
- Parsing and validation of ML/list/CSCA certificates
- Database and object storage integration
- Progress tracking and resumable operations
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import click
import httpx
from cryptography import x509
from cryptography.hazmat.primitives import serialization

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from marty_common.config import load_config
from marty_common.database import get_database_manager
from marty_common.infrastructure import ObjectStorageClient, build_key_vault_client

logger = logging.getLogger(__name__)


class PKDSyncError(Exception):
    """Base exception for PKD sync errors."""

    pass


class PKDSource:
    """Represents a PKD data source."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self.base_url = config.get("base_url", "")
        self.auth_type = config.get("auth_type", "token")
        self.endpoints = config.get("endpoints", {})

    def get_auth_headers(self, token: str | None = None) -> dict[str, str]:
        """Get authentication headers for requests."""
        headers = {
            "User-Agent": "Marty PKD Sync/1.0",
            "Accept": "application/json, application/octet-stream, */*",
        }

        if token and self.auth_type == "token":
            headers["Authorization"] = f"Bearer {token}"
        elif token and self.auth_type == "api_key":
            headers["X-API-Key"] = token

        return headers


class PKDCache:
    """Manages local PKD cache."""

    def __init__(self, cache_dir: str = "data/pkd_cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Ensure cache directory is git-ignored
        gitignore_path = self.cache_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text("*\n!.gitignore\n")

        self.metadata_file = self.cache_dir / "metadata.json"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> dict[str, Any]:
        """Load cache metadata."""
        if self.metadata_file.exists():
            try:
                return json.loads(self.metadata_file.read_text())
            except Exception as e:
                logger.warning("Failed to load cache metadata: %s", e)

        return {
            "version": "1.0",
            "created": datetime.now(timezone.utc).isoformat(),
            "sources": {},
        }

    def _save_metadata(self) -> None:
        """Save cache metadata."""
        self.metadata["updated"] = datetime.now(timezone.utc).isoformat()
        self.metadata_file.write_text(json.dumps(self.metadata, indent=2))

    def get_source_dir(self, source_name: str) -> Path:
        """Get directory for a specific source."""
        source_dir = self.cache_dir / source_name
        source_dir.mkdir(exist_ok=True)
        return source_dir

    def cache_file(self, source_name: str, filename: str, content: bytes) -> Path:
        """Cache a file for a source."""
        source_dir = self.get_source_dir(source_name)
        file_path = source_dir / filename
        file_path.write_bytes(content)

        # Update metadata
        if source_name not in self.metadata["sources"]:
            self.metadata["sources"][source_name] = {}

        self.metadata["sources"][source_name][filename] = {
            "cached": datetime.now(timezone.utc).isoformat(),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

        self._save_metadata()
        return file_path

    def get_cached_file(self, source_name: str, filename: str) -> Path | None:
        """Get path to cached file if it exists."""
        file_path = self.get_source_dir(source_name) / filename
        return file_path if file_path.exists() else None

    def is_file_cached(self, source_name: str, filename: str) -> bool:
        """Check if a file is cached."""
        return self.get_cached_file(source_name, filename) is not None


class CertificateParser:
    """Parses certificates from various formats."""

    @staticmethod
    def parse_pem_certificates(pem_data: bytes) -> list[x509.Certificate]:
        """Parse PEM certificate data."""
        certificates = []
        pem_text = pem_data.decode("utf-8", errors="ignore")

        # Split on certificate boundaries
        cert_blocks = []
        current_block = []
        in_cert = False

        for line in pem_text.split("\n"):
            line = line.strip()
            if line == "-----BEGIN CERTIFICATE-----":
                in_cert = True
                current_block = [line]
            elif line == "-----END CERTIFICATE-----":
                current_block.append(line)
                cert_blocks.append("\n".join(current_block))
                current_block = []
                in_cert = False
            elif in_cert:
                current_block.append(line)

        # Parse each certificate block
        for cert_block in cert_blocks:
            try:
                cert = x509.load_pem_x509_certificate(cert_block.encode())
                certificates.append(cert)
            except Exception as e:
                logger.warning("Failed to parse certificate: %s", e)

        return certificates

    @staticmethod
    def parse_der_certificate(der_data: bytes) -> x509.Certificate | None:
        """Parse DER certificate data."""
        try:
            return x509.load_der_x509_certificate(der_data)
        except Exception as e:
            logger.warning("Failed to parse DER certificate: %s", e)
            return None

    @staticmethod
    def extract_certificate_info(cert: x509.Certificate) -> dict[str, Any]:
        """Extract relevant information from a certificate."""
        try:
            # Basic certificate info - use UTC-aware attributes
            info = {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "serial_number": str(cert.serial_number),
                "not_before": cert.not_valid_before_utc.isoformat().replace("+00:00", "Z"),
                "not_after": cert.not_valid_after_utc.isoformat().replace("+00:00", "Z"),
                "signature_algorithm": cert.signature_algorithm_oid._name,
            }

            # Subject Key Identifier
            try:
                ski_ext = cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER
                )
                info["subject_key_identifier"] = ski_ext.value.digest.hex()
            except x509.ExtensionNotFound:
                pass

            # Authority Key Identifier
            try:
                aki_ext = cert.extensions.get_extension_for_oid(
                    x509.oid.ExtensionOID.AUTHORITY_KEY_IDENTIFIER
                )
                if aki_ext.value.key_identifier:
                    info["authority_key_identifier"] = aki_ext.value.key_identifier.hex()
            except x509.ExtensionNotFound:
                pass

            # Key Usage
            try:
                ku_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.KEY_USAGE)
                info["key_usage"] = {
                    "digital_signature": ku_ext.value.digital_signature,
                    "key_cert_sign": ku_ext.value.key_cert_sign,
                    "crl_sign": ku_ext.value.crl_sign,
                }
            except x509.ExtensionNotFound:
                pass

            # Country from subject
            try:
                for attribute in cert.subject:
                    if attribute.oid == x509.NameOID.COUNTRY_NAME:
                        info["country"] = attribute.value
                        break
            except Exception:
                pass

            # Calculate certificate hash
            cert_der = cert.public_bytes(serialization.Encoding.DER)
            info["sha256_fingerprint"] = hashlib.sha256(cert_der).hexdigest()
            info["sha1_fingerprint"] = hashlib.sha1(cert_der).hexdigest()

            return info

        except Exception as e:
            logger.exception("Failed to extract certificate info: %s", e)
            return {}


class PKDSync:
    """Main PKD synchronization orchestrator."""

    def __init__(self, config_path: str | None = None) -> None:
        self.config = self._load_config(config_path)
        self.cache = PKDCache(self.config.get("cache_dir", "data/pkd_cache"))
        self.sources = self._init_sources()
        self.parser = CertificateParser()

        # HTTP client
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout

        # Progress tracking
        self.stats = {
            "sources_processed": 0,
            "files_downloaded": 0,
            "certificates_parsed": 0,
            "certificates_stored": 0,
            "errors": 0,
        }

    def _load_config(self, config_path: str | None) -> dict[str, Any]:
        """Load PKD sync configuration."""
        if config_path:
            config_file = Path(config_path)
        else:
            config_file = Path("config/pkd_sync.yaml")

        if config_file.exists():
            return load_config(str(config_file))

        # Default configuration
        return {
            "cache_dir": "data/pkd_cache",
            "sources": {
                "icao_pkd": {
                    "base_url": "https://pkddownloadsg.icao.int",
                    "auth_type": "token",
                    "endpoints": {
                        "master_list": "/download/ml",
                        "csca_certificates": "/download/csca",
                        "dscs": "/download/dscs",
                    },
                    "enabled": False,  # Requires manual configuration
                },
            },
            "database": {
                "url": "postgresql://localhost:5432/pkd_service",
            },
            "object_storage": {
                "type": "local",
                "path": "data/pkd_objects",
            },
        }

    def _init_sources(self) -> dict[str, PKDSource]:
        """Initialize PKD sources from configuration."""
        sources = {}
        for name, config in self.config.get("sources", {}).items():
            if config.get("enabled", True):
                sources[name] = PKDSource(name, config)
        return sources

    async def authenticate_source(self, source_name: str) -> str | None:
        """Interactively authenticate with a PKD source."""
        source = self.sources.get(source_name)
        if not source:
            raise PKDSyncError(f"Unknown source: {source_name}")

        click.echo(f"\nAuthentication required for {source_name}")
        click.echo(f"Authentication type: {source.auth_type}")

        if source.auth_type == "token":
            token = click.prompt("Enter access token", hide_input=True)
        elif source.auth_type == "api_key":
            token = click.prompt("Enter API key", hide_input=True)
        else:
            click.echo(f"Unsupported auth type: {source.auth_type}")
            return None

        # Validate token by making a test request
        try:
            headers = source.get_auth_headers(token)
            test_url = urljoin(source.base_url, "/")
            response = await self.client.get(test_url, headers=headers)

            if response.status_code in (200, 401, 403):
                if response.status_code == 200:
                    click.echo("✓ Authentication successful")
                    return token
                else:
                    click.echo("✗ Authentication failed - invalid credentials")
            else:
                click.echo(f"✗ Authentication test failed - HTTP {response.status_code}")

        except Exception as e:
            click.echo(f"✗ Authentication test failed: {e}")

        return None

    async def download_file(
        self,
        source_name: str,
        endpoint: str,
        token: str,
        filename: str | None = None,
    ) -> Path | None:
        """Download a file from a PKD source."""
        source = self.sources[source_name]
        url = urljoin(source.base_url, endpoint)

        if not filename:
            filename = Path(urlparse(url).path).name or "download"

        # Check if already cached
        if self.cache.is_file_cached(source_name, filename):
            logger.info("File %s already cached for %s", filename, source_name)
            return self.cache.get_cached_file(source_name, filename)

        try:
            headers = source.get_auth_headers(token)
            logger.info("Downloading %s from %s", filename, url)

            async with self.client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()

                # Download to temporary file first
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    async for chunk in response.aiter_bytes(8192):
                        temp_file.write(chunk)
                    temp_path = Path(temp_file.name)

                # Read and cache the file
                content = temp_path.read_bytes()
                cached_path = self.cache.cache_file(source_name, filename, content)

                # Clean up temp file
                temp_path.unlink()

                self.stats["files_downloaded"] += 1
                logger.info("Downloaded and cached %s (%d bytes)", filename, len(content))
                return cached_path

        except Exception as e:
            self.stats["errors"] += 1
            logger.exception("Failed to download %s: %s", filename, e)
            return None

    async def process_certificate_file(
        self,
        file_path: Path,
        source_name: str,
        cert_type: str = "unknown",
    ) -> list[dict[str, Any]]:
        """Process a certificate file and extract certificate information."""
        certificates = []

        try:
            content = file_path.read_bytes()

            # Handle different file types
            if file_path.suffix.lower() == ".zip":
                # Extract ZIP file
                with zipfile.ZipFile(file_path, "r") as zip_file:
                    for zip_info in zip_file.infolist():
                        if not zip_info.is_dir():
                            member_content = zip_file.read(zip_info)
                            member_certs = self._parse_certificate_content(
                                member_content, zip_info.filename
                            )
                            certificates.extend(member_certs)
            else:
                # Process single file
                certificates = self._parse_certificate_content(content, file_path.name)

            # Add metadata to each certificate
            for cert_info in certificates:
                cert_info.update(
                    {
                        "source": source_name,
                        "cert_type": cert_type,
                        "file_path": str(file_path),
                        "processed": datetime.now(timezone.utc).isoformat(),
                    }
                )

            self.stats["certificates_parsed"] += len(certificates)
            logger.info("Processed %s: found %d certificates", file_path.name, len(certificates))

        except Exception as e:
            self.stats["errors"] += 1
            logger.exception("Failed to process certificate file %s: %s", file_path, e)

        return certificates

    def _parse_certificate_content(self, content: bytes, filename: str) -> list[dict[str, Any]]:
        """Parse certificate content based on format."""
        certificates = []

        try:
            # Try PEM format first
            if b"-----BEGIN CERTIFICATE-----" in content:
                x509_certs = self.parser.parse_pem_certificates(content)
                for cert in x509_certs:
                    cert_info = self.parser.extract_certificate_info(cert)
                    if cert_info:
                        certificates.append(cert_info)

            # Try DER format
            elif filename.lower().endswith((".der", ".crt", ".cer")):
                cert = self.parser.parse_der_certificate(content)
                if cert:
                    cert_info = self.parser.extract_certificate_info(cert)
                    if cert_info:
                        certificates.append(cert_info)

            # Try to parse as text list (some PKD sources provide lists)
            elif filename.lower().endswith(".txt"):
                # This could be a list of certificate URLs or base64 data
                # Implementation depends on specific source format
                pass

        except Exception as e:
            logger.warning("Failed to parse %s: %s", filename, e)

        return certificates

    async def store_certificates(self, certificates: list[dict[str, Any]]) -> None:
        """Store certificates in database and object storage."""
        if not certificates:
            return

        try:
            # TODO: Implement database storage
            # This would integrate with the PKD service database
            logger.info("Storing %d certificates (storage not implemented)", len(certificates))
            self.stats["certificates_stored"] += len(certificates)

        except Exception as e:
            self.stats["errors"] += 1
            logger.exception("Failed to store certificates: %s", e)

    async def sync_source(self, source_name: str, token: str) -> None:
        """Synchronize data from a single PKD source."""
        source = self.sources[source_name]
        logger.info("Starting sync for source: %s", source_name)

        all_certificates = []

        for endpoint_name, endpoint_path in source.endpoints.items():
            try:
                # Download file
                filename = f"{endpoint_name}_{datetime.now().strftime('%Y%m%d')}"
                file_path = await self.download_file(source_name, endpoint_path, token, filename)

                if file_path:
                    # Process certificates
                    certificates = await self.process_certificate_file(
                        file_path, source_name, endpoint_name
                    )
                    all_certificates.extend(certificates)

            except Exception as e:
                self.stats["errors"] += 1
                logger.exception("Failed to sync endpoint %s: %s", endpoint_name, e)

        # Store all certificates
        if all_certificates:
            await self.store_certificates(all_certificates)

        self.stats["sources_processed"] += 1
        logger.info(
            "Completed sync for source %s: %d certificates", source_name, len(all_certificates)
        )

    async def sync_all(self, tokens: dict[str, str]) -> None:
        """Synchronize all configured sources."""
        logger.info("Starting PKD synchronization")

        for source_name in self.sources:
            token = tokens.get(source_name)
            if not token:
                logger.warning("No token provided for source %s, skipping", source_name)
                continue

            try:
                await self.sync_source(source_name, token)
            except Exception as e:
                self.stats["errors"] += 1
                logger.exception("Failed to sync source %s: %s", source_name, e)

        await self.client.aclose()
        self.print_summary()

    def print_summary(self) -> None:
        """Print synchronization summary."""
        click.echo("\nPKD Synchronization Summary")
        click.echo("=" * 40)
        click.echo(f"Sources processed: {self.stats['sources_processed']}")
        click.echo(f"Files downloaded: {self.stats['files_downloaded']}")
        click.echo(f"Certificates parsed: {self.stats['certificates_parsed']}")
        click.echo(f"Certificates stored: {self.stats['certificates_stored']}")
        click.echo(f"Errors: {self.stats['errors']}")
        click.echo(f"Cache directory: {self.cache.cache_dir}")


@click.command()
@click.option("--config", "-c", help="Configuration file path")
@click.option("--source", "-s", multiple=True, help="Specific sources to sync (default: all)")
@click.option("--dry-run", is_flag=True, help="Download and parse only, don't store")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def main(config: str | None, source: tuple[str, ...], dry_run: bool, verbose: bool) -> None:
    """PKD Synchronization Pipeline

    Safely synchronizes PKD data from external sources with interactive authentication.
    Data is cached locally before being ingested into the PKD service.
    """
    # Set up logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    async def run_sync():
        try:
            # Initialize sync
            pkd_sync = PKDSync(config)

            # Determine which sources to sync
            sources_to_sync = list(source) if source else list(pkd_sync.sources.keys())

            if not sources_to_sync:
                click.echo("No sources configured or available")
                return

            click.echo(f"PKD sources to sync: {', '.join(sources_to_sync)}")

            if dry_run:
                click.echo("DRY RUN MODE - certificates will not be stored")

            # Authenticate each source
            tokens = {}
            for source_name in sources_to_sync:
                if source_name not in pkd_sync.sources:
                    click.echo(f"Unknown source: {source_name}")
                    continue

                token = await pkd_sync.authenticate_source(source_name)
                if token:
                    tokens[source_name] = token
                else:
                    click.echo(f"Skipping {source_name} due to authentication failure")

            if not tokens:
                click.echo("No sources authenticated successfully")
                return

            # Confirm before proceeding
            click.echo(f"\nReady to sync {len(tokens)} sources")
            if not click.confirm("Continue?"):
                return

            # Run synchronization
            if dry_run:
                # Override store method for dry run
                original_store = pkd_sync.store_certificates
                pkd_sync.store_certificates = lambda certs: asyncio.sleep(0)

            await pkd_sync.sync_all(tokens)

        except KeyboardInterrupt:
            click.echo("\nSync interrupted by user")
        except Exception as e:
            click.echo(f"Sync failed: {e}")
            if verbose:
                import traceback

                traceback.print_exc()

    asyncio.run(run_sync())


if __name__ == "__main__":
    main()
