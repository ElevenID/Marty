"""
Test configuration for Marty test suite.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import tempfile
import types
from abc import ABCMeta
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

# ---------------------------------------------------------------------------
# marty_plugin.common stub (must be installed BEFORE any transitive imports)
#
# Several modules in the codebase depend on marty_plugin.common.* which is
# native/Rust code not available in the pure-Python test env.  We install a
# meta-path finder here so *every* test directory benefits from it.
# ---------------------------------------------------------------------------


class _StubModule(types.ModuleType):
    """Module stub that returns MagicMock for any missing attribute."""

    _CLASS_NAMES = {"SODParsingError", "ServiceConfig", "BaseService"}

    # Real implementations for functions that can't be mocked
    _ICAO_WEIGHTS = [7, 3, 1]

    @staticmethod
    def _compute_check_digit(data: str) -> str:
        """ICAO 9303 check digit (weights 7-3-1)."""
        total = 0
        for i, ch in enumerate(str(data)):
            if ch == '<':
                val = 0
            elif ch.isdigit():
                val = int(ch)
            elif ch.isalpha():
                val = ord(ch.upper()) - 55
            else:
                val = 0
            total += val * _StubModule._ICAO_WEIGHTS[i % 3]
        return str(total % 10)

    @staticmethod
    def _validate_check_digit(data: str, check_digit: str) -> bool:
        """Validate an ICAO 9303 check digit."""
        return _StubModule._compute_check_digit(data) == str(check_digit)

    def __getattr__(self, name):
        if name == "compute_check_digit":
            return self._compute_check_digit
        if name == "validate_check_digit":
            return self._validate_check_digit
        if name in self._CLASS_NAMES:
            if "Error" in name:
                cls = type(name, (Exception,), {})
            elif name == "BaseService":
                cls = ABCMeta(name, (object,), {})
            else:
                cls = type(name, (object,), {})
            setattr(self, name, cls)
            return cls
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _make_stub(name: str) -> "_StubModule":
    mod = _StubModule(name)
    mod.__path__ = []
    mod.__package__ = name
    return mod


class _MartyPluginCommonFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Catch-all finder for any ``marty_plugin.common.*`` import (with or without src. prefix)."""

    _PREFIXES = ("marty_plugin.common", "src.marty_plugin.common")

    def find_spec(self, fullname, path, target=None):
        for prefix in self._PREFIXES:
            if fullname == prefix or fullname.startswith(prefix + "."):
                return importlib.machinery.ModuleSpec(fullname, self)
        return None

    def create_module(self, spec):
        return _make_stub(spec.name)

    def exec_module(self, module):
        pass


if not any(isinstance(f, _MartyPluginCommonFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _MartyPluginCommonFinder())

_COMMON_STUBS = [
    "marty_plugin.common",
    "marty_plugin.common.crypto",
    "marty_plugin.common.crypto.data_group_hasher",
    "marty_plugin.common.crypto.sod_parser",
    "marty_plugin.common.crypto.certificate_validator",
    "marty_plugin.common.crypto.vds_nc_keys",
    "marty_plugin.common.crypto_bridge",
    "marty_plugin.common.crypto_role",
    "marty_plugin.common.config_manager",
    "marty_plugin.common.models",
    "marty_plugin.common.models.asn1_structures",
    "marty_plugin.common.infrastructure",
    "marty_plugin.common.infrastructure.trust_models",
    "marty_plugin.common.security",
    "marty_plugin.common.security.encryption",
]
for _name in _COMMON_STUBS:
    if _name not in sys.modules:
        sys.modules[_name] = _make_stub(_name)

_common_parent = sys.modules.get("marty_plugin.common")
if _common_parent is not None:
    for _name in _COMMON_STUBS:
        if not _name.startswith("marty_plugin.common."):
            continue
        _child_path = _name.removeprefix("marty_plugin.common.")
        if "." not in _child_path:
            setattr(_common_parent, _child_path, sys.modules[_name])

if "marty_plugin" in sys.modules:
    sys.modules["marty_plugin"].common = sys.modules["marty_plugin.common"]

# ---------------------------------------------------------------------------
# Wire pure-Python models into marty_plugin.common stubs so that production
# code importing from marty_plugin.common.models.* gets the real classes
# instead of MagicMock.
# ---------------------------------------------------------------------------

# Passport models (Gender, MRZData, etc.)
_passport_stub_name = "marty_plugin.common.models.passport"
if _passport_stub_name not in sys.modules:
    sys.modules[_passport_stub_name] = _make_stub(_passport_stub_name)
try:
    from marty_backend_common.models import passport as _real_passport
    _p_stub = sys.modules[_passport_stub_name]
    for _attr in dir(_real_passport):
        if not _attr.startswith("_"):
            setattr(_p_stub, _attr, getattr(_real_passport, _attr))
except ImportError:
    pass

# MRZ validation models
_mrz_val_stub_name = "marty_plugin.common.models.mrz_validation"
if _mrz_val_stub_name not in sys.modules:
    sys.modules[_mrz_val_stub_name] = _make_stub(_mrz_val_stub_name)
try:
    from marty_backend_common.models import mrz_validation as _real_mrz_val
    _m_stub = sys.modules[_mrz_val_stub_name]
    for _attr in dir(_real_mrz_val):
        if not _attr.startswith("_"):
            setattr(_m_stub, _attr, getattr(_real_mrz_val, _attr))
except ImportError:
    pass

# Exceptions — inject the real MartyServiceException so isinstance/except works
_exc_stub_name = "marty_plugin.common.exceptions"
if _exc_stub_name not in sys.modules:
    sys.modules[_exc_stub_name] = _make_stub(_exc_stub_name)
try:
    from marty_backend_common.exceptions import MartyServiceException as _MSE
    sys.modules[_exc_stub_name].MartyServiceException = _MSE
except ImportError:
    pass

# crypto_bridge — add sha256 real implementation and Certificate class
_crypto_bridge_stub = sys.modules.get("marty_plugin.common.crypto_bridge")
if _crypto_bridge_stub is not None:
    import hashlib as _hashlib
    _crypto_bridge_stub.sha256 = lambda data: _hashlib.sha256(data).digest()

    # Certificate must be a real type (not MagicMock) so isinstance() works
    from cryptography import x509 as _x509

    class _CertificateBridge:
        """Stub for Rust crypto_bridge.Certificate — wraps cryptography x509.Certificate."""
        def __init__(self, crypto_cert=None):
            self._cert = crypto_cert

        def to_cryptography(self):
            return self._cert

        @classmethod
        def from_der(cls, der_bytes: bytes):
            cert = _x509.load_der_x509_certificate(der_bytes)
            return cls(cert)

        def __getattr__(self, name):
            # Delegate any unresolved attribute to the wrapped certificate
            if name.startswith("_"):
                raise AttributeError(name)
            if self._cert is not None:
                return getattr(self._cert, name)
            raise AttributeError(f"No certificate loaded, cannot access '{name}'")

    _crypto_bridge_stub.Certificate = _CertificateBridge

    # Exception types used in verifier
    class _ExtensionNotFound(Exception):
        pass
    _crypto_bridge_stub.ExtensionNotFound = _ExtensionNotFound
    _crypto_bridge_stub.SubjectAlternativeName = _x509.SubjectAlternativeName
    _crypto_bridge_stub.DNSName = _x509.DNSName
    _crypto_bridge_stub.UniformResourceIdentifier = _x509.UniformResourceIdentifier

    # 3DES-CBC encrypt/decrypt — pure-Python fallback via cryptography library
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    def _tdes_cbc_encrypt(key: bytes, data: bytes, iv: bytes) -> bytes:
        cipher = Cipher(algorithms.TripleDES(key), modes.CBC(iv))
        enc = cipher.encryptor()
        return enc.update(data) + enc.finalize()

    def _tdes_cbc_decrypt(key: bytes, data: bytes, iv: bytes) -> bytes:
        cipher = Cipher(algorithms.TripleDES(key), modes.CBC(iv))
        dec = cipher.decryptor()
        return dec.update(data) + dec.finalize()

    _crypto_bridge_stub.tdes_cbc_encrypt = _tdes_cbc_encrypt
    _crypto_bridge_stub.tdes_cbc_decrypt = _tdes_cbc_decrypt

    # P-256 key generation and ECDH — pure-Python fallback
    from cryptography.hazmat.primitives.asymmetric import ec as _ec, padding as _padding
    from cryptography.hazmat.primitives import hashes as _hashes, serialization as _ser

    def _p256_generate():
        private_key = _ec.generate_private_key(_ec.SECP256R1())
        public_bytes = private_key.public_key().public_bytes(
            _ser.Encoding.X962, _ser.PublicFormat.UncompressedPoint
        )
        # Return (private_key_object, public_key_bytes)
        return private_key, public_bytes

    def _p256_agree(private_key, peer_public_bytes: bytes) -> bytes:
        peer_public = _ec.EllipticCurvePublicKey.from_encoded_point(
            _ec.SECP256R1(), peer_public_bytes
        )
        return private_key.exchange(_ec.ECDH(), peer_public)

    def _ecdsa_p256_generate():
        private_key = _ec.generate_private_key(_ec.SECP256R1())
        public_bytes = private_key.public_key().public_bytes(
            _ser.Encoding.X962, _ser.PublicFormat.UncompressedPoint
        )
        return private_key, public_bytes

    def _ecdsa_p384_generate():
        private_key = _ec.generate_private_key(_ec.SECP384R1())
        public_bytes = private_key.public_key().public_bytes(
            _ser.Encoding.X962, _ser.PublicFormat.UncompressedPoint
        )
        return private_key, public_bytes

    def _raw_private_key_to_pkcs8(private_key, key_type: str) -> bytes:
        if hasattr(private_key, "private_bytes"):
            return private_key.private_bytes(
                _ser.Encoding.DER,
                _ser.PrivateFormat.PKCS8,
                _ser.NoEncryption(),
            )
        raise TypeError(f"Unsupported private key object for {key_type}")

    def _raw_public_key_to_spki(public_key, key_type: str) -> bytes:
        if hasattr(public_key, "public_bytes"):
            return public_key.public_bytes(
                _ser.Encoding.DER,
                _ser.PublicFormat.SubjectPublicKeyInfo,
            )
        if isinstance(public_key, bytes):
            curve = _ec.SECP256R1() if key_type == "P256" else _ec.SECP384R1()
            key = _ec.EllipticCurvePublicKey.from_encoded_point(curve, public_key)
            return key.public_bytes(
                _ser.Encoding.DER,
                _ser.PublicFormat.SubjectPublicKeyInfo,
            )
        raise TypeError(f"Unsupported public key object for {key_type}")

    def _pkcs8_to_raw_private_key(der_bytes: bytes):
        key = _ser.load_der_private_key(der_bytes, password=None)
        if hasattr(key, "curve"):
            curve_name = "P384" if isinstance(key.curve, _ec.SECP384R1) else "P256"
            return key, curve_name
        return key, "RSA"

    def _spki_to_raw_public_key(der_bytes: bytes):
        key = _ser.load_der_public_key(der_bytes)
        if hasattr(key, "curve"):
            curve_name = "P384" if isinstance(key.curve, _ec.SECP384R1) else "P256"
            return key, curve_name
        return key, "RSA"

    _crypto_bridge_stub.p256_generate = _p256_generate
    _crypto_bridge_stub.p256_agree = _p256_agree
    _crypto_bridge_stub.ecdsa_p256_generate = _ecdsa_p256_generate
    _crypto_bridge_stub.ecdsa_p384_generate = _ecdsa_p384_generate
    _crypto_bridge_stub.raw_private_key_to_pkcs8 = _raw_private_key_to_pkcs8
    _crypto_bridge_stub.raw_public_key_to_spki = _raw_public_key_to_spki
    _crypto_bridge_stub.pkcs8_to_raw_private_key = _pkcs8_to_raw_private_key
    _crypto_bridge_stub.spki_to_raw_public_key = _spki_to_raw_public_key

    # Encoding enum — wire real serialization.Encoding so public_bytes() works
    _crypto_bridge_stub.Encoding = _ser.Encoding

    # RSA key generation and key PEM helpers — pure-Python fallback
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    def _rsa_generate(key_size: int = 2048):
        k = _rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        priv = k.private_bytes(_ser.Encoding.DER, _ser.PrivateFormat.PKCS8, _ser.NoEncryption())
        pub = k.public_key().public_bytes(_ser.Encoding.DER, _ser.PublicFormat.SubjectPublicKeyInfo)
        return priv, pub

    def _save_private_key_pem(der_bytes: bytes) -> str:
        k = _ser.load_der_private_key(der_bytes, password=None)
        return k.private_bytes(_ser.Encoding.PEM, _ser.PrivateFormat.PKCS8, _ser.NoEncryption()).decode()

    def _load_private_key_pem(pem: str) -> bytes:
        k = _ser.load_pem_private_key(pem.encode(), password=None)
        return k.private_bytes(_ser.Encoding.DER, _ser.PrivateFormat.PKCS8, _ser.NoEncryption())

    def _extract_public_key(priv_der: bytes) -> bytes:
        k = _ser.load_der_private_key(priv_der, password=None)
        return k.public_key().public_bytes(_ser.Encoding.DER, _ser.PublicFormat.SubjectPublicKeyInfo)

    def _save_public_key_pem(pub_der: bytes) -> str:
        k = _ser.load_der_public_key(pub_der)
        return k.public_bytes(_ser.Encoding.PEM, _ser.PublicFormat.SubjectPublicKeyInfo).decode()

    def _load_public_key_pem(pem: str) -> bytes:
        k = _ser.load_pem_public_key(pem.encode())
        return k.public_bytes(_ser.Encoding.DER, _ser.PublicFormat.SubjectPublicKeyInfo)

    def _detect_private_key_type(der_bytes: bytes) -> str:
        k = _ser.load_der_private_key(der_bytes, password=None)
        if isinstance(k, _rsa.RSAPrivateKey):
            return "RSA"
        if isinstance(k, _ec.EllipticCurvePrivateKey):
            if isinstance(k.curve, _ec.SECP384R1):
                return "P-384"
            if isinstance(k.curve, _ec.SECP256R1):
                return "P-256"
        raise ValueError("Unsupported private key type")

    def _detect_public_key_type(der_bytes: bytes) -> str:
        k = _ser.load_der_public_key(der_bytes)
        if isinstance(k, _rsa.RSAPublicKey):
            return "RSA"
        if isinstance(k, _ec.EllipticCurvePublicKey):
            if isinstance(k.curve, _ec.SECP384R1):
                return "P-384"
            if isinstance(k.curve, _ec.SECP256R1):
                return "P-256"
        raise ValueError("Unsupported public key type")

    def _rsa_pkcs1_sha256_sign(priv_der: bytes, data: bytes) -> bytes:
        k = _ser.load_der_private_key(priv_der, password=None)
        return k.sign(data, _padding.PKCS1v15(), _hashes.SHA256())

    def _rsa_pkcs1_sha384_sign(priv_der: bytes, data: bytes) -> bytes:
        k = _ser.load_der_private_key(priv_der, password=None)
        return k.sign(data, _padding.PKCS1v15(), _hashes.SHA384())

    def _rsa_pkcs1_sha512_sign(priv_der: bytes, data: bytes) -> bytes:
        k = _ser.load_der_private_key(priv_der, password=None)
        return k.sign(data, _padding.PKCS1v15(), _hashes.SHA512())

    def _rsa_pkcs1_sha256_verify(pub_der: bytes, data: bytes, signature: bytes) -> bool:
        k = _ser.load_der_public_key(pub_der)
        try:
            k.verify(signature, data, _padding.PKCS1v15(), _hashes.SHA256())
            return True
        except Exception:
            return False

    def _rsa_pkcs1_sha384_verify(pub_der: bytes, data: bytes, signature: bytes) -> bool:
        k = _ser.load_der_public_key(pub_der)
        try:
            k.verify(signature, data, _padding.PKCS1v15(), _hashes.SHA384())
            return True
        except Exception:
            return False

    def _rsa_pkcs1_sha512_verify(pub_der: bytes, data: bytes, signature: bytes) -> bool:
        k = _ser.load_der_public_key(pub_der)
        try:
            k.verify(signature, data, _padding.PKCS1v15(), _hashes.SHA512())
            return True
        except Exception:
            return False

    def _ecdsa_p256_sign(private_key, data: bytes) -> bytes:
        return private_key.sign(data, _ec.ECDSA(_hashes.SHA256()))

    def _ecdsa_p384_sign(private_key, data: bytes) -> bytes:
        return private_key.sign(data, _ec.ECDSA(_hashes.SHA384()))

    def _ecdsa_p256_verify(public_key, data: bytes, signature: bytes) -> bool:
        try:
            public_key.verify(signature, data, _ec.ECDSA(_hashes.SHA256()))
            return True
        except Exception:
            return False

    def _ecdsa_p384_verify(public_key, data: bytes, signature: bytes) -> bool:
        try:
            public_key.verify(signature, data, _ec.ECDSA(_hashes.SHA384()))
            return True
        except Exception:
            return False

    _crypto_bridge_stub.rsa_generate = _rsa_generate
    _crypto_bridge_stub.save_private_key_pem = _save_private_key_pem
    _crypto_bridge_stub.load_private_key_pem = _load_private_key_pem
    _crypto_bridge_stub.extract_public_key = _extract_public_key
    _crypto_bridge_stub.save_public_key_pem = _save_public_key_pem
    _crypto_bridge_stub.load_public_key_pem = _load_public_key_pem
    _crypto_bridge_stub.detect_private_key_type = _detect_private_key_type
    _crypto_bridge_stub.detect_public_key_type = _detect_public_key_type
    _crypto_bridge_stub.rsa_pkcs1_sha256_sign = _rsa_pkcs1_sha256_sign
    _crypto_bridge_stub.rsa_pkcs1_sha384_sign = _rsa_pkcs1_sha384_sign
    _crypto_bridge_stub.rsa_pkcs1_sha512_sign = _rsa_pkcs1_sha512_sign
    _crypto_bridge_stub.rsa_pkcs1_sha256_verify = _rsa_pkcs1_sha256_verify
    _crypto_bridge_stub.rsa_pkcs1_sha384_verify = _rsa_pkcs1_sha384_verify
    _crypto_bridge_stub.rsa_pkcs1_sha512_verify = _rsa_pkcs1_sha512_verify
    _crypto_bridge_stub.ecdsa_p256_sign = _ecdsa_p256_sign
    _crypto_bridge_stub.ecdsa_p384_sign = _ecdsa_p384_sign
    _crypto_bridge_stub.ecdsa_p256_verify = _ecdsa_p256_verify
    _crypto_bridge_stub.ecdsa_p384_verify = _ecdsa_p384_verify

# ASN.1 structures — wire real classes so sod_signer/sod_parser work
_asn1_stub_name = "marty_plugin.common.models.asn1_structures"
if _asn1_stub_name not in sys.modules:
    sys.modules[_asn1_stub_name] = _make_stub(_asn1_stub_name)
try:
    from marty_backend_common.models import asn1_structures as _real_asn1
    _a_stub = sys.modules[_asn1_stub_name]
    for _attr in dir(_real_asn1):
        if not _attr.startswith("_"):
            setattr(_a_stub, _attr, getattr(_real_asn1, _attr))
except ImportError:
    pass

# crypto.certificate_validator — wire real classes (CertificateChainValidator, etc.)
_cv_stub_name = "marty_plugin.common.crypto.certificate_validator"
if _cv_stub_name not in sys.modules:
    sys.modules[_cv_stub_name] = _make_stub(_cv_stub_name)
try:
    from marty_backend_common.crypto import certificate_validator as _real_cv
    _cv_stub = sys.modules[_cv_stub_name]
    for _attr in dir(_real_cv):
        if not _attr.startswith("_"):
            setattr(_cv_stub, _attr, getattr(_real_cv, _attr))
except ImportError:
    pass

# crypto.data_group_hasher — stub verify_passport_data_groups to return success
_dgh_stub_name = "marty_plugin.common.crypto.data_group_hasher"
if _dgh_stub_name not in sys.modules:
    sys.modules[_dgh_stub_name] = _make_stub(_dgh_stub_name)
_dgh_stub = sys.modules[_dgh_stub_name]


def _stub_verify_passport_data_groups(sod_data, dg_dict):
    """Stub that returns a successful verification result."""
    return (True, [], {"data_groups_verified": len(dg_dict), "hash_algorithm": "SHA-256"})


_dgh_stub.verify_passport_data_groups = _stub_verify_passport_data_groups

# MRZ utils — wire real MRZFormatter so generate_td1_mrz / generate_td3_mrz work
_mrz_utils_stub_name = "marty_plugin.common.utils.mrz_utils"
for _n in ("marty_plugin.common.utils", _mrz_utils_stub_name):
    if _n not in sys.modules:
        sys.modules[_n] = _make_stub(_n)
try:
    from marty_backend_common.utils import mrz_utils as _real_mrz_utils
    _mu_stub = sys.modules[_mrz_utils_stub_name]
    for _attr in dir(_real_mrz_utils):
        if not _attr.startswith("_"):
            setattr(_mu_stub, _attr, getattr(_real_mrz_utils, _attr))
except ImportError:
    pass

# VC / SD-JWT — wire real b64url_encode into the stub
for _n in ("marty_plugin.common.vc", "marty_plugin.common.vc.sd_jwt"):
    if _n not in sys.modules:
        sys.modules[_n] = _make_stub(_n)
try:
    from marty_backend_common.utils.base64_utils import b64url_encode as _b64url
    sys.modules["marty_plugin.common.vc.sd_jwt"]._b64url_encode = _b64url
except ImportError:
    pass

# ---------------------------------------------------------------------------

try:
    from marty_backend_common.models.passport import Gender, MRZData
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal test environments
    Gender = Mock()
    MRZData = Mock()
from tests.fixtures.data_loader import test_data_loader


# Kubernetes test fixtures
@pytest.fixture(scope="session")
def k8s_orchestrator():
    """Session-scoped Kubernetes test orchestrator."""
    from tests.k8s_test_orchestrator import KubernetesTestOrchestrator

    project_root = Path(__file__).parent.parent
    orchestrator = KubernetesTestOrchestrator(
        project_root=project_root,
        namespace="marty-test",
    )
    return orchestrator


@pytest.fixture
def k8s_test_env(k8s_orchestrator, request):
    """Kubernetes test environment context manager."""
    from tests.k8s_test_orchestrator import TestMode

    # Determine test mode from markers
    test_mode = TestMode.UNIT  # default
    if request.node.get_closest_marker("integration"):
        test_mode = TestMode.INTEGRATION
    elif request.node.get_closest_marker("e2e"):
        test_mode = TestMode.E2E

    with k8s_orchestrator.test_environment(test_mode) as env:
        yield env


@pytest.fixture
def k8s_service_urls(k8s_test_env):
    """Get service URLs for Kubernetes-deployed services."""
    return {
        service_name: k8s_test_env.get_service_url(service_name)
        for service_name in k8s_test_env.services.keys()
    }


# Test markers
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "k8s: mark test as requiring Kubernetes")
    config.addinivalue_line("markers", "external: mark test as requiring external services")
    config.addinivalue_line("markers", "mrz: mark test as MRZ related")
    config.addinivalue_line("markers", "ocr: mark test as OCR related")
    config.addinivalue_line("markers", "pdf: mark test as PDF related")
    config.addinivalue_line(
        "markers", "document_processing: mark test as document processing service related"
    )


# Collection settings
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    for item in items:
        # Add unit marker to unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Add integration marker to integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Add k8s marker to Kubernetes tests
        if "k8s" in str(item.fspath) or "kubernetes" in str(item.fspath):
            item.add_marker(pytest.mark.k8s)

        # Add document processing marker
        if "document_processing" in str(item.fspath):
            item.add_marker(pytest.mark.document_processing)

        # Add specific markers based on file names
        if "mrz" in item.name.lower():
            item.add_marker(pytest.mark.mrz)
        if "ocr" in item.name.lower():
            item.add_marker(pytest.mark.ocr)
        if "pdf" in item.name.lower():
            item.add_marker(pytest.mark.pdf)


# Test environment setup
@pytest.fixture(scope="session", autouse=True)
def test_environment_setup():
    """Set up test environment."""

    # Set test environment variables
    original_env = os.environ.copy()

    os.environ["MARTY_ENV"] = "testing"
    os.environ["MARTY_LOG_LEVEL"] = "DEBUG"
    os.environ["MARTY_DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_martydb"

    yield

    # Restore environment
    os.environ.clear()
    os.environ.update(original_env)


# Skip tests if dependencies are not available
def pytest_runtest_setup(item):
    """Skip tests based on availability of dependencies."""

    # Skip PassportEye tests if not available
    if item.get_closest_marker("external"):
        try:
            import passporteye
        except ImportError:
            pytest.skip("PassportEye not available")

    # Skip numpy/skimage tests if not available
    if item.get_closest_marker("ocr"):
        try:
            import numpy as np
            import skimage
        except ImportError:
            pytest.skip("numpy/skimage not available for OCR tests")

    # Skip docker tests if docker not available
    if item.get_closest_marker("docker"):
        import subprocess

        try:
            subprocess.run(["docker", "version"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            pytest.skip("Docker not available")


# Custom test result reporting
def pytest_report_teststatus(report, config):
    """Custom test status reporting."""
    if report.when == "call":
        if report.outcome == "passed":
            return report.outcome, "P", f"PASSED {report.nodeid}"
        if report.outcome == "failed":
            return report.outcome, "F", f"FAILED {report.nodeid}"
        if report.outcome == "skipped":
            return report.outcome, "S", f"SKIPPED {report.nodeid}"
    return None


# Test Data Classes
class TestDataFixtures:
    """Container for test data fixtures."""

    # Sample MRZ data for testing
    SAMPLE_TD3_MRZ = (
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"
    )

    SAMPLE_MRZ_DATA = MRZData(
        document_type="P",
        issuing_country="UTO",
        document_number="L898902C3",
        surname="ERIKSSON",
        given_names="ANNA MARIA",
        nationality="UTO",
        date_of_birth="740812",
        gender=Gender.FEMALE,
        date_of_expiry="120415",
        personal_number="ZE184226B",
    )

    # Sample certificate data
    SAMPLE_CERTIFICATE_DATA = {
        "certificate_id": "cert_test_001",
        "subject": "CN=Test Certificate,O=Test Org,C=US",
        "issuer": "CN=Test CA,O=Test CA Org,C=US",
        "not_before": "2024-01-01T00:00:00Z",
        "not_after": "2025-01-01T00:00:00Z",
        "serial_number": "123456789",
    }

    # Sample passport data
    SAMPLE_PASSPORT_DATA = {
        "passport_number": "P123456789",
        "issuing_country": "UTO",
        "holder_name": "ANNA MARIA ERIKSSON",
        "date_of_birth": "1974-08-12",
        "date_of_expiry": "2012-04-15",
        "nationality": "UTO",
        "gender": "F",
    }


class MockPassportEngineStub:
    """Mock passport engine stub for testing."""

    def ProcessPassport(self, request):
        """Mock ProcessPassport method."""

        mock_response = Mock()
        mock_response.status = "SUCCESS"
        mock_response.passport_data = TestDataFixtures.SAMPLE_PASSPORT_DATA
        return mock_response


class MockCscaServiceStub:
    """Mock CSCA service stub for testing."""

    def CreateCertificate(self, request):
        """Mock CreateCertificate method."""

        mock_response = Mock()
        mock_response.status = "SUCCESS"
        mock_response.certificate_id = "cert_test_001"
        return mock_response

    def CheckExpiringCertificates(self, request):
        """Mock CheckExpiringCertificates method."""

        mock_response = Mock()
        mock_response.certificates = []
        return mock_response


# Test Fixtures
@pytest.fixture
def test_data():
    """Provide test data fixtures."""
    return TestDataFixtures()


@pytest.fixture
def mock_mrz_data():
    """Provide mock MRZ data."""
    return TestDataFixtures.SAMPLE_MRZ_DATA


@pytest.fixture
def sample_mrz_string():
    """Provide sample MRZ string."""
    return TestDataFixtures.SAMPLE_TD3_MRZ


@pytest.fixture
def mock_certificate():
    """Provide mock certificate data."""
    return TestDataFixtures.SAMPLE_CERTIFICATE_DATA


@pytest.fixture
def mock_passport():
    """Provide mock passport data."""
    return TestDataFixtures.SAMPLE_PASSPORT_DATA


@pytest.fixture
def temp_directory():
    """Provide a temporary directory for test files."""

    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_grpc_channel():
    """Provide a mock gRPC channel."""

    mock_channel = Mock()
    mock_channel.__enter__ = Mock(return_value=mock_channel)
    mock_channel.__exit__ = Mock(return_value=None)
    return mock_channel


@pytest.fixture
def mock_grpc_stub():
    """Provide a mock gRPC stub."""

    return Mock()


@pytest.fixture(scope="session")
def project_root():
    """Provide the project root path."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def test_config():
    """Provide test configuration."""
    return {
        "services": {
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "test_martydb",
                "username": "test_user",
                "password": "test_password",
            },
            "grpc_services": {
                "csca_service": {"host": "localhost", "port": 50051},
                "passport_engine": {"host": "localhost", "port": 50052},
                "trust_anchor": {"host": "localhost", "port": 50053},
            },
        },
        "testing": {"timeout": 30, "retry_attempts": 3, "mock_external_services": True},
    }


@pytest.fixture
def mock_service_response():
    """Provide mock service response."""

    mock_response = Mock()
    mock_response.status = "SUCCESS"
    mock_response.message = "Test operation completed"
    return mock_response


@pytest.fixture
def mock_passport_engine_stub():
    """Provide mock passport engine stub."""
    return MockPassportEngineStub()


@pytest.fixture
def mock_csca_service_stub():
    """Provide mock CSCA service stub."""
    return MockCscaServiceStub()


@pytest.fixture
def test_pdf_bytes():
    """Provide test PDF bytes."""
    return create_test_pdf_bytes()


# Real Data Fixtures using scraped data
@pytest.fixture
def real_passport_data():
    """Provide real passport data from scraped files."""
    return test_data_loader.load_passport_data()


@pytest.fixture
def sample_passport_collection():
    """Provide a collection of sample passport data for comprehensive testing."""
    return test_data_loader.get_sample_passports(10)


@pytest.fixture
def regular_passports():
    """Provide regular passports starting with 'P'."""
    return test_data_loader.get_passport_by_type("P")


@pytest.fixture
def iceland_passports():
    """Provide Iceland passports starting with 'IS'."""
    return test_data_loader.get_passport_by_type("IS")


@pytest.fixture
def special_passports():
    """Provide special passports starting with 'PM'."""
    return test_data_loader.get_passport_by_type("PM")


@pytest.fixture
def invalid_passport_data():
    """Provide invalid passport data for negative testing."""
    return test_data_loader.load_invalid_passport_data()


@pytest.fixture
def csca_lifecycle_data():
    """Provide real CSCA certificate lifecycle data."""
    return test_data_loader.load_csca_lifecycle_data()


@pytest.fixture
def trust_store_config():
    """Provide trust store configuration data."""
    return test_data_loader.load_trust_store_data()


@pytest.fixture
def passport_test_images():
    """Provide real passport test images."""
    return test_data_loader.get_passport_images()


@pytest.fixture
def test_image_files():
    """Provide all test image files."""
    return test_data_loader.get_test_images()


@pytest.fixture
def test_pdf_files():
    """Provide test PDF files."""
    return test_data_loader.get_test_pdfs()


@pytest.fixture
def comprehensive_test_data():
    """Provide comprehensive test data combining all sources."""
    return {
        "passports": {
            "regular": test_data_loader.get_passport_by_type("P")[:5],
            "iceland": test_data_loader.get_passport_by_type("IS")[:5],
            "special": test_data_loader.get_passport_by_type("PM")[:5],
            "invalid": test_data_loader.load_invalid_passport_data(),
        },
        "certificates": test_data_loader.load_csca_lifecycle_data(),
        "trust_store": test_data_loader.load_trust_store_data(),
        "images": test_data_loader.get_passport_images(),
        "pdfs": test_data_loader.get_test_pdfs(),
    }


# Enhanced Mock Classes with Real Data
class EnhancedMockPassportEngineStub:
    """Enhanced mock passport engine stub using real data."""

    def __init__(self):
        self.passport_data = test_data_loader.get_sample_passports(5)

    def ProcessPassport(self, request):
        """Mock ProcessPassport method with real passport data."""

        mock_response = Mock()
        mock_response.status = "SUCCESS"

        # Use real passport data
        if self.passport_data:
            mock_response.passport_data = self.passport_data[0]
        else:
            mock_response.passport_data = TestDataFixtures.SAMPLE_PASSPORT_DATA

        return mock_response


class EnhancedMockCscaServiceStub:
    """Enhanced mock CSCA service stub using real lifecycle data."""

    def __init__(self):
        try:
            self.lifecycle_data = test_data_loader.load_csca_lifecycle_data()
        except FileNotFoundError:
            self.lifecycle_data = {}

    def CreateCertificate(self, request):
        """Mock CreateCertificate method."""

        mock_response = Mock()
        mock_response.status = "SUCCESS"
        mock_response.certificate_id = (
            f"cert_real_{len(self.lifecycle_data.get('certificate_events', {}))}"
        )
        return mock_response

    def CheckExpiringCertificates(self, request):
        """Mock CheckExpiringCertificates method with real lifecycle data."""

        mock_response = Mock()

        # Use real certificate events if available
        if self.lifecycle_data and "certificate_events" in self.lifecycle_data:
            mock_response.certificates = list(self.lifecycle_data["certificate_events"].keys())[:5]
        else:
            mock_response.certificates = []

        return mock_response


@pytest.fixture
def enhanced_passport_engine_stub():
    """Provide enhanced mock passport engine stub with real data."""
    return EnhancedMockPassportEngineStub()


@pytest.fixture
def enhanced_csca_service_stub():
    """Provide enhanced mock CSCA service stub with real data."""
    return EnhancedMockCscaServiceStub()


# =============================================================================
# Email Testing Fixtures
# =============================================================================

class MockEmailHelpers:
    """
    Mock email helper for Python unit tests (CI/CD environments).
    
    Provides in-memory email storage compatible with MailHog API structure.
    """
    
    def __init__(self):
        """Initialize in-memory email storage."""
        self.emails = {}  # Dict[str, List[dict]] - recipient -> emails
    
    def get_all_emails(self):
        """Get all emails from mock storage."""
        all_emails = []
        for emails in self.emails.values():
            all_emails.extend(emails)
        return sorted(all_emails, key=lambda e: e['Created'], reverse=True)
    
    def get_emails_to(self, email: str):
        """Get emails sent to a specific address."""
        return self.emails.get(email, [])
    
    def wait_for_email(self, email: str, subject_contains: str = None, timeout: int = 30):
        """
        Mock wait for email (returns immediately if email exists).
        
        In mock mode, this doesn't actually wait, it just checks if the email exists.
        For realistic testing, emails must be pre-populated via mock_send_email.
        """
        emails = self.get_emails_to(email)
        for msg in emails:
            subject = msg['Content']['Headers']['Subject'][0]
            if not subject_contains or subject_contains in subject:
                return msg
        return None
    
    def extract_link(self, email: dict, pattern: str = r'https?://[^\s"<>]+'):
        """Extract link from email body."""
        import re
        body = email['Content'].get('Body', '')
        matches = re.findall(pattern, body)
        return matches[0] if matches else None
    
    def clear_all_emails(self):
        """Clear all emails from mock storage."""
        self.emails.clear()
    
    def mock_send_email(self, to: str, subject: str, body: str, from_email: str = 'noreply@marty.demo'):
        """
        Mock sending an email (for testing email sending functionality).
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (HTML or plain text)
            from_email: Sender email address
        
        Returns:
            dict: Mock email object in MailHog format
        """
        import datetime
        import random
        import string
        
        email_id = f"mock-{''.join(random.choices(string.ascii_lowercase + string.digits, k=12))}"
        email = {
            'ID': email_id,
            'Created': datetime.datetime.utcnow().isoformat() + 'Z',
            'Raw': {
                'From': from_email,
                'To': [to],
                'Data': f"From: {from_email}\r\nTo: {to}\r\nSubject: {subject}\r\n\r\n{body}"
            },
            'Content': {
                'Headers': {
                    'Subject': [subject],
                    'From': [from_email],
                    'To': [to],
                    'Date': [datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')],
                    'Content-Type': ['text/html; charset=UTF-8']
                },
                'Body': body,
                'Size': len(body),
                'MIME': None
            }
        }
        
        if to not in self.emails:
            self.emails[to] = []
        self.emails[to].append(email)
        return email


class MailHogHelpers:
    """
    MailHog API helper for Python integration tests.
    
    Provides direct access to MailHog HTTP API for email testing.
    """
    
    def __init__(self, mailhog_url: str = None):
        """Initialize MailHog helper."""
        self.mailhog_url = mailhog_url or os.getenv('MAILHOG_URL', 'http://localhost:8025')
    
    def get_all_emails(self):
        """Get all emails from MailHog."""
        import requests
        response = requests.get(f'{self.mailhog_url}/api/v2/messages')
        response.raise_for_status()
        data = response.json()
        return data.get('items', [])
    
    def get_emails_to(self, email: str):
        """Get emails sent to a specific address."""
        all_emails = self.get_all_emails()
        return [
            msg for msg in all_emails
            if any(email in to for to in msg.get('Raw', {}).get('To', []))
            or any(email in to for to in msg.get('Content', {}).get('Headers', {}).get('To', []))
        ]
    
    def wait_for_email(self, email: str, subject_contains: str = None, timeout: int = 30):
        """Wait for an email to arrive."""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            emails = self.get_emails_to(email)
            for msg in emails:
                subject = msg.get('Content', {}).get('Headers', {}).get('Subject', [''])[0]
                if not subject_contains or subject_contains in subject:
                    return msg
            time.sleep(1)
        
        raise TimeoutError(f"Timeout waiting for email to {email}")
    
    def extract_link(self, email: dict, pattern: str = r'https?://[^\s"<>]+'):
        """Extract link from email body."""
        import re
        body = email.get('Content', {}).get('Body', '')
        matches = re.findall(pattern, body)
        return matches[0] if matches else None
    
    def clear_all_emails(self):
        """Clear all emails from MailHog."""
        import requests
        response = requests.delete(f'{self.mailhog_url}/api/v1/messages')
        response.raise_for_status()


@pytest.fixture
def email_helper(request):
    """
    Environment-aware email testing helper.
    
    Returns MailHogHelpers for integration tests, MockEmailHelpers for unit tests.
    Checks TEST_PROVIDER environment variable and test markers.
    """
    test_provider = os.getenv('TEST_PROVIDER', 'mailhog')
    
    # Check if test is marked as integration
    is_integration = request.node.get_closest_marker('integration') is not None
    
    if test_provider == 'mock' or not is_integration:
        return MockEmailHelpers()
    else:
        return MailHogHelpers()


@pytest.fixture
def mailhog_client():
    """
    Direct MailHog client for integration tests.
    
    Use this fixture when you explicitly need MailHog (not the mock).
    Session-scoped for efficiency.
    """
    return MailHogHelpers()


@pytest.fixture(scope='session')
def mock_email_helper():
    """
    Session-scoped mock email helper for shared state across tests.
    
    Use this for test scenarios that need to share email state.
    """
    return MockEmailHelpers()


# Test helper functions
def create_test_image(width: int = 100, height: int = 100):
    """Create a test image for OCR/MRZ testing."""
    try:
        import numpy as np

        return np.ones((height, width), dtype=np.uint8) * 255
    except ImportError:
        pytest.skip("numpy not available for image creation")


def create_test_pdf_bytes():
    """Create test PDF bytes for PDF extraction testing."""
    # Minimal PDF structure
    return b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 4
0000000000 65535 f
0000000010 00000 n
0000000062 00000 n
0000000119 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
197
%%EOF"""
