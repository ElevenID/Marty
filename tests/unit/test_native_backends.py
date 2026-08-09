"""Tests for fail-closed native backend loading."""

import pytest

from marty_plugin.native_backends import (
    NativeBackendUnavailable,
    backend_diagnostics,
    require_backend,
)


def test_missing_native_backend_raises_typed_error() -> None:
    with pytest.raises(NativeBackendUnavailable, match="Required native backend"):
        require_backend("marty_backend_that_does_not_exist")


def test_backend_diagnostics_reports_unavailable_backends() -> None:
    diagnostics = backend_diagnostics()

    assert set(diagnostics) == {"marty_iso18013", "marty_verification", "_marty_rs"}
    assert all("available" in value for value in diagnostics.values())
