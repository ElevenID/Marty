#!/usr/bin/env python3
"""
Trust Services Development Job

One-shot job for loading synthetic master lists and displaying statistics.
Useful for development and testing environments.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from .config import TrustServiceConfig, config
from .database import DatabaseManager
from .models import RevocationStatus


class DevJobRunner:
    """Development job runner for trust services."""

    def __init__(self, config_obj: TrustServiceConfig = config):
        self.config = config_obj
        self.db_manager = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        """Initialize database connection."""
        self.db_manager = DatabaseManager(self.config)
        await self.db_manager.initialize()

    async def close(self) -> None:
        """Close database connection."""
        if self.db_manager:
            await self.db_manager.close()

    async def load_synthetic_master_list(
        self, country_code: str = "DEV", certificate_count: int = 25, output_format: str = "json"
    ) -> dict[str, Any]:
        """
        Load synthetic master list data for development.

        Args:
            country_code: Country code for synthetic data
            certificate_count: Number of certificates to generate
            output_format: Output format (json, table)

        Returns:
            Statistics dictionary
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Start job tracking
            job_id = await self.db_manager.start_job(
                job_name="dev_load_synthetic",
                job_type="load_synthetic",
                metadata={
                    "country_code": country_code,
                    "certificate_count": certificate_count,
                    "output_format": output_format,
                },
            )

            # Generate synthetic trust anchor
            trust_anchor_data = self._generate_synthetic_trust_anchor(country_code)
            trust_anchor_id = await self.db_manager.add_trust_anchor(trust_anchor_data)

            # Generate synthetic DSC certificates
            dsc_data_list = self._generate_synthetic_dscs(
                country_code,
                certificate_count - 1,  # Subtract 1 for the trust anchor
                trust_anchor_id,
            )

            added_dscs = 0
            revocation_stats = {"good": 0, "bad": 0, "unknown": 0}

            for dsc_data in dsc_data_list:
                # Add DSC to database
                await self._add_synthetic_dsc(dsc_data)
                added_dscs += 1

                # Track revocation status
                status = dsc_data["revocation_status"]
                revocation_stats[status] += 1

            # Generate synthetic master list record
            master_list_data = self._generate_synthetic_master_list(
                country_code, certificate_count, trust_anchor_id
            )

            await self._add_synthetic_master_list(master_list_data)

            # Generate synthetic CRL with some revoked certificates
            if revocation_stats["bad"] > 0:
                crl_data = self._generate_synthetic_crl(country_code, dsc_data_list)
                await self._add_synthetic_crl(crl_data)

            # Complete job
            await self.db_manager.complete_job(
                job_id=job_id, status="completed", records_processed=certificate_count
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Compile statistics
            statistics = {
                "job_id": job_id,
                "duration_seconds": duration,
                "master_list": {
                    "country": country_code,
                    "certificates": certificate_count,
                    "valid_certificates": certificate_count - 2,  # Simulate some expired
                    "expired_certificates": 2,
                },
                "trust_anchors": {"loaded": 1, "skipped": 0, "trust_anchor_id": trust_anchor_id},
                "dsc_certificates": {"loaded": added_dscs, "revocation_status": revocation_stats},
                "crls": {
                    "generated": 1 if revocation_stats["bad"] > 0 else 0,
                    "revoked_certificates": revocation_stats["bad"],
                },
            }

            self.logger.info(
                f"Synthetic data loaded for {country_code}: {certificate_count} certificates"
            )

            return statistics

        except Exception as e:
            self.logger.error(f"Failed to load synthetic data: {e}")
            raise

    def _generate_synthetic_trust_anchor(self, country_code: str) -> dict[str, Any]:
        """Generate synthetic CSCA trust anchor."""
        now = datetime.now(timezone.utc)

        certificate_data = f"SYNTHETIC_CSCA_{country_code}_CERT_DATA".encode()
        certificate_hash = f"SYNTHETIC_CSCA_{country_code}_HASH"

        return {
            "country_code": country_code,
            "certificate_hash": certificate_hash,
            "certificate_data": certificate_data,
            "subject_dn": f"CN=CSCA-{country_code},C={country_code},O={country_code} Authority",
            "issuer_dn": f"CN=CSCA-{country_code},C={country_code},O={country_code} Authority",
            "serial_number": f"{country_code}001",
            "valid_from": now - timedelta(days=365),
            "valid_to": now + timedelta(days=1825),  # 5 years
            "key_usage": ["keyCertSign", "cRLSign"],
            "signature_algorithm": "sha256WithRSAEncryption",
            "public_key_algorithm": "RSA",
            "trust_level": "standard",
            "status": "active",
        }

    def _generate_synthetic_dscs(
        self, country_code: str, count: int, trust_anchor_id: str
    ) -> list[dict[str, Any]]:
        """Generate synthetic DSC certificates."""
        now = datetime.now(timezone.utc)
        dscs = []

        for i in range(1, count + 1):
            # Determine revocation status (80% good, 10% bad, 10% unknown)
            if i % 10 == 0:
                revocation_status = "bad"
            elif i % 5 == 0:
                revocation_status = "unknown"
            else:
                revocation_status = "good"

            certificate_data = f"SYNTHETIC_DSC_{country_code}_{i:03d}_CERT_DATA".encode()
            certificate_hash = f"SYNTHETIC_DSC_{country_code}_{i:03d}_HASH"

            dsc_data = {
                "country_code": country_code,
                "certificate_hash": certificate_hash,
                "certificate_data": certificate_data,
                "issuer_trust_anchor_id": trust_anchor_id,
                "subject_dn": f"CN=DSC-{country_code}-{i:03d},C={country_code},O=Document Signer",
                "issuer_dn": f"CN=CSCA-{country_code},C={country_code},O={country_code} Authority",
                "serial_number": f"{country_code}{i:03d}",
                "valid_from": now - timedelta(days=30),
                "valid_to": now + timedelta(days=730),  # 2 years
                "key_usage": ["digitalSignature"],
                "signature_algorithm": "sha256WithRSAEncryption",
                "public_key_algorithm": "RSA",
                "revocation_status": revocation_status,
                "revocation_checked_at": now - timedelta(hours=1),
                "chain_valid": True,
                "chain_validated_at": now - timedelta(hours=1),
                "status": "active",
            }

            dscs.append(dsc_data)

        return dscs

    async def _add_synthetic_dsc(self, dsc_data: dict[str, Any]) -> None:
        """Add synthetic DSC to database."""
        async with self.db_manager.get_session() as session:
            from sqlalchemy import text

            query = text(
                """
                INSERT INTO trust_svc.dsc_certificates
                (country_code, certificate_hash, certificate_data, issuer_trust_anchor_id,
                 subject_dn, issuer_dn, serial_number, valid_from, valid_to, key_usage,
                 signature_algorithm, public_key_algorithm, revocation_status,
                 revocation_checked_at, chain_valid, chain_validated_at, status)
                VALUES
                (:country_code, :certificate_hash, :certificate_data, :issuer_trust_anchor_id,
                 :subject_dn, :issuer_dn, :serial_number, :valid_from, :valid_to, :key_usage,
                 :signature_algorithm, :public_key_algorithm, :revocation_status,
                 :revocation_checked_at, :chain_valid, :chain_validated_at, :status)
                ON CONFLICT (certificate_hash) DO NOTHING
            """
            )

            await session.execute(query, dsc_data)
            await session.commit()

    def _generate_synthetic_master_list(
        self, country_code: str, certificate_count: int, trust_anchor_id: str
    ) -> dict[str, Any]:
        """Generate synthetic master list metadata."""
        now = datetime.now(timezone.utc)

        master_list_content = f"SYNTHETIC_MASTER_LIST_{country_code}_{now.isoformat()}"
        data_hash = f"SYNTHETIC_ML_HASH_{country_code}"

        return {
            "country_code": country_code,
            "sequence_number": 1,
            "version": "1.0.0",
            "issue_date": now,
            "next_update": now + timedelta(days=30),
            "certificate_count": certificate_count,
            "data_hash": data_hash,
            "raw_data": master_list_content.encode(),
            "signature_valid": True,
            "signer_certificate_hash": f"SYNTHETIC_CSCA_{country_code}_HASH",
            "source_type": "synthetic",
            "source_url": f"synthetic://{country_code}/master_list",
            "status": "active",
        }

    async def _add_synthetic_master_list(self, master_list_data: dict[str, Any]) -> None:
        """Add synthetic master list to database."""
        async with self.db_manager.get_session() as session:
            from sqlalchemy import text

            query = text(
                """
                INSERT INTO trust_svc.master_lists
                (country_code, sequence_number, version, issue_date, next_update,
                 certificate_count, data_hash, raw_data, signature_valid,
                 signer_certificate_hash, source_type, source_url, status)
                VALUES
                (:country_code, :sequence_number, :version, :issue_date, :next_update,
                 :certificate_count, :data_hash, :raw_data, :signature_valid,
                 :signer_certificate_hash, :source_type, :source_url, :status)
                ON CONFLICT (country_code, sequence_number) DO UPDATE SET
                issue_date = EXCLUDED.issue_date,
                certificate_count = EXCLUDED.certificate_count,
                data_hash = EXCLUDED.data_hash
            """
            )

            await session.execute(query, master_list_data)
            await session.commit()

    def _generate_synthetic_crl(
        self, country_code: str, dsc_data_list: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Generate synthetic CRL."""
        now = datetime.now(timezone.utc)

        crl_content = f"SYNTHETIC_CRL_{country_code}_{now.isoformat()}"
        crl_hash = f"SYNTHETIC_CRL_HASH_{country_code}"

        # Count revoked certificates
        revoked_count = len([dsc for dsc in dsc_data_list if dsc["revocation_status"] == "bad"])

        return {
            "issuer_dn": f"CN=CSCA-{country_code},C={country_code},O={country_code} Authority",
            "issuer_certificate_hash": f"SYNTHETIC_CSCA_{country_code}_HASH",
            "crl_url": f"synthetic://{country_code}/crl",
            "crl_number": 1001,
            "this_update": now - timedelta(hours=1),
            "next_update": now + timedelta(days=7),
            "crl_data": crl_content.encode(),
            "crl_hash": crl_hash,
            "signature_valid": True,
            "revoked_count": revoked_count,
            "status": "active",
        }

    async def _add_synthetic_crl(self, crl_data: dict[str, Any]) -> None:
        """Add synthetic CRL to database."""
        crl_id = await self.db_manager.add_crl(crl_data)

        # Add revoked certificate entries
        async with self.db_manager.get_session() as session:
            from sqlalchemy import text

            # Get revoked DSCs
            revoked_query = text(
                """
                SELECT serial_number, certificate_hash
                FROM trust_svc.dsc_certificates
                WHERE revocation_status = 'bad'
                AND country_code = :country_code
            """
            )

            result = await session.execute(
                revoked_query, {"country_code": crl_data["issuer_dn"][-3:]}
            )

            for row in result.fetchall():
                revoked_entry = {
                    "crl_id": crl_id,
                    "serial_number": row.serial_number,
                    "revocation_date": datetime.now(timezone.utc) - timedelta(days=30),
                    "reason_code": 1,  # Key compromise
                    "certificate_hash": row.certificate_hash,
                }

                insert_query = text(
                    """
                    INSERT INTO trust_svc.revoked_certificates
                    (crl_id, serial_number, revocation_date, reason_code, certificate_hash)
                    VALUES (:crl_id, :serial_number, :revocation_date, :reason_code, :certificate_hash)
                    ON CONFLICT (crl_id, serial_number) DO NOTHING
                """
                )

                await session.execute(insert_query, revoked_entry)

            await session.commit()


def format_statistics(statistics: dict[str, Any], output_format: str = "json") -> str:
    """Format statistics for output."""
    if output_format.lower() == "json":
        return json.dumps(statistics, indent=2, default=str)

    elif output_format.lower() == "table":
        output = []
        output.append("=" * 60)
        output.append("TRUST SERVICES - SYNTHETIC DATA LOAD RESULTS")
        output.append("=" * 60)
        output.append(f"Country: {statistics['master_list']['country']}")
        output.append(f"Duration: {statistics['duration_seconds']:.2f} seconds")
        output.append("")

        output.append("Master List:")
        ml_stats = statistics["master_list"]
        output.append(f"  Total Certificates: {ml_stats['certificates']}")
        output.append(f"  Valid Certificates: {ml_stats['valid_certificates']}")
        output.append(f"  Expired Certificates: {ml_stats['expired_certificates']}")
        output.append("")

        output.append("Trust Anchors:")
        ta_stats = statistics["trust_anchors"]
        output.append(f"  Loaded: {ta_stats['loaded']}")
        output.append(f"  Skipped: {ta_stats['skipped']}")
        output.append("")

        output.append("DSC Certificates:")
        dsc_stats = statistics["dsc_certificates"]
        output.append(f"  Loaded: {dsc_stats['loaded']}")
        output.append("  Revocation Status:")
        for status, count in dsc_stats["revocation_status"].items():
            output.append(f"    {status.title()}: {count}")
        output.append("")

        if statistics.get("crls", {}).get("generated", 0) > 0:
            output.append("Certificate Revocation Lists:")
            crl_stats = statistics["crls"]
            output.append(f"  Generated: {crl_stats['generated']}")
            output.append(f"  Revoked Certificates: {crl_stats['revoked_certificates']}")

        output.append("=" * 60)
        return "\n".join(output)

    else:
        return f"Statistics: {statistics}"


async def main():
    """Main entry point for development job."""
    import argparse

    parser = argparse.ArgumentParser(description="Trust Services Development Job")
    parser.add_argument("--country", default="DEV", help="Country code for synthetic data")
    parser.add_argument("--count", type=int, default=25, help="Number of certificates to generate")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="Output format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Run the job
    runner = DevJobRunner()

    try:
        await runner.initialize()

        statistics = await runner.load_synthetic_master_list(
            country_code=args.country, certificate_count=args.count, output_format=args.format
        )

        # Output results
        output = format_statistics(statistics, args.format)
        print(output)

    except Exception as e:
        logging.error(f"Job failed: {e}")
        sys.exit(1)

    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
