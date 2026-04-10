"""
Pytest fixtures for mDoc/mDL OpenID4VP unit tests with mocking.

Provides mock gRPC stubs and FastAPI test client fixtures for testing
without requiring live services.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Pre-mock marty_plugin.common subtree (Rust FFI bridge not available in tests)
# Must run before any other imports that may trigger the chain:
#   test → marty_backend_common → marty_plugin.common.*
# ---------------------------------------------------------------------------
import importlib.abc
import importlib.machinery
import sys
from unittest.mock import MagicMock


class _StubModule(MagicMock):
    """A MagicMock that acts as a module but returns real classes for names
    that are used as base classes (to avoid metaclass conflicts with ABC etc.)."""

    # Names that must be real classes (used in inheritance)
    _CLASS_NAMES = {
        "BaseService", "ServiceConfig", "BaseValidator", "BaseProvider",
        "BaseCryptoProvider", "BaseTransport", "BaseEngine",
    }
    # Names that must be real exceptions (used in except/raise)
    _EXCEPTION_NAMES = {
        "CryptoError", "ValidationError", "ConfigError", "SecurityError",
        "EncryptionError", "DecryptionError", "SigningError", "VerificationError",
    }

    def __getattr__(self, name):
        if name in self._CLASS_NAMES:
            return type(name, (), {})
        if name in self._EXCEPTION_NAMES:
            return type(name, (Exception,), {})
        return super().__getattr__(name)


class _CommonSubmoduleFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Intercept any `marty_plugin.common*` import and return a stub module."""

    _PREFIXES = ("marty_plugin.common", "src.marty_plugin.common")

    def find_spec(self, fullname, path, target=None):
        for prefix in self._PREFIXES:
            if fullname == prefix or fullname.startswith(prefix + "."):
                return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        mod = _StubModule()
        mod.__name__ = spec.name
        mod.__package__ = spec.name
        mod.__path__ = [f"/mock/{spec.name.replace('.', '/')}"]
        mod.__spec__ = spec
        mod.__loader__ = self
        return mod

    def exec_module(self, module):
        pass  # _StubModule is already usable


# Install finder early so all downstream conftest and test imports are covered
if not any(isinstance(f, _CommonSubmoduleFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _CommonSubmoduleFinder())

# ---------------------------------------------------------------------------

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Generator
from unittest.mock import patch

import pytest
from jwcrypto import jwk


# =============================================================================
# Mock Response Factories
# =============================================================================

class MockPersonInfo:
    """Mock PersonInfo protobuf message."""
    
    def __init__(
        self,
        first_name: str = "John",
        last_name: str = "Doe",
        date_of_birth: str = "1990-01-01",
        place_of_birth: str = "New York, NY",
        nationality: str = "US",
        gender: str = "M",
    ):
        self.first_name = first_name
        self.last_name = last_name
        self.date_of_birth = date_of_birth
        self.place_of_birth = place_of_birth
        self.nationality = nationality
        self.gender = gender


class MockSignatureInfo:
    """Mock SignatureInfo protobuf message."""
    
    def __init__(
        self,
        signature_date: str = "2024-01-01",
        signer_id: str = "test_signer",
        signature: bytes = b"mock_signature",
        is_valid: bool = True,
    ):
        self.signature_date = signature_date
        self.signer_id = signer_id
        self.signature = signature
        self.is_valid = is_valid


class MockDocumentField:
    """Mock DocumentField protobuf message."""
    
    def __init__(
        self,
        field_name: str = "",
        field_value: str = "",
        is_mandatory: bool = False,
        namespace: str = "",
    ):
        self.field_name = field_name
        self.field_value = field_value
        self.is_mandatory = is_mandatory
        self.namespace = namespace


class MockMDocResponse:
    """Mock MDocResponse protobuf message."""
    
    def __init__(
        self,
        mdoc_id: str | None = None,
        document_type: str = "DRIVER_LICENSE",
        document_number: str = "DL123456789",
        issuing_authority: str = "Test DMV",
        issue_date: str = "2024-01-01",
        expiry_date: str = "2034-01-01",
        status: str = "ACTIVE",
        person_info: MockPersonInfo | None = None,
        signature_info: MockSignatureInfo | None = None,
        document_fields: list | None = None,
    ):
        self.mdoc_id = mdoc_id or f"mdoc_{uuid.uuid4().hex[:8]}"
        self.document_type = document_type
        self.document_number = document_number
        self.issuing_authority = issuing_authority
        self.issue_date = issue_date
        self.expiry_date = expiry_date
        self.status = status
        self.person_info = person_info or MockPersonInfo()
        self.signature_info = signature_info or MockSignatureInfo()
        self.document_fields = document_fields or []
        self.error_message = ""
        self.created_at = datetime.now(timezone.utc).isoformat()


class MockCreateMDocResponse:
    """Mock CreateMDocResponse protobuf message."""
    
    def __init__(
        self,
        mdoc_id: str | None = None,
        status: str = "CREATED",
        error: Any = None,
    ):
        self.mdoc_id = mdoc_id or f"mdoc_{uuid.uuid4().hex[:8]}"
        self.status = status
        self.error = error


class MockSignMDocResponse:
    """Mock SignMDocResponse protobuf message."""
    
    def __init__(
        self,
        success: bool = True,
        signature_info: MockSignatureInfo | None = None,
        error_message: str = "",
    ):
        self.success = success
        self.signature_info = signature_info or MockSignatureInfo()
        self.error_message = error_message


class MockVerifyMDocResponse:
    """Mock VerifyMDocResponse protobuf message."""
    
    def __init__(
        self,
        is_valid: bool = True,
        verification_results: list | None = None,
        mdoc_data: MockMDocResponse | None = None,
        error_message: str = "",
    ):
        self.is_valid = is_valid
        self.verification_results = verification_results or []
        self.mdoc_data = mdoc_data
        self.error_message = error_message


class MockPresentMDocResponse:
    """Mock response for PresentMDoc method."""
    
    def __init__(
        self,
        presentation_data: bytes | None = None,
        error_message: str = "",
    ):
        self.presentation_data = presentation_data or b'{}'
        self.error_message = error_message


# =============================================================================
# MDL Mock Classes
# =============================================================================

class MockMDLResponse:
    """Mock MDLResponse protobuf message."""
    
    def __init__(
        self,
        mdl_id: str | None = None,
        first_name: str = "John",
        last_name: str = "Doe",
        date_of_birth: str = "1990-01-01",
        license_number: str = "DL123456789",
        issuing_authority: str = "Test DMV",
        issue_date: str = "2024-01-01",
        expiry_date: str = "2034-01-01",
        status: str = "ACTIVE",
    ):
        self.mdl_id = mdl_id or f"mdl_{uuid.uuid4().hex[:8]}"
        self.first_name = first_name
        self.last_name = last_name
        self.date_of_birth = date_of_birth
        self.license_number = license_number
        self.issuing_authority = issuing_authority
        self.issue_date = issue_date
        self.expiry_date = expiry_date
        self.status = status


class MockCreateMDLResponse:
    """Mock CreateMdlResponse protobuf message."""
    
    def __init__(
        self,
        mdl_id: str | None = None,
        license_number: str = "DL123456789",
        status: str = "CREATED",
    ):
        self.mdl_id = mdl_id or f"mdl_{uuid.uuid4().hex[:8]}"
        self.license_number = license_number
        self.status = status


class MockSignMDLResponse:
    """Mock SignMdlResponse protobuf message."""
    
    def __init__(self, success: bool = True):
        self.success = success


class MockVerifyMDLResponse:
    """Mock VerifyMdlResponse protobuf message."""
    
    def __init__(self, is_valid: bool = True):
        self.is_valid = is_valid


# =============================================================================
# gRPC Stub Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_mdoc_stub() -> MagicMock:
    """
    Create a mock MDocEngine gRPC stub with pre-configured responses.
    
    Returns a MagicMock that simulates the MDocEngineStub behavior.
    """
    stub = MagicMock()
    
    # Store created mDocs for consistency across calls
    created_mdocs: dict[str, MockMDocResponse] = {}
    
    def create_mdoc_side_effect(request):
        """Side effect for CreateMDoc that stores the created mDoc."""
        mdoc_id = f"mdoc_{uuid.uuid4().hex[:8]}"
        person_info = MockPersonInfo(
            first_name=request.person_info.first_name if hasattr(request, 'person_info') else "John",
            last_name=request.person_info.last_name if hasattr(request, 'person_info') else "Doe",
            date_of_birth=request.person_info.date_of_birth if hasattr(request, 'person_info') else "1990-01-01",
        )
        mdoc = MockMDocResponse(
            mdoc_id=mdoc_id,
            document_type=getattr(request, 'document_type', 'DRIVER_LICENSE'),
            document_number=getattr(request, 'document_number', f'DOC{uuid.uuid4().hex[:8].upper()}'),
            person_info=person_info,
            status="CREATED",
        )
        created_mdocs[mdoc_id] = mdoc
        return MockCreateMDocResponse(mdoc_id=mdoc_id, status="CREATED")
    
    def get_mdoc_side_effect(request):
        """Side effect for GetMDoc that returns stored mDoc."""
        mdoc_id = request.mdoc_id
        if mdoc_id in created_mdocs:
            return created_mdocs[mdoc_id]
        # Return a default mock if not found
        return MockMDocResponse(mdoc_id=mdoc_id)
    
    def sign_mdoc_side_effect(request):
        """Side effect for SignMDoc that updates status."""
        mdoc_id = request.mdoc_id
        if mdoc_id in created_mdocs:
            created_mdocs[mdoc_id].status = "ACTIVE"
        return MockSignMDocResponse(success=True)
    
    def present_mdoc_side_effect(request):
        """Side effect for PresentMDoc that returns presentation data."""
        # Handle MagicMock mdoc_id - convert to string if needed
        mdoc_id = request.mdoc_id
        if isinstance(mdoc_id, MagicMock):
            mdoc_id = str(mdoc_id)
        
        mdoc = created_mdocs.get(mdoc_id, MockMDocResponse(mdoc_id=mdoc_id))
        
        # Build presentation data based on requested elements
        # Handle MagicMock list - iterate safely
        requested_elements_attr = getattr(request, 'requested_elements', [])
        if isinstance(requested_elements_attr, MagicMock):
            requested_elements = []
        else:
            requested_elements = list(requested_elements_attr)
        
        presentation_data = {
            "mdoc_id": str(mdoc_id),
            "doc_type": str(mdoc.document_type) if not isinstance(mdoc.document_type, MagicMock) else "DRIVER_LICENSE",
            "requested_elements_data": {},
        }
        
        # Helper to safely get string value from potentially mocked attribute
        def safe_str(val, default=""):
            if val is None or isinstance(val, MagicMock):
                return default
            return str(val)
        
        # Map requested elements to mDoc data with safe extraction
        element_mapping = {
            "given_name": safe_str(mdoc.person_info.first_name, "John"),
            "family_name": safe_str(mdoc.person_info.last_name, "Doe"),
            "birth_date": safe_str(mdoc.person_info.date_of_birth, "1990-01-01"),
            "document_number": safe_str(mdoc.document_number, "DL123456"),
            "license_number": safe_str(mdoc.document_number, "DL123456"),
            "issue_date": safe_str(mdoc.issue_date, "2023-01-01"),
            "expiry_date": safe_str(mdoc.expiry_date, "2028-01-01"),
            "nationality": safe_str(mdoc.person_info.nationality, "US"),
            "status": safe_str(mdoc.status, "ACTIVE"),
            "revoked": False,
        }
        
        for element in requested_elements:
            if element in element_mapping:
                presentation_data["requested_elements_data"][element] = element_mapping[element]
            elif element.startswith("age_over_"):
                # Handle age verification
                min_age = int(element.split("_")[-1])
                dob_str = safe_str(mdoc.person_info.date_of_birth, "1990-01-01")
                birth_date = datetime.strptime(dob_str, "%Y-%m-%d")
                age = (datetime.now() - birth_date).days // 365
                presentation_data["requested_elements_data"][element] = age >= min_age
        
        return MockPresentMDocResponse(
            presentation_data=json.dumps(presentation_data).encode()
        )
    
    def verify_mdoc_side_effect(request):
        """Side effect for VerifyMDoc."""
        mdoc_id = getattr(request, 'mdoc_id', None)
        if mdoc_id and mdoc_id in created_mdocs:
            mdoc = created_mdocs[mdoc_id]
            # Check if expired
            expiry = datetime.strptime(mdoc.expiry_date, "%Y-%m-%d")
            is_valid = datetime.now() < expiry and mdoc.status == "ACTIVE"
            return MockVerifyMDocResponse(is_valid=is_valid, mdoc_data=mdoc)
        return MockVerifyMDocResponse(is_valid=True)
    
    # Configure stub methods with side effects
    stub.CreateMDoc.side_effect = create_mdoc_side_effect
    stub.GetMDoc.side_effect = get_mdoc_side_effect
    stub.SignMDoc.side_effect = sign_mdoc_side_effect
    stub.PresentMDoc.side_effect = present_mdoc_side_effect
    stub.VerifyMDoc.side_effect = verify_mdoc_side_effect
    
    # Store reference to created_mdocs for test access
    stub._created_mdocs = created_mdocs
    
    return stub


@pytest.fixture
def mock_mdl_stub() -> MagicMock:
    """
    Create a mock MdlEngine gRPC stub with pre-configured responses.
    
    Returns a MagicMock that simulates the MdlEngineStub behavior.
    """
    stub = MagicMock()
    
    # Store created mDLs for consistency
    created_mdls: dict[str, MockMDLResponse] = {}
    
    def create_mdl_side_effect(request):
        """Side effect for CreateMdl."""
        mdl_id = f"mdl_{uuid.uuid4().hex[:8]}"
        mdl = MockMDLResponse(
            mdl_id=mdl_id,
            first_name=getattr(request, 'first_name', 'John'),
            last_name=getattr(request, 'last_name', 'Doe'),
            date_of_birth=getattr(request, 'date_of_birth', '1990-01-01'),
            license_number=getattr(request, 'license_number', f'DL{uuid.uuid4().hex[:8].upper()}'),
            status="CREATED",
        )
        created_mdls[mdl_id] = mdl
        return MockCreateMDLResponse(mdl_id=mdl_id, license_number=mdl.license_number)
    
    def get_mdl_side_effect(request):
        """Side effect for GetMdl."""
        mdl_id = request.mdl_id
        if mdl_id in created_mdls:
            return created_mdls[mdl_id]
        return MockMDLResponse(mdl_id=mdl_id)
    
    def sign_mdl_side_effect(request):
        """Side effect for SignMdl."""
        mdl_id = request.mdl_id
        if mdl_id in created_mdls:
            created_mdls[mdl_id].status = "ACTIVE"
        return MockSignMDLResponse(success=True)
    
    def verify_mdl_side_effect(request):
        """Side effect for VerifyMdl."""
        return MockVerifyMDLResponse(is_valid=True)
    
    stub.CreateMdl.side_effect = create_mdl_side_effect
    stub.GetMdl.side_effect = get_mdl_side_effect
    stub.SignMdl.side_effect = sign_mdl_side_effect
    stub.VerifyMdl.side_effect = verify_mdl_side_effect
    
    stub._created_mdls = created_mdls
    
    return stub


@pytest.fixture
def mock_grpc_channel() -> Generator[MagicMock, None, None]:
    """
    Mock the gRPC channel creation.
    
    Patches grpc.insecure_channel to return a mock channel.
    """
    with patch('grpc.insecure_channel') as mock_channel:
        channel_instance = MagicMock()
        mock_channel.return_value = channel_instance
        yield mock_channel


# =============================================================================
# Cryptographic Key Fixtures
# =============================================================================

@pytest.fixture
def issuer_jwk() -> jwk.JWK:
    """Generate a real EC P-256 key for issuer."""
    return jwk.JWK.generate(kty="EC", crv="P-256")


@pytest.fixture
def holder_jwk() -> jwk.JWK:
    """Generate a real EC P-256 key for holder."""
    return jwk.JWK.generate(kty="EC", crv="P-256")


@pytest.fixture
def verifier_jwk() -> jwk.JWK:
    """Generate a real EC P-256 key for verifier."""
    return jwk.JWK.generate(kty="EC", crv="P-256")


# =============================================================================
# OpenID4VP Test Data Fixtures
# =============================================================================

@pytest.fixture
def sample_presentation_definition() -> dict[str, Any]:
    """Sample OpenID4VP presentation definition."""
    return {
        "id": str(uuid.uuid4()),
        "input_descriptors": [
            {
                "id": "input_driver_license",
                "format": {
                    "mso_mdoc": {
                        "alg": ["ES256", "ES384", "ES512"]
                    }
                },
                "constraints": {
                    "fields": [
                        {"path": ["$.given_name"], "purpose": "Verify given name"},
                        {"path": ["$.family_name"], "purpose": "Verify family name"},
                        {"path": ["$.birth_date"], "purpose": "Verify birth date"},
                        {"path": ["$.document_number"], "purpose": "Verify document number"},
                    ]
                }
            }
        ]
    }


@pytest.fixture
def sample_age_verification_definition() -> dict[str, Any]:
    """Sample OpenID4VP presentation definition for age verification."""
    return {
        "id": str(uuid.uuid4()),
        "input_descriptors": [
            {
                "id": "age_verification",
                "format": {
                    "mso_mdoc": {
                        "alg": ["ES256"]
                    }
                },
                "constraints": {
                    "fields": [
                        {"path": ["$.age_over_21"], "purpose": "Verify age is over 21"}
                    ]
                }
            }
        ]
    }


@pytest.fixture
def expired_mdoc_data() -> dict[str, Any]:
    """Data for creating an expired mDoc."""
    return {
        "user_id": f"expired_user_{uuid.uuid4()}",
        "document_type": "DRIVER_LICENSE",
        "document_number": f"EXP{uuid.uuid4().hex[:8].upper()}",
        "issuing_authority": "Test DMV",
        "issue_date": "2020-01-01",
        "expiry_date": "2021-01-01",  # Expired
        "person_info": {
            "first_name": "Expired",
            "last_name": "User",
            "date_of_birth": "1980-01-01",
            "nationality": "US",
        }
    }


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture
def base_url() -> str:
    """Base URL for API testing."""
    return "http://localhost:8000"


@pytest.fixture
def mdoc_service_url() -> str:
    """mDoc gRPC service URL."""
    return "localhost:8086"


@pytest.fixture
def mdl_service_url() -> str:
    """mDL gRPC service URL."""
    return "localhost:8085"
