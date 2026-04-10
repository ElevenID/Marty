"""
Shared test fixtures for integration tests.

This module provides reusable fixtures for MDL/mDoc credential testing
with ISO 18013-5 compliant data structures.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest


# =============================================================================
# ISO 18013-5 MDL Test Data Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def mdl_namespace() -> str:
    """ISO 18013-5 namespace for mDL credentials."""
    return "org.iso.18013.5.1"


@pytest.fixture(scope="session")
def mdl_doctype() -> str:
    """ISO 18013-5 document type for mDL credentials."""
    return "org.iso.18013.5.1.mDL"


@pytest.fixture(scope="session")
def mdl_holder_info() -> dict[str, Any]:
    """
    Reusable MDL holder personal information.
    Based on ISO 18013-5 data elements.
    """
    return {
        "family_name": "Doe",
        "given_name": "John",
        "birth_date": "1990-05-15",
        "issue_date": "2023-01-01",
        "expiry_date": "2028-01-01",
        "issuing_country": "US",
        "issuing_authority": "State DMV",
        "document_number": "DL123456789",
        "portrait": b"portrait_placeholder_data",
        "driving_privileges": [
            {
                "vehicle_category_code": "C",
                "issue_date": "2023-01-01",
                "expiry_date": "2028-01-01",
            },
            {
                "vehicle_category_code": "B",
                "issue_date": "2020-06-15",
                "expiry_date": "2028-01-01",
            },
        ],
        "un_distinguishing_sign": "USA",
        "administrative_number": "ADM987654321",
        "sex": 1,  # ISO 5218: 1 = male, 2 = female
        "height": 180,  # cm
        "weight": 75,  # kg
        "eye_colour": "BLU",
        "hair_colour": "BRN",
        "birth_place": "New York, NY",
        "resident_address": "123 Main St, Springfield, IL 62701",
        "resident_city": "Springfield",
        "resident_state": "IL",
        "resident_postal_code": "62701",
        "resident_country": "US",
        "age_in_years": 34,
        "age_over_18": True,
        "age_over_21": True,
        "nationality": "US",
    }


@pytest.fixture(scope="session")
def mdl_test_data(mdl_holder_info: dict[str, Any], mdl_doctype: str, mdl_namespace: str) -> dict[str, Any]:
    """
    Complete MDL test data structure for cross-SDK compatibility testing.
    Combines holder info with credential metadata.
    """
    return {
        "doctype": mdl_doctype,
        "namespace": mdl_namespace,
        "holder": mdl_holder_info,
        "credential_id": f"urn:uuid:{uuid.uuid4()}",
        "issuer_id": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "issuance_date": datetime.now(timezone.utc).isoformat(),
        "expiration_date": (datetime.now(timezone.utc) + timedelta(days=365 * 5)).isoformat(),
    }


@pytest.fixture(scope="session")
def mdl_claims(mdl_holder_info: dict[str, Any]) -> dict[str, Any]:
    """
    MDL claims in the format expected by credential issuers.
    Maps to ISO 18013-5 data elements.
    """
    return {
        "family_name": mdl_holder_info["family_name"],
        "given_name": mdl_holder_info["given_name"],
        "birth_date": mdl_holder_info["birth_date"],
        "document_number": mdl_holder_info["document_number"],
        "issue_date": mdl_holder_info["issue_date"],
        "expiry_date": mdl_holder_info["expiry_date"],
        "issuing_authority": mdl_holder_info["issuing_authority"],
        "issuing_country": mdl_holder_info["issuing_country"],
        "driving_privileges": mdl_holder_info["driving_privileges"],
        "resident_address": mdl_holder_info["resident_address"],
        "resident_city": mdl_holder_info["resident_city"],
        "resident_state": mdl_holder_info["resident_state"],
        "resident_postal_code": mdl_holder_info["resident_postal_code"],
        "age_over_18": mdl_holder_info["age_over_18"],
        "age_over_21": mdl_holder_info["age_over_21"],
    }


@pytest.fixture(scope="session")
def mdl_selective_disclosure_claims() -> list[str]:
    """
    Common selective disclosure claim sets for MDL presentations.
    """
    return [
        "given_name",
        "family_name",
        "birth_date",
        "document_number",
    ]


@pytest.fixture(scope="session")
def mdl_age_verification_claims() -> list[str]:
    """
    Claims for age verification without revealing birth_date.
    """
    return [
        "age_over_18",
        "age_over_21",
        "given_name",
        "family_name",
    ]


# =============================================================================
# Secondary Test Holder Data (for multi-credential tests)
# =============================================================================

@pytest.fixture(scope="session")
def mdl_holder_info_secondary() -> dict[str, Any]:
    """
    Secondary MDL holder for multi-credential or cross-verification tests.
    """
    return {
        "family_name": "Smith",
        "given_name": "Jane",
        "birth_date": "1985-11-22",
        "issue_date": "2022-06-15",
        "expiry_date": "2027-06-15",
        "issuing_country": "US",
        "issuing_authority": "State DMV",
        "document_number": "DL987654321",
        "portrait": b"secondary_portrait_data",
        "driving_privileges": [
            {
                "vehicle_category_code": "B",
                "issue_date": "2022-06-15",
                "expiry_date": "2027-06-15",
            },
        ],
        "un_distinguishing_sign": "USA",
        "sex": 2,  # ISO 5218: female
        "height": 165,
        "weight": 60,
        "eye_colour": "GRN",
        "hair_colour": "BLK",
        "birth_place": "Los Angeles, CA",
        "resident_address": "456 Oak Ave, San Francisco, CA 94102",
        "resident_city": "San Francisco",
        "resident_state": "CA",
        "resident_postal_code": "94102",
        "resident_country": "US",
        "age_in_years": 39,
        "age_over_18": True,
        "age_over_21": True,
        "nationality": "US",
    }


# =============================================================================
# OID4VC Test Configuration Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def oid4vci_issuer_config() -> dict[str, Any]:
    """
    OID4VCI issuer configuration for testing.
    """
    return {
        "issuer_url": "http://localhost:8000/oidc4vci",
        "issuer_name": "Test MDL Issuer",
        "credential_endpoint": "http://localhost:8000/oidc4vci/credential",
        "token_endpoint": "http://localhost:8000/oidc4vci/token",
        "supported_formats": ["mso_mdoc", "jwt_vc_json", "vc+sd-jwt"],
        "supported_credentials": [
            {
                "id": "mdl_credential",
                "format": "mso_mdoc",
                "doctype": "org.iso.18013.5.1.mDL",
                "display": {"name": "Mobile Driver's License", "locale": "en-US"},
            },
            {
                "id": "mdl_jwt_credential",
                "format": "jwt_vc_json",
                "type": ["VerifiableCredential", "ISO18013DriversLicense"],
                "display": {"name": "Driver's License (JWT)", "locale": "en-US"},
            },
        ],
    }


@pytest.fixture(scope="session")
def oid4vp_verifier_config() -> dict[str, Any]:
    """
    OID4VP verifier configuration for testing.
    """
    return {
        "verifier_id": "did:key:z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH",
        "verifier_name": "Test MDL Verifier",
        "response_uri": "http://localhost:8000/api/verifier/response",
        "presentation_definition": {
            "id": "mdl-verification-request",
            "input_descriptors": [
                {
                    "id": "mdl_descriptor",
                    "format": {
                        "mso_mdoc": {"alg": ["ES256"]},
                        "jwt_vp": {"alg": ["ES256"]},
                    },
                    "constraints": {
                        "limit_disclosure": "required",
                        "fields": [
                            {"path": ["$.credentialSubject.given_name"], "intent_to_retain": False},
                            {"path": ["$.credentialSubject.family_name"], "intent_to_retain": False},
                            {"path": ["$.credentialSubject.document_number"], "intent_to_retain": False},
                        ],
                    },
                },
            ],
        },
    }


# =============================================================================
# Expired/Invalid Credential Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def expired_mdl_holder_info(mdl_holder_info: dict[str, Any]) -> dict[str, Any]:
    """
    MDL holder info with expired dates for negative testing.
    """
    expired_info = mdl_holder_info.copy()
    expired_info["issue_date"] = "2018-01-01"
    expired_info["expiry_date"] = "2023-01-01"  # Already expired
    expired_info["document_number"] = "DLEXPIRED001"
    return expired_info


@pytest.fixture(scope="function")
def unique_credential_id() -> str:
    """
    Generate a unique credential ID for each test function.
    """
    return f"urn:uuid:{uuid.uuid4()}"


# =============================================================================
# gRPC Service Configuration
# =============================================================================

@pytest.fixture(scope="session")
def mdl_engine_address() -> str:
    """MDL Engine gRPC service address."""
    return os.getenv("MDL_ENGINE_ADDRESS", "localhost:50051")


@pytest.fixture(scope="session")
def mdoc_engine_address() -> str:
    """mDoc Engine gRPC service address."""
    return os.getenv("MDOC_ENGINE_ADDRESS", "localhost:50054")


@pytest.fixture(scope="session")
def oid4vc_api_base_url() -> str:
    """OID4VC API base URL."""
    return os.getenv("OID4VC_API_URL", "http://localhost:8000")


# =============================================================================
# Database Fixtures for KMS Integration Tests
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_engine():
    """
    Create database engine for integration tests.
    Uses test database: postgresql://test:test@localhost:5432/marty_test
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from src.subscription.models import Base
    
    # Use test database
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://test:test@localhost:5432/marty_test"
    )
    
    engine = create_async_engine(database_url, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(db_engine):
    """Provide a database session for each test."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def free_organization(db_session):
    """Create a free tier organization for testing."""
    from src.subscription.models import Organization
    
    org = Organization(
        id=uuid.uuid4(),
        name="Free Test Organization",
        square_customer_id=f"test_customer_{uuid.uuid4().hex[:8]}"
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def starter_organization(db_session):
    """Create a starter tier organization for testing."""
    from src.subscription.models import Organization
    
    org = Organization(
        id=uuid.uuid4(),
        name="Starter Test Organization",
        square_customer_id=f"test_customer_{uuid.uuid4().hex[:8]}"
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def professional_organization(db_session):
    """Create a professional tier organization for testing."""
    from src.subscription.models import Organization
    
    org = Organization(
        id=uuid.uuid4(),
        name="Professional Test Organization",
        square_customer_id=f"test_customer_{uuid.uuid4().hex[:8]}"
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def free_subscription(db_session, free_organization):
    """Create a free subscription."""
    from src.subscription.models import Subscription
    from src.subscription.square_service import SquarePlan
    
    subscription = Subscription(
        id=uuid.uuid4(),
        organization_id=free_organization.id,
        plan=SquarePlan.SANDBOX.value,
        status="active",
        is_trial=False
    )
    db_session.add(subscription)
    await db_session.flush()
    return subscription


@pytest.fixture
async def starter_subscription(db_session, starter_organization):
    """Create a starter subscription with KMS enabled."""
    from src.subscription.models import Subscription
    from src.subscription.square_service import SquarePlan
    
    subscription = Subscription(
        id=uuid.uuid4(),
        organization_id=starter_organization.id,
        plan=SquarePlan.STARTER.value,
        status="active",
        is_trial=False,
        remote_signing_enabled=True
    )
    db_session.add(subscription)
    await db_session.flush()
    return subscription


@pytest.fixture
async def professional_subscription(db_session, professional_organization):
    """Create a professional subscription with KMS enabled."""
    from src.subscription.models import Subscription
    from src.subscription.square_service import SquarePlan
    
    subscription = Subscription(
        id=uuid.uuid4(),
        organization_id=professional_organization.id,
        plan=SquarePlan.PROFESSIONAL.value,
        status="active",
        is_trial=False,
        remote_signing_enabled=True
    )
    db_session.add(subscription)
    await db_session.flush()
    return subscription
