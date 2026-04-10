"""
Open Badges test configuration.

Stubs ``marty_plugin.common.*`` (same approach as tests/subscription/conftest.py).
"""

import importlib.abc
import importlib.machinery
import sys
import types
from unittest.mock import MagicMock


class _StubModule(types.ModuleType):
    """Module stub that returns MagicMock for any missing attribute."""

    # Names that must be real classes (used as base classes or exceptions)
    _CLASS_NAMES = {"SODParsingError", "ServiceConfig"}

    def __getattr__(self, name):
        if name in self._CLASS_NAMES:
            cls = type(name, (), {})
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


if not any(isinstance(f, _MartyPluginCommonFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _MartyPluginCommonFinder())

# Pre-populate known sub-modules so Python never looks on disk
_STUBS = [
    "marty_plugin.common",
    "marty_plugin.common.infrastructure",
    "marty_plugin.common.infrastructure.trust_models",
    "marty_plugin.common.crypto",
    "marty_plugin.common.crypto.sod_parser",
    "marty_plugin.common.crypto.certificate_validator",
    "marty_plugin.common.crypto.vds_nc_keys",
    "marty_plugin.common.crypto_bridge",
    "marty_plugin.common.crypto_role",
    "marty_plugin.common.config_manager",
    "marty_plugin.common.models",
    "marty_plugin.common.models.asn1_structures",
    "marty_plugin.common.security",
    "marty_plugin.common.security.encryption",
]
for _name in _STUBS:
    if _name not in sys.modules:
        sys.modules[_name] = _make_stub(_name)

if "marty_plugin" in sys.modules:
    sys.modules["marty_plugin"].common = sys.modules["marty_plugin.common"]
