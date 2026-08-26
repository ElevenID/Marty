"""Prevent parity-gated Python MMF compatibility packages from returning."""

import ast

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RETIRED_PATHS = (
    ROOT
    / "packages"
    / "marty-common"
    / "marty_common"
    / "crypto"
    / "credential_kms.py",
    ROOT / "src" / "notifications",
    ROOT / "src" / "marty_plugin" / "csca_service",
)

RETIRED_DELIVERY_PATHS = (
    ROOT / "src" / "main.py",
    ROOT / "src" / "document_signer",
    ROOT / "src" / "marty_plugin" / "passport_engine",
    ROOT / "src" / "marty_plugin" / "inspection_system",
)

HISTORICAL_GUIDES = (
    ROOT / "docs" / "guides" / "CERTIFICATE_MANAGEMENT_MIGRATION_PLAN.md",
    ROOT / "docs" / "guides" / "CONFIGURATION_CONSOLIDATION_GUIDE.md",
    ROOT / "docs" / "guides" / "NATIVE_DEVELOPMENT.md",
    ROOT / "docs" / "DATABASE_PER_SERVICE.md",
    ROOT / "docs" / "DEVELOPER_GUIDE.md",
    ROOT / "docs" / "OBSERVABILITY_IMPLEMENTATION.md",
    ROOT / "docs" / "PROMETHEUS_MONITORING.md",
    ROOT / "docs" / "RESILIENCE.md",
    ROOT / "docs" / "production_readiness_plan.md",
)


def test_parity_gated_python_mmf_sources_are_absent() -> None:
    violations = []
    for path in RETIRED_PATHS:
        if path.is_file() or (path.is_dir() and any(path.rglob("*.py"))):
            violations.append(path.relative_to(ROOT))

    assert not violations


def test_retired_root_mmf_plugin_delivery_surface_is_absent() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "marty-msf" not in pyproject
    assert 'entry-points."mmf.plugins"' not in pyproject

    retired_files = (
        "src/marty_plugin/plugin.py",
        "src/marty_plugin/config.py",
        "src/marty_plugin/runtime.py",
        "src/marty_plugin/services.py",
        "src/marty_plugin/trust_anchor/modern_trust_anchor.py",
        "docker/mmf-plugin.Dockerfile",
        "docker-compose.yml",
        ".github/workflows/cd.yml",
        ".github/workflows/warm-ci-caches.yml",
        "config/plugins/marty.yaml",
    )
    returned = [path for path in retired_files if (ROOT / path).exists()]
    assert not returned, f"retired root MMF delivery files returned: {returned}"

    assert not any(path.is_file() for path in (ROOT / "deploy/helm/marty").rglob("*"))
    assert not any(path.is_file() for path in (ROOT / "k8s").rglob("*"))


def test_retained_trust_api_has_no_transitive_server_import() -> None:
    api = ROOT / "src/marty_plugin/trust_svc/api.py"
    module = ast.parse(api.read_text(encoding="utf-8"), filename=str(api))
    top_level_imports = {
        alias.name
        for node in module.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert "uvicorn" not in top_level_imports


def test_compatibility_source_has_no_legacy_framework_imports() -> None:
    retired_roots = {"framework", "mmf", "marty_msf"}
    violations: list[str] = []

    for source_root in (ROOT / "src", ROOT / "scripts"):
        for path in source_root.rglob("*.py"):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    imports = (alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports = (node.module.split(".", 1)[0],)
                else:
                    continue
                for imported in imports:
                    if imported in retired_roots:
                        relative = path.relative_to(ROOT).as_posix()
                        violations.append(f"{relative}:{node.lineno}:{imported}")

    assert not violations, f"retired Python framework imports returned: {violations}"


def test_consumer_zero_framework_adapters_remain_absent() -> None:
    retired = (
        "packages/marty-common/marty_common/config_migration.py",
        "scripts/validate_observability_migration.py",
        "src/marty_plugin/trust_svc/config_unified.py",
        "src/marty_plugin/trust_anchor/modern_grpc_service.py",
        "src/marty_plugin/trust_anchor/observable_grpc_service.py",
    )

    returned = [path for path in retired if (ROOT / path).exists()]
    assert not returned, f"consumer-zero framework adapters returned: {returned}"


def test_retained_python_mmf_guides_are_explicitly_historical() -> None:
    for guide in HISTORICAL_GUIDES:
        introduction = " ".join(
            line.lstrip("> ")
            for line in guide.read_text(encoding="utf-8").splitlines()[:16]
        )
        assert "Historical record" in introduction, guide
        assert "not a supported" in introduction or "not a current" in introduction, (
            guide
        )
        assert "Do not" in introduction, guide


def test_retired_framework_is_not_a_build_context() -> None:
    for ignore_file in (ROOT / ".dockerignore", ROOT / ".gitignore"):
        assert "marty-microservices-framework/" not in ignore_file.read_text(
            encoding="utf-8"
        )


def test_retired_python_service_launchers_are_not_executable_surfaces() -> None:
    retired_tokens = ("src.apps", "src/apps", "apps.runtime", "src.main")
    violations: list[str] = []

    for source_root in (ROOT / "src", ROOT / "scripts"):
        for path in source_root.rglob("*"):
            if not path.is_file() or (
                path.suffix not in {".py", ".sh"} and path.name != "Dockerfile"
            ):
                continue
            content = path.read_text(encoding="utf-8")
            for token in retired_tokens:
                if token in content:
                    violations.append(f"{path.relative_to(ROOT).as_posix()}:{token}")

    assert not violations, f"retired Python launch surfaces returned: {violations}"


def test_dead_python_delivery_paths_remain_absent() -> None:
    returned = [
        path.relative_to(ROOT)
        for path in RETIRED_DELIVERY_PATHS
        if path.is_file()
        or (path.is_dir() and any(candidate.is_file() for candidate in path.rglob("*")))
    ]

    assert not returned, f"dead Python delivery paths returned: {returned}"


def test_deployment_boundary_names_only_current_release_owners() -> None:
    deployment = (ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")

    assert "does not provide a deployable Python microservice stack" in deployment
    assert "marty-ui" in deployment
    assert "marty-microservices-framework" in deployment
    assert "src.apps" not in deployment
    assert "src/main.py" not in deployment


def test_architecture_classifies_legacy_names_without_advertising_servers() -> None:
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    normalized = " ".join(architecture.split())

    assert "this repository is not a deployable Python" in normalized
    assert "A name in this repository does not imply" in normalized
    assert "CSCA parity record" in architecture
    assert "Removal gate for retained compatibility code" in architecture
    assert "marty-ui` `signing-keys" in architecture
    assert "marty-microservices-framework" in architecture
    assert "config/production.yaml" in architecture

    for dead_link in (
        "../src/csca_service/",
        "../src/document_signer/",
        "../src/inspection_system/",
        "../src/passport_engine/",
    ):
        assert dead_link not in architecture


def test_legacy_yaml_names_are_classified_as_compatibility_configuration() -> None:
    for relative in (
        "config/base.yaml",
        "config/development.yaml",
        "config/testing.yaml",
        "config/production.yaml",
        "config/policy.yaml",
        "config/annex9_data_retention.yaml",
    ):
        introduction = " ".join(
            (ROOT / relative).read_text(encoding="utf-8").splitlines()[:4]
        )
        assert "Compatibility configuration" in introduction, relative
        assert "not a Rust service registry or deployment manifest" in introduction, (
            relative
        )


def test_compatibility_yaml_is_valid_and_has_no_silent_duplicate_keys() -> None:
    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_unique_mapping(
        loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
    ) -> dict:
        loader.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            assert key not in mapping, f"duplicate YAML key: {key!r}"
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_unique_mapping,
    )

    loaded = {}
    for relative in (
        "config/base.yaml",
        "config/development.yaml",
        "config/testing.yaml",
        "config/production.yaml",
        "config/policy.yaml",
        "config/annex9_data_retention.yaml",
    ):
        try:
            loaded[relative] = yaml.load(
                (ROOT / relative).read_text(encoding="utf-8"),
                Loader=UniqueKeyLoader,
            )
        except (AssertionError, yaml.YAMLError) as exc:
            raise AssertionError(f"invalid compatibility YAML in {relative}: {exc}") from exc

    production = loaded["config/production.yaml"]
    assert production["services"]["document_signer"]["sd_jwt"][
        "credential_ttl_seconds"
    ] == 604800
    assert production["services"]["passport_engine"]["signing_algorithm"] == (
        "rsa2048"
    )
    assert production["services"]["dtc_engine"]["signing_algorithm"] == "ecdsa-p256"
    assert production["database"]["pool_size"] == 20
    assert "document_signer" in production["database"]
    assert production["security"]["grpc_tls"]["mtls"] is True
    assert production["security"]["auth"]["required"] is True
    assert production["security"]["authz"]["default_action"] == "deny"

    development = loaded["config/development.yaml"]
    assert development["security"]["grpc_tls"]["mtls"] is True
    assert development["security"]["auth"]["required"] is True
    assert development["security"]["authz"]["default_action"] == "deny"

    testing = loaded["config/testing.yaml"]
    assert testing["security"]["grpc_tls"]["mtls"] is True
    assert testing["security"]["auth"]["required"] is True
    assert testing["security"]["authz"]["default_action"] == "deny"
    assert testing["services"]["postgres"]["health_check_retries"] == 10
    assert "document-signer" in testing["services"]
    assert "document-signer" in testing["test_modes"]["integration"][
        "services_required"
    ]
