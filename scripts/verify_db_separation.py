#!/usr/bin/env python3
"""
Test script for verifying database schema creation without complex imports.

This demonstrates that the database per service setup is working
by creating simple test tables in each database.
"""

import asyncio
import re

import asyncpg


def _validate_identifier(name: str) -> None:
    """Validate that a name is a safe SQL identifier."""
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")

# Test database configuration
DB_CONFIG = {"host": "localhost", "port": 5432, "user": "dev_user", "password": "dev_password"}

# Service databases to test
SERVICE_DATABASES = ["marty_document_signer", "marty_csca", "marty_pkd", "marty_passport_engine"]


async def create_test_schema(database_name: str) -> bool:
    """Create a simple test schema in the database."""
    try:
        conn = await asyncpg.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=database_name,
        )

        # Create a simple test table to verify schema creation works
        service_name = database_name.replace("marty_", "")
        _validate_identifier(service_name)
        
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {service_name}_test (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """
        )

        # Insert test data
        await conn.execute(
            f"""
            INSERT INTO {service_name}_test (name)
            VALUES ('Test {service_name} data')
            ON CONFLICT DO NOTHING
        """
        )

        # Verify the data
        count = await conn.fetchval(f"SELECT COUNT(*) FROM {service_name}_test")

        print(f"✅ {database_name}: Schema created, {count} records")

        await conn.close()
        return True

    except Exception as e:
        print(f"❌ {database_name}: Schema creation failed - {e}")
        return False


async def verify_database_separation():
    """Verify that each service has its own isolated database."""
    print("Verifying database per service separation...")
    print("=" * 60)

    results = {}

    for db_name in SERVICE_DATABASES:
        results[db_name] = await create_test_schema(db_name)
        print()

    # Test cross-database isolation
    print("Testing database isolation...")
    try:
        # Connect to one database and verify we can't see other service tables
        conn = await asyncpg.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database="marty_document_signer",
        )

        # Try to query a table that should only exist in marty_csca
        try:
            await conn.fetchval("SELECT COUNT(*) FROM csca_test")
            print("❌ Database isolation FAILED: Can see other service tables")
            isolation_success = False
        except asyncpg.exceptions.UndefinedTableError:
            print("✅ Database isolation PASSED: Cannot see other service tables")
            isolation_success = True

        await conn.close()

    except Exception as e:
        print(f"❌ Database isolation test failed: {e}")
        isolation_success = False

    print("\n" + "=" * 60)
    print("Summary:")

    success_count = sum(results.values())
    total_count = len(results)

    for db_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {db_name}: {status}")

    print(f"\nSchema Creation: {success_count}/{total_count} databases")
    print(f"Database Isolation: {'✅ PASS' if isolation_success else '❌ FAIL'}")

    overall_success = success_count == total_count and isolation_success

    if overall_success:
        print("\n🎉 Database per service setup is working correctly!")
        print("Each service has its own isolated database with working schema creation.")
    else:
        print("\n⚠️  Database per service setup needs attention")

    return overall_success


if __name__ == "__main__":
    import sys

    success = asyncio.run(verify_database_separation())
    sys.exit(0 if success else 1)
