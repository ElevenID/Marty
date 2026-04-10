"""
Subscription test configuration.

Pre-populates sys.modules with stubs for ``marty_plugin.common.*``
(native/Rust code absent in pure-Python unit tests).  The chain is:

  subscription.__init__ → kms_router → remote_signing_service
  → marty_backend_common.crypto → sod_parser / data_group_hasher
  → marty_plugin.common.*

Because ``marty_plugin`` is a *real* package on sys.path (src/marty_plugin/),
we combine two strategies:
  1. Pre-populate sys.modules with stubs for known sub-modules.
  2. Install a meta-path finder to catch any *additional* sub-modules
     that might be imported later (e.g. marty_plugin.common.crypto_role).
"""

import importlib.abc
import importlib.machinery
import sys
import types
from unittest.mock import MagicMock


class _StubModule(types.ModuleType):
    """Module stub that returns MagicMock for any missing attribute."""

    _CLASS_NAMES = {"SODParsingError", "ServiceConfig"}

    def __getattr__(self, name):
        if name in self._CLASS_NAMES:
            cls = type(name, (Exception if "Error" in name else object,), {})
            setattr(self, name, cls)
            return cls
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _make_stub(name: str) -> _StubModule:
    mod = _StubModule(name)
    mod.__path__ = []
    mod.__package__ = name
    return mod


class _MartyPluginCommonFinder(importlib.abc.MetaPathFinder):
    """Catch-all finder for any ``marty_plugin.common.*`` import."""

    _PREFIX = "marty_plugin.common"

    def find_module(self, fullname, path=None):
        if fullname == self._PREFIX or fullname.startswith(self._PREFIX + "."):
            return self
        return None

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        mod = _make_stub(fullname)
        sys.modules[fullname] = mod
        return mod


# Install the catch-all finder first (it runs *after* sys.modules check,
# so pre-populated stubs take priority).
if not any(isinstance(f, _MartyPluginCommonFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _MartyPluginCommonFinder())

# Pre-populate known sub-modules
_STUBS = [
    "marty_plugin.common",
    "marty_plugin.common.crypto",
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

for _name in _STUBS:
    if _name not in sys.modules:
        sys.modules[_name] = _make_stub(_name)

# Register ``common`` as an attribute on the real ``marty_plugin`` package.
if "marty_plugin" in sys.modules:
    sys.modules["marty_plugin"].common = sys.modules["marty_plugin.common"]
