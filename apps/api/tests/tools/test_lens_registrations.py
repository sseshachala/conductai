"""#1219 Phase 3b Chunk A — Lens Executor tool registrations.

Non-DB unit tests: prove each Executor `_tool_*` method has a matching
ToolDef in `app.tools.registrations.lens._TOOLS`, prove the tags and
annotations are set, prove the registry populates on import.

DB-hitting behavior is exercised by tests/regression/test_mcp_parity.py.
"""
from __future__ import annotations

import inspect

from app.tools.registrations import lens as lens_reg
from app.tools.registry import ToolRegistry, default_registry
from app.tools.types import ToolDef


def _executor_tool_methods() -> set[str]:
    from app.modules.glens.executor import Executor
    return {
        name[len("_tool_") :]
        for name, _fn in inspect.getmembers(Executor, predicate=inspect.isfunction)
        if name.startswith("_tool_")
    }


def test_every_executor_tool_has_registration():
    method_names = _executor_tool_methods()
    registered_names = {t.name for t in lens_reg._TOOLS}
    # every Executor tool must have a registration — else it's invisible to MCP
    missing = method_names - registered_names
    assert not missing, f"Executor tools without registrations: {sorted(missing)}"


def test_registrations_target_real_executor_methods():
    method_names = _executor_tool_methods()
    unknown = {t.name for t in lens_reg._TOOLS} - method_names
    assert not unknown, f"Registrations point at missing Executor methods: {sorted(unknown)}"


def test_default_registry_contains_all_lens_tools():
    assert default_registry.count() >= len(lens_reg._TOOLS)
    lens_registered = default_registry.list(tag="lens")
    assert len(lens_registered) == len(lens_reg._TOOLS)


def test_all_lens_tools_are_read_only():
    for t in lens_reg._TOOLS:
        assert t.annotations.read_only, f"{t.name} should be read_only"
        assert not t.annotations.destructive, f"{t.name} must not be destructive"


def test_open_world_tools_are_the_expected_three():
    open_world = {t.name for t in lens_reg._TOOLS if t.annotations.open_world}
    expected = {"search_memory", "search_sessions", "search_knowledge", "get_governance_narrative"}
    assert open_world == expected


def test_input_schemas_are_valid_json_schema_shape():
    for t in lens_reg._TOOLS:
        assert isinstance(t.input_schema, dict)
        assert t.input_schema.get("type") == "object"
        assert "properties" in t.input_schema
        assert "required" in t.input_schema


def test_isolated_registry_can_be_populated():
    """register() with replace=True should be safe against an isolated registry."""
    reg = ToolRegistry()
    for t in lens_reg._TOOLS:
        reg.register(t)
    assert reg.count() == len(lens_reg._TOOLS)
