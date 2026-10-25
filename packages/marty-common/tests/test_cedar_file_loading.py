"""Both public adapters retain their filesystem loading and factory behavior."""

import pytest

from marty_common.authorization import PolicyEngine
from marty_common.cedar_engine import CedarEngine


@pytest.fixture(params=[PolicyEngine, CedarEngine])
def engine_type(request):
    return request.param


def test_files_and_directories_preserve_order_and_filtering(tmp_path, engine_type):
    schema = tmp_path / "schema"
    schema.write_text("schema")
    first = tmp_path / "first.cedar"
    first.write_text("first")
    last = tmp_path / "last.cedar"
    last.write_text("last")
    directory = tmp_path / "policies"
    directory.mkdir()
    (directory / "z.cedar").write_text("z")
    (directory / "a.cedar").write_text("a")
    (directory / "ignored.txt").write_text("not a policy")
    nested = directory / "nested"
    nested.mkdir()
    (nested / "hidden.cedar").write_text("not recursive")

    engine = engine_type.from_files(
        str(schema), [first, str(directory), tmp_path / "absent", last]
    )

    assert isinstance(engine, engine_type)
    assert engine._schema == "schema"
    assert engine._policies == "first\n\na\n\nz\n\nlast"


def test_factory_preserves_subclass_and_empty_inputs(tmp_path, engine_type):
    schema = tmp_path / "schema"
    schema.write_text("")

    class CapturingEngine(engine_type):
        def __init__(self, schema, policies):
            self.received = schema, policies

    engine = CapturingEngine.from_files(schema, [tmp_path / "absent"])
    assert isinstance(engine, CapturingEngine)
    assert engine.received == ("", "")


def test_missing_schema_fails_before_policy_loading(tmp_path, engine_type):
    with pytest.raises(FileNotFoundError):
        engine_type.from_files(tmp_path / "absent", [])


def test_unreadable_policy_does_not_become_empty_success(tmp_path, engine_type):
    schema = tmp_path / "schema"
    schema.write_text("schema")
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "directory.cedar").mkdir()

    with pytest.raises(OSError):
        engine_type.from_files(schema, [policies])
