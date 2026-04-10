#!/usr/bin/env python3
"""
Database setup script for creating per-service databases.

This script creates individual PostgreSQL databases for each service
and sets up the initial schema using Alembic migrations.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
from asyncpg import Connection

# Service database configurations
SERVICES = {
    "document_signer": "marty_document_signer",
    "csca_service": "marty_csca",
    "pkd_service": "marty_pkd",
    "passport_engine": "marty_passport_engine",
}

# Default database connection settings
DEFAULT_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "dev_user",
    "password": "dev_password",
    "admin_user": "postgres",
    "admin_password": "postgres",
}


async def create_database(admin_conn: Connection, db_name: str, user: str) -> None:
    """Create a database and grant permissions to user."""
    print(f"Creating database: {db_name}")

    # Check if database exists
    result = await admin_conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)

    if result:
        print(f"  Database {db_name} already exists")
        return

    # Create database
    await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    print(f"  Created database: {db_name}")

    # Grant permissions
    await admin_conn.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO "{user}"')
    print(f"  Granted permissions to {user}")


async def create_user(admin_conn: Connection, username: str, password: str) -> None:
    """Create a PostgreSQL user if it doesn't exist."""
    print(f"Creating user: {username}")

    # Check if user exists
    result = await admin_conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", username)

    if result:
        print(f"  User {username} already exists")
        return

    # Create user — asyncpg's execute() does not support parameterised DDL
    # for identifiers, so we validate the username to prevent injection.
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', username):
        raise ValueError(f"Invalid username: {username!r}")
    await admin_conn.execute(
        f'CREATE USER "{username}" WITH PASSWORD $1', password
    )
    print(f"  Created user: {username}")


async def setup_databases() -> None:
    """Set up all service databases."""
    config = DEFAULT_CONFIG.copy()

    # Override with environment variables
    config.update(
        {
            "host": os.getenv("POSTGRES_HOST", config["host"]),
            "port": int(os.getenv("POSTGRES_PORT", str(config["port"]))),
            "user": os.getenv("POSTGRES_USER", config["user"]),
            "password": os.getenv("POSTGRES_PASSWORD", config["password"]),
            "admin_user": os.getenv("POSTGRES_ADMIN_USER", config["admin_user"]),
            "admin_password": os.getenv("POSTGRES_ADMIN_PASSWORD", config["admin_password"]),
        }
    )

    print("Connecting to PostgreSQL as admin...")
    admin_conn = await asyncpg.connect(
        host=config["host"],
        port=config["port"],
        user=config["admin_user"],
        password=config["admin_password"],
        database="postgres",
    )

    try:
        # Create the application user
        await create_user(admin_conn, config["user"], config["password"])

        # Create databases for each service
        for service_name, db_name in SERVICES.items():
            await create_database(admin_conn, db_name, config["user"])

    finally:
        await admin_conn.close()

    print("\\nDatabase setup completed!")


def run_alembic_migrations() -> None:
    """Run Alembic migrations for all services."""
    print("\\nRunning Alembic migrations...")
    project_root = Path(__file__).parent

    for service_name in SERVICES.keys():
        print(f"\\nRunning migrations for {service_name}...")
        service_dir = project_root / "src" / "services" / service_name

        if not service_dir.exists():
            print(f"  Warning: Service directory not found: {service_dir}")
            continue

        # Change to service directory and run alembic
        try:
            result = subprocess.run(
                ["uv", "run", "alembic", "upgrade", "head"],
                cwd=service_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"  ✓ Migrations completed for {service_name}")
            if result.stdout:
                print(f"    {result.stdout.strip()}")

        except subprocess.CalledProcessError as e:
            print(f"  ✗ Migration failed for {service_name}: {e}")
            if e.stdout:
                print(f"    stdout: {e.stdout}")
            if e.stderr:
                print(f"    stderr: {e.stderr}")
        except FileNotFoundError:
            print(f"  ✗ Could not find 'uv' command for {service_name}")


def generate_initial_migrations() -> None:
    """Generate initial migrations for all services."""
    print("\\nGenerating initial migrations...")
    project_root = Path(__file__).parent

    for service_name in SERVICES.keys():
        print(f"\\nGenerating initial migration for {service_name}...")
        service_dir = project_root / "src" / "services" / service_name

        if not service_dir.exists():
            print(f"  Warning: Service directory not found: {service_dir}")
            continue

        try:
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "alembic",
                    "revision",
                    "--autogenerate",
                    "-m",
                    f"Initial {service_name} schema",
                ],
                cwd=service_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"  ✓ Initial migration generated for {service_name}")
            if result.stdout:
                print(f"    {result.stdout.strip()}")

        except subprocess.CalledProcessError as e:
            print(f"  ✗ Migration generation failed for {service_name}: {e}")
            if e.stdout:
                print(f"    stdout: {e.stdout}")
            if e.stderr:
                print(f"    stderr: {e.stderr}")
        except FileNotFoundError:
            print(f"  ✗ Could not find 'uv' command for {service_name}")


def main() -> None:
    """Main setup function."""
    print("=== Database Per Service Setup ===\\n")

    if len(sys.argv) > 1 and sys.argv[1] == "--migrations-only":
        generate_initial_migrations()
        run_alembic_migrations()
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Usage:")
        print("  python setup_databases.py                 # Full setup (databases + migrations)")
        print("  python setup_databases.py --migrations-only  # Only generate and run migrations")
        print("  python setup_databases.py --help            # Show this help")
        return

    # Full setup
    print("This script will:")
    print("1. Create PostgreSQL databases for each service")
    print("2. Generate initial Alembic migrations")
    print("3. Run migrations to create schemas")
    print()

    response = input("Continue? (y/N): ")
    if response.lower() != "y":
        print("Setup cancelled.")
        return

    # Setup databases
    asyncio.run(setup_databases())

    # Generate and run migrations
    generate_initial_migrations()
    run_alembic_migrations()

    print("\\n=== Setup Complete ===")
    print("\\nNext steps:")
    print("1. Update your service configurations to use the per-service databases")
    print("2. Test service startup with: make db-current SERVICE=<service_name>")
    print(
        "3. Create new migrations with: make db-revision SERVICE=<service_name> MESSAGE='description'"
    )


if __name__ == "__main__":
    main()
