"""
Data loaders for scraped test data.

This module provides utilities to load real data from scraped sources
for use in testing, providing higher confidence in implementation.
Falls back gracefully when scraped data is not available, using
realistic generated passport data via PassportGenerator.
"""

from __future__ import annotations

import json
import logging
import secrets
import sys
from pathlib import Path
from typing import Any

# Add project root to path for accessing generators
project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

try:
    from tests.generators.passport_generator import PassportGenerator

    PASSPORT_GENERATOR_AVAILABLE = True
except ImportError:
    PASSPORT_GENERATOR_AVAILABLE = False
    logging.warning("PassportGenerator not available, using basic fallback data")

logger = logging.getLogger(__name__)


class TestDataLoader:
    """Loads scraped test data and generated test data with graceful fallbacks."""

    def __init__(self, data_root: Path | None = None):
        """Initialize with data root directory."""
        if data_root is None:
            # Default to scraped data directory within tests/data
            self.data_root = Path(__file__).parents[1] / "data" / "scraped"
        else:
            self.data_root = Path(data_root)

        # Also check for generated data directory
        self.generated_data_root = Path(__file__).parents[1] / "data" / "generated"

        # Check if scraped data is available
        self.has_scraped_data = self.data_root.exists()
        if not self.has_scraped_data:
            logger.warning("Scraped data directory not found: %s", self.data_root)

        # Check if generated data is available
        self.has_generated_data = self.generated_data_root.exists()
        if self.has_generated_data:
            logger.info("Generated test data available at: %s", self.generated_data_root)
        else:
            logger.info("Generated test data not found at: %s", self.generated_data_root)

        # Initialize PassportGenerator for realistic fallback data
        self._passport_generator = None
        if PASSPORT_GENERATOR_AVAILABLE:
            try:
                self._passport_generator = PassportGenerator()
                logger.info("PassportGenerator initialized for realistic fallback data")
            except (ImportError, AttributeError, TypeError) as e:
                logger.warning("Failed to initialize PassportGenerator: %s", e)
                self._passport_generator = None

    def _get_fallback_passport_data(self) -> dict[str, Any]:
        """Provide fallback passport data when scraped data is not available."""
        if self._passport_generator is not None:
            return self._generate_realistic_passport_data()

        # Basic fallback if PassportGenerator is not available
        return {
            "passport_number": "P12345678",
            "issue_date": "2024-01-01",
            "expiry_date": "2034-01-01",
            "data_groups": {
                "DG1": "MRZ-DATA-FALLBACK",
                "DG2": "PHOTO-DATA-FALLBACK",
                "DG3": "FINGERPRINT-DATA-FALLBACK",
                "DG4": "IRIS-DATA-FALLBACK",
            },
            "sod": "FALLBACK_SOD_DATA",
            "_is_fallback": True,
        }

    def _generate_realistic_passport_data(self) -> dict[str, Any]:
        """Generate realistic passport data using PassportGenerator."""
        if self._passport_generator is None:
            logger.warning("PassportGenerator not available, using basic fallback")
            return self._get_basic_fallback_data()

        try:
            # Define variations for different passport types
            passport_variations = [
                {
                    "issuing_country": "USA",
                    "nationality": "USA",
                    "name": "SMITH",
                    "surname": "JOHN",
                    "sex": "M",
                    "passport_num": secrets.token_hex(4).upper()[:9],
                    "birth_date": "900101",
                    "expiry_date": "280101",
                },
                {
                    "issuing_country": "GBR",
                    "nationality": "GBR",
                    "name": "JONES",
                    "surname": "MARY",
                    "sex": "F",
                    "passport_num": secrets.token_hex(4).upper()[:9],
                    "birth_date": "851215",
                    "expiry_date": "291215",
                },
                {
                    "issuing_country": "CAN",
                    "nationality": "CAN",
                    "name": "BROWN",
                    "surname": "DAVID",
                    "sex": "M",
                    "passport_num": secrets.token_hex(4).upper()[:9],
                    "birth_date": "870630",
                    "expiry_date": "310630",
                },
                {
                    "issuing_country": "AUS",
                    "nationality": "AUS",
                    "name": "WILLIAMS",
                    "surname": "SARAH",
                    "sex": "F",
                    "passport_num": secrets.token_hex(4).upper()[:9],
                    "birth_date": "920410",
                    "expiry_date": "320410",
                },
            ]

            # Select a random variation
            variation = passport_variations[secrets.randbelow(len(passport_variations))]

            # Generate realistic passport data using PassportGenerator
            raw_passport_data = self._passport_generator.generate_passport(**variation)

            # Convert to format matching scraped data structure
            prefix = "P"  # Default to Personal passport
            file_passport_num = f"{prefix}{variation['passport_num']}"

            # Convert raw data to expected format
            converted_data = {
                "passport_number": file_passport_num,
                "issue_date": "1990-01-15",  # Default dates
                "expiry_date": "2030-01-15",
                "data_groups": raw_passport_data.get("data_groups", {}),
                "sod": raw_passport_data.get("sod", f"GENERATED_SOD_{secrets.token_hex(16)}"),
                "_generated_by": "PassportGenerator",
                "_is_fallback": True,
                "_is_realistic": True,
                "_country": variation["issuing_country"],
                "_type": prefix,
            }

            # Ensure data_groups has the expected structure
            if "mrz" in raw_passport_data:
                converted_data["data_groups"]["DG1"] = raw_passport_data["mrz"]

            # Add placeholder data for other data groups if not present
            dg_defaults = {
                "DG2": None,  # Photo data
                "DG3": f"FINGERPRINT-DATA-{file_passport_num}",
                "DG4": f"IRIS-DATA-{file_passport_num}",
            }

            for dg_key, default_value in dg_defaults.items():
                if dg_key not in converted_data["data_groups"]:
                    converted_data["data_groups"][dg_key] = default_value

            logger.debug(
                "Generated realistic passport data for country: %s", variation["issuing_country"]
            )
        except (AttributeError, TypeError, KeyError) as e:
            logger.warning("Error generating realistic passport data: %s", e)
            return self._get_basic_fallback_data()
        else:
            return converted_data

    def _get_basic_fallback_data(self) -> dict[str, Any]:
        """Get basic hardcoded fallback data as last resort."""
        return {
            "passport_number": "P12345678",
            "issue_date": "2024-01-01",
            "expiry_date": "2034-01-01",
            "data_groups": {
                "DG1": "MRZ-DATA-FALLBACK",
                "DG2": "PHOTO-DATA-FALLBACK",
                "DG3": "FINGERPRINT-DATA-FALLBACK",
                "DG4": "IRIS-DATA-FALLBACK",
            },
            "sod": "FALLBACK_SOD_DATA",
            "_is_fallback": True,
        }

    def _generate_realistic_passport_collection(self, count: int = 5) -> list[dict[str, Any]]:
        """Generate a collection of realistic passport data using PassportGenerator."""
        if self._passport_generator is None:
            logger.warning("PassportGenerator not available, using basic fallback collection")
            return [self._get_basic_fallback_data()]

        try:
            # Generate multiple realistic passports with different countries and data
            passport_variations = [
                {
                    "issuing_country": "USA",
                    "nationality": "USA",
                    "name": "SMITH",
                    "surname": "JOHN",
                    "sex": "M",
                },
                {
                    "issuing_country": "GBR",
                    "nationality": "GBR",
                    "name": "JONES",
                    "surname": "MARY",
                    "sex": "F",
                },
                {
                    "issuing_country": "CAN",
                    "nationality": "CAN",
                    "name": "BROWN",
                    "surname": "DAVID",
                    "sex": "M",
                },
                {
                    "issuing_country": "AUS",
                    "nationality": "AUS",
                    "name": "WILLIAMS",
                    "surname": "SARAH",
                    "sex": "F",
                },
                {
                    "issuing_country": "FRA",
                    "nationality": "FRA",
                    "name": "MARTIN",
                    "surname": "PIERRE",
                    "sex": "M",
                },
                {
                    "issuing_country": "DEU",
                    "nationality": "DEU",
                    "name": "MULLER",
                    "surname": "ANNA",
                    "sex": "F",
                },
                {
                    "issuing_country": "JPN",
                    "nationality": "JPN",
                    "name": "TANAKA",
                    "surname": "HIROSHI",
                    "sex": "M",
                },
                {
                    "issuing_country": "ITA",
                    "nationality": "ITA",
                    "name": "ROSSI",
                    "surname": "MARIA",
                    "sex": "F",
                },
            ]

            passports = []
            max_count = min(count, len(passport_variations))

            for i in range(max_count):
                variation = passport_variations[i].copy()
                variation["passport_num"] = secrets.token_hex(4).upper()[:9]
                birth_date = f"{85 + i:02d}0{1 + (i % 12):02d}{10 + (i % 20):02d}"
                expiry_date = f"{28 + i:02d}0{1 + (i % 12):02d}{10 + (i % 20):02d}"
                variation["birth_date"] = birth_date
                variation["expiry_date"] = expiry_date

                passport_data = self._passport_generator.generate_passport(**variation)
                passport_data["_is_fallback"] = True
                passport_data["_generated_by"] = "PassportGenerator"
                passport_data["_collection_index"] = i

                passports.append(passport_data)

            logger.debug(
                "Generated realistic passport collection with %d passports", len(passports)
            )
        except (AttributeError, TypeError, KeyError) as e:
            logger.warning("Error generating realistic passport collection: %s", e)
            return [self._get_basic_fallback_data()]
        else:
            return passports

    def _load_json_file(self, file_path: Path) -> dict[str, Any] | None:
        """Safely load a JSON file, returning None on error."""
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to load JSON file: %s", file_path)
            return None

    def _get_random_passport_file(self, passport_files: list[Path]) -> Path | None:
        """Select a random passport file using secure random."""
        if not passport_files:
            return None
        return passport_files[secrets.randbelow(len(passport_files))]

    def load_passport_data(self, passport_number: str | None = None) -> dict[str, Any]:
        """Load passport data from scraped/generated files or fallback data."""
        fallback = self._get_fallback_passport_data()

        if passport_number:
            # Look for specific passport in both scraped and generated data
            data = self._find_passport_by_number(passport_number)
            if data is not None:
                return data

            logger.warning(
                "Passport data for %s not found in any source, using fallback", passport_number
            )
            return fallback

        # Load random passport from combined sources
        all_passport_files = []

        # Collect scraped passport files
        if self.has_scraped_data:
            scraped_dir = self.data_root / "passport"
            if scraped_dir.exists():
                all_passport_files.extend(
                    [
                        ("scraped", f)
                        for f in scraped_dir.glob("*.json")
                        if not f.name.startswith("INVALID")
                    ]
                )

        # Collect generated passport files
        if self.has_generated_data:
            generated_dir = self.generated_data_root / "passport"
            if generated_dir.exists():
                all_passport_files.extend(
                    [
                        ("generated", f)
                        for f in generated_dir.glob("*.json")
                        if not f.name.startswith("INVALID")
                    ]
                )

        if all_passport_files:
            source_type, random_file = all_passport_files[
                secrets.randbelow(len(all_passport_files))
            ]
            data = self._load_json_file(random_file)
            if data is not None:
                data["_source_type"] = source_type
                return data

        logger.info("No passport data files found, using fallback generation")
        return fallback

    def _find_passport_by_number(self, passport_number: str) -> dict[str, Any] | None:
        """Find a specific passport by number in both scraped and generated data."""
        # Check scraped data first
        if self.has_scraped_data:
            scraped_file = self.data_root / "passport" / f"{passport_number}.json"
            if scraped_file.exists():
                data = self._load_json_file(scraped_file)
                if data is not None:
                    data["_source_type"] = "scraped"
                    return data

        # Check generated data
        if self.has_generated_data:
            generated_file = self.generated_data_root / "passport" / f"{passport_number}.json"
            if generated_file.exists():
                data = self._load_json_file(generated_file)
                if data is not None:
                    data["_source_type"] = "generated"
                    return data

        return None

    def load_all_passport_data(self) -> list[dict[str, Any]]:
        """Load all passport data files from both scraped and generated sources."""
        passport_data = []

        # Load scraped data
        if self.has_scraped_data:
            scraped_data = self._load_scraped_passport_data()
            passport_data.extend(scraped_data)
            logger.info("Loaded %d scraped passport data files", len(scraped_data))

        # Load generated data
        if self.has_generated_data:
            generated_data = self._load_generated_passport_data()
            passport_data.extend(generated_data)
            logger.info("Loaded %d generated passport data files", len(generated_data))

        # If no data available, use fallback generation
        if not passport_data:
            logger.warning("No passport data available, using fallback generation")
            return self._generate_realistic_passport_collection()

        logger.info("Total passport data loaded: %d files", len(passport_data))
        return passport_data

    def load_invalid_passport_data(self) -> list[dict[str, Any]]:
        """Load invalid passport data from both scraped and generated sources."""
        invalid_data = []

        # Load invalid scraped data
        if self.has_scraped_data:
            scraped_invalid = self._load_scraped_invalid_passport_data()
            invalid_data.extend(scraped_invalid)

        # Load invalid generated data
        if self.has_generated_data:
            generated_invalid = self._load_generated_invalid_passport_data()
            invalid_data.extend(generated_invalid)

        return invalid_data

    def _load_scraped_passport_data(self) -> list[dict[str, Any]]:
        """Load passport data from scraped data directory."""
        passport_data = []
        passport_dir = self.data_root / "passport"

        if not passport_dir.exists():
            return passport_data

        try:
            for passport_file in passport_dir.glob("*.json"):
                # Skip invalid passports unless specifically requested
                if passport_file.name.startswith("INVALID"):
                    continue

                data = self._load_json_file(passport_file)
                if data is not None:
                    data["_source_file"] = passport_file.name
                    data["_source_type"] = "scraped"
                    passport_data.append(data)
        except OSError:
            logger.exception("Error scanning scraped passport directory")

        return passport_data

    def _load_generated_passport_data(self) -> list[dict[str, Any]]:
        """Load passport data from generated data directory."""
        passport_data = []
        passport_dir = self.generated_data_root / "passport"

        if not passport_dir.exists():
            return passport_data

        try:
            for passport_file in passport_dir.glob("*.json"):
                # Skip invalid passports unless specifically requested
                if passport_file.name.startswith("INVALID"):
                    continue

                data = self._load_json_file(passport_file)
                if data is not None:
                    data["_source_file"] = passport_file.name
                    data["_source_type"] = "generated"
                    passport_data.append(data)
        except OSError:
            logger.exception("Error scanning generated passport directory")

        return passport_data

    def _load_scraped_invalid_passport_data(self) -> list[dict[str, Any]]:
        """Load invalid passport data from scraped data directory."""
        invalid_data = []
        passport_dir = self.data_root / "passport"

        if not passport_dir.exists():
            return invalid_data

        try:
            for passport_file in passport_dir.glob("INVALID*.json"):
                data = self._load_json_file(passport_file)
                if data is not None:
                    data["_source_file"] = passport_file.name
                    data["_source_type"] = "scraped_invalid"
                    invalid_data.append(data)
        except OSError:
            logger.exception("Error loading scraped invalid passport data")

        return invalid_data

    def _load_generated_invalid_passport_data(self) -> list[dict[str, Any]]:
        """Load invalid passport data from generated data directory."""
        invalid_data = []
        passport_dir = self.generated_data_root / "passport"

        if not passport_dir.exists():
            return invalid_data

        try:
            for passport_file in passport_dir.glob("INVALID*.json"):
                data = self._load_json_file(passport_file)
                if data is not None:
                    data["_source_file"] = passport_file.name
                    data["_source_type"] = "generated_invalid"
                    invalid_data.append(data)
        except OSError:
            logger.exception("Error loading generated invalid passport data")

        return invalid_data

    def load_csca_lifecycle_data(self) -> dict[str, Any]:
        """Load CSCA certificate lifecycle event data or return fallback."""
        fallback_data = {
            "certificate_events": {
                "cert_fallback_001": [
                    {
                        "timestamp": "2024-01-01T00:00:00.000000+00:00",
                        "event_type": "created",
                        "days_remaining": 365,
                    }
                ]
            },
            "_is_fallback": True,
        }

        if not self.has_scraped_data:
            logger.info("Using fallback CSCA lifecycle data")
            return fallback_data

        csca_file = self.data_root / "csca" / "lifecycle_events.json"

        if csca_file.exists():
            data = self._load_json_file(csca_file)
            return data if data is not None else fallback_data

        logger.warning("CSCA lifecycle data not found, using fallback")
        return fallback_data

    def load_trust_store_data(self) -> dict[str, Any]:
        """Load trust store configuration data or return fallback."""
        fallback_data = {
            "trusted_entities": {
                "csca-service": True,
                "document-signer": True,
                "inspection-system": True,
                "passport-engine": True,
                "test-entity": True,
            },
            "revoked_entities": [],
            "_is_fallback": True,
        }

        if not self.has_scraped_data:
            logger.info("Using fallback trust store data")
            return fallback_data

        trust_file = self.data_root / "trust_store.json"

        if trust_file.exists():
            data = self._load_json_file(trust_file)
            return data if data is not None else fallback_data

        logger.warning("Trust store data not found, using fallback")
        return fallback_data

    def get_passport_by_type(self, passport_type: str) -> list[dict[str, Any]]:
        """Get passports by type (based on prefix) or return fallback data."""
        all_passports = self.load_all_passport_data()

        prefix_map = {
            "P": "P",  # Regular passports
            "IS": "IS",  # Iceland passports
            "PM": "PM",  # Special type
        }

        prefix = prefix_map.get(passport_type.upper(), passport_type)
        return [p for p in all_passports if p["passport_number"].startswith(prefix)]

    def get_sample_passports(self, count: int = 5) -> list[dict[str, Any]]:
        """Get a sample of passport data for testing."""
        all_passports = self.load_all_passport_data()
        max_count = min(count, len(all_passports))

        if max_count == 0:
            return []

        # Use secure random sampling
        indices = []
        for _ in range(max_count):
            idx = secrets.randbelow(len(all_passports))
            if idx not in indices:
                indices.append(idx)

        return [all_passports[i] for i in indices]


# Singleton instance for easy access
test_data_loader = TestDataLoader()
