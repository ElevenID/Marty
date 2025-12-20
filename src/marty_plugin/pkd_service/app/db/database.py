"""
Database connection and interface for PKD service
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import aiosqlite
from app.core.config import settings
from app.models.pkd_models import CertificateStatus

logger = logging.getLogger(__name__)

# Initialize database path
DB_PATH = os.path.join(settings.DATA_PATH, "pkd.db")

# SQL scripts for creating database tables
CREATE_CERTIFICATES_TABLE = """
CREATE TABLE IF NOT EXISTS certificates (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    issuer TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    serial_number TEXT NOT NULL,
    certificate_data BLOB NOT NULL,
    status TEXT NOT NULL,
    country_code TEXT NOT NULL,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_CRLS_TABLE = """
CREATE TABLE IF NOT EXISTS crls (
    id TEXT PRIMARY KEY,
    issuer TEXT NOT NULL,
    this_update TEXT NOT NULL,
    next_update TEXT NOT NULL,
    crl_data BLOB NOT NULL,
    created_at TEXT NOT NULL
);
"""

CREATE_REVOKED_CERTIFICATES_TABLE = """
CREATE TABLE IF NOT EXISTS revoked_certificates (
    id TEXT PRIMARY KEY,
    serial_number TEXT NOT NULL,
    revocation_date TEXT NOT NULL,
    reason_code INTEGER,
    crl_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (crl_id) REFERENCES crls (id)
);
"""

CREATE_DEVIATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS deviations (
    id TEXT PRIMARY KEY,
    country TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    certificate_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CREATE_SYNC_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS sync_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    sync_source TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    components TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


async def init_db() -> None:
    """
    Initialize the database connection and create tables if they don't exist.
    """
    logger.info(f"Initializing database at {DB_PATH}")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Create tables
            await db.execute(CREATE_CERTIFICATES_TABLE)
            await db.execute(CREATE_CRLS_TABLE)
            await db.execute(CREATE_REVOKED_CERTIFICATES_TABLE)
            await db.execute(CREATE_DEVIATIONS_TABLE)
            await db.execute(CREATE_SYNC_JOBS_TABLE)
            await db.commit()

        logger.info("Database initialized successfully")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        raise


async def get_db() -> AsyncGenerator:
    """
    Get a database connection.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Make sure we get row objects with keys/values
            db.row_factory = aiosqlite.Row
            yield db
    except Exception as e:
        logger.exception(f"Database connection error: {e}")
        raise


class DatabaseManager:
    """Database operations manager for PKD service"""

    @staticmethod
    async def store_certificate(certificate_data: dict[str, Any], cert_type: str = "CSCA") -> str:
        """
        Store a certificate in the database.

        Args:
            certificate_data: Certificate data dictionary
            cert_type: Type of certificate (CSCA or DSC)

        Returns:
            ID of the stored certificate
        """
        certificate_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO certificates (
                        id, subject, issuer, valid_from, valid_to, serial_number,
                        certificate_data, status, country_code, type, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        certificate_id,
                        certificate_data["subject"],
                        certificate_data["issuer"],
                        certificate_data["valid_from"].isoformat(),
                        certificate_data["valid_to"].isoformat(),
                        certificate_data["serial_number"],
                        certificate_data["certificate_data"],
                        certificate_data["status"],
                        certificate_data["country_code"],
                        cert_type,
                        now,
                        now,
                    ),
                )
                await db.commit()

                return certificate_id

        except Exception as e:
            logger.exception(f"Failed to store certificate: {e}")
            raise

    @staticmethod
    async def update_certificate_status(certificate_id: str, status: CertificateStatus) -> bool:
        """Update the status of a certificate identified by its ID."""

        now = datetime.now().isoformat()
        status_value = status.value if isinstance(status, CertificateStatus) else str(status)

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    """
                    UPDATE certificates
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status_value, now, certificate_id),
                )
                await db.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.exception(f"Failed to update certificate status: {e}")
            return False

    @staticmethod
    async def update_certificate_status_by_serial(
        serial_number: str, cert_type: str, status: CertificateStatus
    ) -> int:
        """Update certificate status using serial number and type."""

        now = datetime.now().isoformat()
        status_value = status.value if isinstance(status, CertificateStatus) else str(status)

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    """
                    UPDATE certificates
                    SET status = ?, updated_at = ?
                    WHERE serial_number = ? AND type = ?
                    """,
                    (status_value, now, serial_number, cert_type),
                )
                await db.commit()
                return cursor.rowcount

        except Exception as e:
            logger.exception(f"Failed to update certificate status by serial: {e}")
            return 0

    @staticmethod
    async def get_certificates(
        cert_type: str = "CSCA", country: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get certificates from the database.

        Args:
            cert_type: Type of certificates to retrieve (CSCA or DSC)
            country: Optional country code filter

        Returns:
            List of certificate dictionaries
        """
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row

                if country:
                    query = """
                    SELECT * FROM certificates
                    WHERE type = ? AND country_code = ?
                    ORDER BY valid_from DESC
                    """
                    cursor = await db.execute(query, (cert_type, country))
                else:
                    query = """
                    SELECT * FROM certificates
                    WHERE type = ?
                    ORDER BY valid_from DESC
                    """
                    cursor = await db.execute(query, (cert_type,))

                rows = await cursor.fetchall()
                certificates = []

                for row in rows:
                    certificates.append(
                        {
                            "id": row["id"],
                            "subject": row["subject"],
                            "issuer": row["issuer"],
                            "valid_from": datetime.fromisoformat(row["valid_from"]),
                            "valid_to": datetime.fromisoformat(row["valid_to"]),
                            "serial_number": row["serial_number"],
                            "certificate_data": row["certificate_data"],
                            "status": row["status"],
                            "country_code": row["country_code"],
                        }
                    )

                return certificates

        except Exception as e:
            logger.exception(f"Failed to get certificates: {e}")
            return []

    @staticmethod
    async def store_crl(crl_data: dict[str, Any]) -> str:
        """
        Store a CRL in the database.

        Args:
            crl_data: CRL data dictionary

        Returns:
            ID of the stored CRL
        """
        crl_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Store the CRL
                await db.execute(
                    """
                    INSERT INTO crls (
                        id, issuer, this_update, next_update, crl_data, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        crl_id,
                        crl_data["issuer"],
                        crl_data["this_update"].isoformat(),
                        crl_data["next_update"].isoformat(),
                        crl_data["crl_data"],
                        now,
                    ),
                )

                # Store the revoked certificates
                for revoked_cert in crl_data["revoked_certificates"]:
                    revoked_id = str(uuid.uuid4())
                    await db.execute(
                        """
                        INSERT INTO revoked_certificates (
                            id, serial_number, revocation_date, reason_code, crl_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            revoked_id,
                            revoked_cert["serial_number"],
                            revoked_cert["revocation_date"].isoformat(),
                            revoked_cert.get("reason_code"),
                            crl_id,
                            now,
                        ),
                    )

                await db.commit()
                return crl_id

        except Exception as e:
            logger.exception(f"Failed to store CRL: {e}")
            raise

    @staticmethod
    async def get_crl(issuer: str | None = None) -> dict[str, Any] | None:
        """
        Get the latest CRL from the database.

        Args:
            issuer: Optional issuer filter

        Returns:
            CRL data dictionary or None if not found
        """
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row

                if issuer:
                    query = """
                    SELECT * FROM crls
                    WHERE issuer LIKE ?
                    ORDER BY this_update DESC
                    LIMIT 1
                    """
                    cursor = await db.execute(query, (f"%{issuer}%",))
                else:
                    query = """
                    SELECT * FROM crls
                    ORDER BY this_update DESC
                    LIMIT 1
                    """
                    cursor = await db.execute(query)

                row = await cursor.fetchone()
                if not row:
                    return None

                crl_id = row["id"]

                # Get the revoked certificates for this CRL
                query = """
                SELECT * FROM revoked_certificates
                WHERE crl_id = ?
                """
                cursor = await db.execute(query, (crl_id,))
                revoked_rows = await cursor.fetchall()

                revoked_certificates = []
                for revoked_row in revoked_rows:
                    revoked_certificates.append(
                        {
                            "serial_number": revoked_row["serial_number"],
                            "revocation_date": datetime.fromisoformat(
                                revoked_row["revocation_date"]
                            ),
                            "reason_code": revoked_row["reason_code"],
                        }
                    )

                return {
                    "id": row["id"],
                    "issuer": row["issuer"],
                    "this_update": datetime.fromisoformat(row["this_update"]),
                    "next_update": datetime.fromisoformat(row["next_update"]),
                    "crl_data": row["crl_data"],
                    "revoked_certificates": revoked_certificates,
                }

        except Exception as e:
            logger.exception(f"Failed to get CRL: {e}")
            return None

    @staticmethod
    async def store_deviation(deviation_data: dict[str, Any]) -> str:
        """
        Store a deviation in the database.

        Args:
            deviation_data: Deviation data dictionary

        Returns:
            ID of the stored deviation
        """
        deviation_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO deviations (
                        id, country, type, description, certificate_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        deviation_id,
                        deviation_data["country"],
                        deviation_data["type"],
                        deviation_data["description"],
                        deviation_data.get("certificate_id"),
                        now,
                        now,
                    ),
                )
                await db.commit()

                return deviation_id

        except Exception as e:
            logger.exception(f"Failed to store deviation: {e}")
            raise

    @staticmethod
    async def get_deviations(country: str | None = None) -> list[dict[str, Any]]:
        """
        Get deviations from the database.

        Args:
            country: Optional country code filter

        Returns:
            List of deviation dictionaries
        """
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row

                if country:
                    query = """
                    SELECT * FROM deviations
                    WHERE country = ?
                    ORDER BY created_at DESC
                    """
                    cursor = await db.execute(query, (country,))
                else:
                    query = """
                    SELECT * FROM deviations
                    ORDER BY created_at DESC
                    """
                    cursor = await db.execute(query)

                rows = await cursor.fetchall()
                deviations = []

                for row in rows:
                    deviations.append(
                        {
                            "id": row["id"],
                            "country": row["country"],
                            "type": row["type"],
                            "description": row["description"],
                            "certificate_id": row["certificate_id"],
                            "created_at": datetime.fromisoformat(row["created_at"]),
                            "updated_at": datetime.fromisoformat(row["updated_at"]),
                        }
                    )

                return deviations

        except Exception as e:
            logger.exception(f"Failed to get deviations: {e}")
            return []

    @staticmethod
    async def store_sync_job(sync_data: dict[str, Any]) -> str:
        """
        Store a sync job in the database.

        Args:
            sync_data: Sync job data dictionary

        Returns:
            ID of the stored sync job
        """
        sync_id = sync_data.get("id", str(uuid.uuid4()))
        now = datetime.now().isoformat()

        # Convert components list to a comma-separated string
        components_str = ",".join(sync_data.get("components", []))

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO sync_jobs (
                        id, status, sync_source, start_time, end_time, components,
                        error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sync_id,
                        sync_data["status"],
                        sync_data["sync_source"],
                        sync_data["start_time"].isoformat(),
                        (
                            sync_data.get("end_time", "").isoformat()
                            if sync_data.get("end_time")
                            else None
                        ),
                        components_str,
                        sync_data.get("error_message"),
                        now,
                        now,
                    ),
                )
                await db.commit()

                return sync_id

        except Exception as e:
            logger.exception(f"Failed to store sync job: {e}")
            raise

    @staticmethod
    async def update_sync_job(sync_id: str, update_data: dict[str, Any]) -> bool:
        """
        Update a sync job in the database.

        Args:
            sync_id: ID of the sync job to update
            update_data: Data to update

        Returns:
            True if successful, False otherwise
        """
        now = datetime.now().isoformat()

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                # Build the update query dynamically based on provided fields
                query_parts = []
                params = []

                if "status" in update_data:
                    query_parts.append("status = ?")
                    params.append(update_data["status"])

                if "end_time" in update_data:
                    query_parts.append("end_time = ?")
                    params.append(update_data["end_time"].isoformat())

                if "error_message" in update_data:
                    query_parts.append("error_message = ?")
                    params.append(update_data["error_message"])

                # Always update the updated_at field
                query_parts.append("updated_at = ?")
                params.append(now)

                # Add the sync_id to the params
                params.append(sync_id)

                query = f"UPDATE sync_jobs SET {', '.join(query_parts)} WHERE id = ?"

                await db.execute(query, params)
                await db.commit()

                return True

        except Exception as e:
            logger.exception(f"Failed to update sync job: {e}")
            return False

    @staticmethod
    async def get_sync_job(sync_id: str) -> dict[str, Any] | None:
        """
        Get a sync job from the database.

        Args:
            sync_id: ID of the sync job to retrieve

        Returns:
            Sync job data dictionary or None if not found
        """
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row

                query = """
                SELECT * FROM sync_jobs
                WHERE id = ?
                """
                cursor = await db.execute(query, (sync_id,))

                row = await cursor.fetchone()
                if not row:
                    return None

                # Convert components string back to a list
                components = row["components"].split(",") if row["components"] else []

                return {
                    "id": row["id"],
                    "status": row["status"],
                    "sync_source": row["sync_source"],
                    "start_time": datetime.fromisoformat(row["start_time"]),
                    "end_time": (
                        datetime.fromisoformat(row["end_time"]) if row["end_time"] else None
                    ),
                    "components": components,
                    "error_message": row["error_message"],
                    "created_at": datetime.fromisoformat(row["created_at"]),
                    "updated_at": datetime.fromisoformat(row["updated_at"]),
                }

        except Exception as e:
            logger.exception(f"Failed to get sync job: {e}")
            return None

    @staticmethod
    async def get_latest_sync_job() -> dict[str, Any] | None:
        """
        Get the latest sync job from the database.

        Returns:
            Latest sync job data dictionary or None if not found
        """
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row

                query = """
                SELECT * FROM sync_jobs
                ORDER BY start_time DESC
                LIMIT 1
                """
                cursor = await db.execute(query)

                row = await cursor.fetchone()
                if not row:
                    return None

                # Convert components string back to a list
                components = row["components"].split(",") if row["components"] else []

                return {
                    "id": row["id"],
                    "status": row["status"],
                    "sync_source": row["sync_source"],
                    "start_time": datetime.fromisoformat(row["start_time"]),
                    "end_time": (
                        datetime.fromisoformat(row["end_time"]) if row["end_time"] else None
                    ),
                    "components": components,
                    "error_message": row["error_message"],
                    "created_at": datetime.fromisoformat(row["created_at"]),
                    "updated_at": datetime.fromisoformat(row["updated_at"]),
                }

        except Exception as e:
            logger.exception(f"Failed to get latest sync job: {e}")
            return None
