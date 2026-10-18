"""Behavior checks for public compatibility facades and manual security scans."""

import asyncio
import importlib
import importlib.util
import json
from pathlib import Path
import pickle
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "packages/marty-common/marty_common"


@pytest.fixture
def modules():
    # Isolate optional top-level platform integrations; execute the actual target packages.
    previous = {k: v for k, v in sys.modules.items() if k == "marty_common" or k.startswith("marty_common.")}
    for key in previous:
        del sys.modules[key]
    for name, path in (("marty_common", COMMON), ("marty_common.resilience", COMMON / "resilience")):
        package = ModuleType(name)
        package.__path__ = [str(path)]
        sys.modules[name] = package
    try:
        yield lambda name: importlib.import_module("marty_common." + name)
    finally:
        for key in list(sys.modules):
            if key == "marty_common" or key.startswith("marty_common."):
                del sys.modules[key]
        sys.modules.update(previous)


@pytest.mark.parametrize("first", ["monitoring", "monitoring.service_monitor"])
def test_monitoring_import_order_preserves_existing_types(modules, first):
    modules(first)
    package = modules("monitoring")
    health = modules("monitoring.health_monitor")
    service = modules("monitoring.service_monitor")
    for name in ("Metric", "Alert", "HealthCheck", "MetricsCollector", "HealthMonitor"):
        assert getattr(package, name) is getattr(health, name)
    assert package.Metric is not service.Metric
    assert service.HealthStatus is package.HealthStatus
    assert service.AlertSeverity is package.AlertSeverity
    assert package.create_service_monitor is service.create_service_monitor
    assert package.create_metrics_interceptor is service.create_metrics_interceptor
    monitor = package.create_service_monitor("test", port=1234)
    assert monitor.service_info.port == 1234
    with package.monitor_operation(monitor.metrics_collector, "ok"):
        pass
    with pytest.raises(ValueError):
        with package.monitor_operation(monitor.metrics_collector, "bad"):
            raise ValueError("expected")
    assert monitor.metrics_collector.get_metrics("operations.ok.success.total")
    assert monitor.metrics_collector.get_metrics("operations.bad.errors.total")
    assert monitor.metrics_collector.get_metrics("operations.bad.duration")


def test_retry_types_pickle_and_separate_metric_histories(modules):
    basic = modules("resilience.retry")
    enhanced = modules("resilience.retry_enhanced")
    assert basic.RetryConfig is enhanced.RetryConfig
    assert basic.RetryMetrics is enhanced.RetryMetrics
    config = enhanced.RetryConfig(max_attempts=7)
    assert pickle.loads(pickle.dumps(config)) == config
    legacy_config = enhanced.RetryConfig(max_attempts=7, retry_on_exceptions=(ValueError,))
    old_pickle = pickle.dumps(legacy_config, protocol=0).replace(
        b"marty_common.resilience.retry\n", b"marty_common.resilience.retry_enhanced\n"
    )
    assert pickle.loads(old_pickle) == legacy_config
    basic.get_retry_metrics("same").record_success()
    assert enhanced.get_retry_metrics("same").successful_calls == 0
    assert basic.get_retry_metrics("same").successful_calls == 1


@pytest.mark.parametrize("facade", ["retry", "retry_enhanced"])
def test_policy_retries_sync_and_async_without_losing_stop_limits(modules, facade):
    module = modules("resilience." + facade)
    factory = getattr(module, "create_retry_policy" + ("_enhanced" if facade.endswith("enhanced") else ""))
    config = module.RetryConfig(max_attempts=3, base_delay=0, max_delay=0, jitter=False)
    calls = []

    @factory(config)
    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("transient")
        return "ok"

    assert operation() == "ok"
    assert len(calls) == 3
    calls.clear()

    @factory(config)
    async def async_operation():
        calls.append(1)
        raise ConnectionError("exhausted")

    with pytest.raises(ConnectionError, match="exhausted"):
        asyncio.run(async_operation())
    assert len(calls) == 3
    calls.clear()
    config.max_total_delay = 1e-9

    @factory(config)
    def expired():
        calls.append(1)
        raise ConnectionError("deadline")

    with pytest.raises(ConnectionError, match="deadline"):
        expired()
    assert len(calls) == 1


def test_default_exception_selection_and_decorator_metrics_stay_compatible(modules):
    module = modules("resilience.retry")
    calls = []
    config = module.RetryConfig(max_attempts=3, base_delay=0, max_delay=0, jitter=False)

    @module.create_retry_policy(config)
    def unselected():
        calls.append(1)
        raise OSError("not in the configured exception tuple")

    assert module.is_retryable_exception(OSError())
    with pytest.raises(OSError):
        unselected()
    assert len(calls) == 1
    calls.clear()

    @module.retry_sync(max_attempts=2, base=0, max_wait=0)
    def decorated():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("retry")
        return 4

    assert decorated() == 4
    stats = module.get_retry_metrics("decorated").get_stats()
    assert (stats["total_attempts"], stats["total_retries"], stats["successful_calls"]) == (2, 1, 1)


def test_advanced_abort_and_circuit_features_remain_distinct(modules):
    advanced = modules("resilience.advanced_retry")
    config = advanced.AdvancedRetryConfig(enable_circuit_breaker=False, base_delay=0, max_delay=0)
    manager = advanced.AdvancedRetryManager("advanced", config)
    calls = []

    def abort():
        calls.append(1)
        raise ValueError("abort")

    with pytest.raises(ValueError):
        manager.retry_sync(abort)
    assert len(calls) == 1
    manager.circuit_breaker = SimpleNamespace(allow_request=lambda: False)
    with pytest.raises(RuntimeError, match="is open"):
        manager.retry_sync(abort)
    assert len(calls) == 1
    assert manager.metrics.circuit_breaker_rejections == 1


@pytest.fixture
def scanner():
    spec = importlib.util.spec_from_file_location("security_scan_under_test", ROOT / "scripts/security_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scanner_uses_hook_scope_and_records_real_result(scanner, monkeypatch, tmp_path):
    monkeypatch.setattr(scanner.shutil, "which", lambda _: "available")

    def execute(command, **kwargs):
        import yaml

        config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
        version = next(r["rev"] for r in config["repos"] if r["repo"] == "https://github.com/PyCQA/bandit")
        assert command[:5] == ["uv", "run", "--no-project", "--with", f"bandit=={version}"]
        assert "packages/marty-common/marty_common" in command
        assert "-c" in command and "pyproject.toml" in command
        Path(command[-1]).write_text(json.dumps({"errors": [], "metrics": {"_totals": {"loc": 10}}, "results": []}))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(scanner.subprocess, "run", execute)
    output = tmp_path / "scan"
    assert scanner.main(["code", "--output-dir", str(output)]) == 0
    assert json.loads((output / "summary.json").read_text())["results"][0]["status"] == "passed"


@pytest.mark.parametrize("failure", ["missing", "timeout", "malformed", "finding"])
def test_scanner_never_passes_incomplete_or_finding_runs(scanner, monkeypatch, tmp_path, failure):
    monkeypatch.setattr(scanner.shutil, "which", lambda _: None if failure == "missing" else "available")

    def execute(command, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 1)
        Path(command[-1]).write_text("invalid" if failure == "malformed" else json.dumps({
            "errors": [], "metrics": {"_totals": {"loc": 10}}, "results": [{"test_id": "B605"}],
        }))
        return SimpleNamespace(returncode=1 if failure == "finding" else 0, stdout="", stderr="")

    monkeypatch.setattr(scanner.subprocess, "run", execute)
    assert scanner.main(["code", "--output-dir", str(tmp_path / "scan")]) == (1 if failure == "finding" else 2)


def test_scanner_requires_explicit_target_and_never_reuses_stale_output(scanner, tmp_path):
    output = tmp_path / "scan"
    assert scanner.main(["containers", "--output-dir", str(output)]) == 2
    before = (output / "summary.json").read_bytes()
    with pytest.raises(SystemExit) as error:
        scanner.main(["containers", "--output-dir", str(output)])
    assert error.value.code == 2
    assert (output / "summary.json").read_bytes() == before
    assert scanner.main(["compliance", "--output-dir", str(tmp_path / "manual")]) == 2


@pytest.mark.parametrize("tool,code,data,expected", [
    ("pip-audit", 1, {"dependencies": [{"vulns": [{"id": "CVE-example"}]}]}, "findings"),
    ("pip-audit", 0, {"dependencies": [{"vulns": [], "skip_reason": "unsupported"}]}, "error"),
    ("detect-secrets", 0, {"results": {"source.py": [{"type": "Secret"}]}}, "findings"),
    ("grype", 0, {"source": {"type": "image"}, "matches": [{}]}, "findings"),
    ("syft", 0, {}, "error"),
    ("semgrep", 2, {"errors": [], "results": [], "paths": {"scanned": []}}, "error"),
])
def test_scanner_interprets_findings_and_incomplete_structured_results(scanner, tmp_path, tool, code, data, expected):
    assert scanner.classify(tool, code, json.dumps(data), tmp_path / "unused") == expected


@pytest.mark.parametrize("patterns,code,expected", [("", 0, 2), ("", 1, 2), ("prohibited-pattern\n", 0, 0)])
def test_git_secrets_requires_detection_policy(scanner, monkeypatch, tmp_path, patterns, code, expected):
    monkeypatch.setattr(scanner.shutil, "which", lambda _: "available")
    commands = []

    def execute(command, **kwargs):
        commands.append(command)
        if command[1] == "config":
            assert command == ["git", "config", "--get-all", "secrets.patterns"]
            return SimpleNamespace(returncode=code, stdout=patterns, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(scanner.subprocess, "run", execute)
    assert scanner.main(["secrets", "--tool", "git-secrets", "--output-dir", str(tmp_path / "scan")]) == expected
    assert len(commands) == (2 if expected == 0 else 1)


def test_scanner_preserves_help_alias(scanner):
    with pytest.raises(SystemExit) as error:
        scanner.main(["help"])
    assert error.value.code == 0


@pytest.mark.parametrize("image", ["example@sha256:short", "-option@sha256:" + "a" * 64])
def test_scanner_rejects_invalid_image_digest(scanner, tmp_path, image):
    assert scanner.main(["containers", "--image=" + image, "--output-dir", str(tmp_path / "scan")]) == 2
