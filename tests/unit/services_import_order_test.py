"""Service compatibility exports stay importable without eager transport setup."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("order", ["certificate", "public", "direct"])
def test_service_import_orders_preserve_identity_without_eager_frameworks(order):
    script = """
import sys
import marty_common.services as services
assert not any(name in sys.modules for name in (
    'marty_common.services.base_grpc_service', 'marty_common.services.base_openxpki_service'
))
if ORDER == 'certificate':
    from marty_common.services.certificate_validation import CertificateValidationService
    assert 'marty_common.services.base_grpc_service' not in sys.modules
    assert 'marty_common.services.base_openxpki_service' not in sys.modules
elif ORDER == 'direct':
    from marty_common.services.base_grpc_service import BaseGrpcService
from marty_common.services import BaseService, BaseGrpcService, BaseOpenXPKIService
from marty_common.services.base_service import BaseService as DirectService
from marty_common.services.base_grpc_service import BaseGrpcService as DirectGrpc
from marty_common.services.base_openxpki_service import BaseOpenXPKIService as DirectOpenXPKI
assert BaseService is DirectService and BaseGrpcService is DirectGrpc
assert BaseOpenXPKIService is DirectOpenXPKI
assert set(services.__all__) == {'BaseService', 'BaseGrpcService', 'BaseOpenXPKIService'}
assert all(name in dir(services) for name in services.__all__)
try:
    services.unknown_service
except AttributeError:
    pass
else:
    raise AssertionError('unknown export accepted')
"""
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / "packages/marty-common"), str(ROOT / "src"))))
    result = subprocess.run(
        [sys.executable, "-c", "ORDER = " + repr(order) + "\n" + script],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
