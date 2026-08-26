"""ToolRegistry unit tests — #1219 Phase 1."""
from __future__ import annotations

import pytest

from app.tools.registry import ToolRegistry, ToolRegistryError
from app.tools.types import ToolAnnotations, ToolDef


def _tool(name: str = "example", **over) -> ToolDef:
    base = dict(
        name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}},
        impl=lambda: {"ok": True},
    )
    base.update(over)
    return ToolDef(**base)


# ─── Registration ────────────────────────────────────────────────────────────

def test_register_returns_the_tool():
    reg = ToolRegistry()
    t = _tool("x")
    result = reg.register(t)
    assert result is t
    assert reg.count() == 1


def test_register_duplicate_raises():
    reg = ToolRegistry()
    reg.register(_tool("dup"))
    with pytest.raises(ToolRegistryError, match="already registered"):
        reg.register(_tool("dup"))


def test_register_same_instance_is_idempotent():
    reg = ToolRegistry()
    t = _tool("same")
    reg.register(t)
    result = reg.register(t)  # same object — allowed
    assert result is t
    assert reg.count() == 1


def test_register_with_replace_overwrites():
    reg = ToolRegistry()
    reg.register(_tool("dup", description="first"))
    reg.register(_tool("dup", description="second"), replace=True)
    assert reg.get("dup").description == "second"
    assert reg.count() == 1


def test_register_all_bulk():
    reg = ToolRegistry()
    reg.register_all([_tool("a"), _tool("b"), _tool("c")])
    assert reg.count() == 3
    assert reg.names() == ["a", "b", "c"]  # order preserved


# ─── Lookup ──────────────────────────────────────────────────────────────────

def test_get_returns_none_for_missing():
    reg = ToolRegistry()
    assert reg.get("missing") is None


def test_require_raises_for_missing():
    reg = ToolRegistry()
    with pytest.raises(ToolRegistryError, match="Unknown tool"):
        reg.require("missing")


def test_require_returns_registered():
    reg = ToolRegistry()
    t = _tool("found")
    reg.register(t)
    assert reg.require("found") is t


def test_unregister_returns_true_when_removed():
    reg = ToolRegistry()
    reg.register(_tool("gone"))
    assert reg.unregister("gone") is True
    assert reg.count() == 0


def test_unregister_returns_false_for_missing():
    reg = ToolRegistry()
    assert reg.unregister("missing") is False


# ─── Listing ─────────────────────────────────────────────────────────────────

def test_list_preserves_registration_order():
    reg = ToolRegistry()
    reg.register(_tool("first"))
    reg.register(_tool("second"))
    reg.register(_tool("third"))
    names = [t.name for t in reg.list()]
    assert names == ["first", "second", "third"]


def test_list_filters_by_tag():
    reg = ToolRegistry()
    reg.register(_tool("g1", tags=("guard",)))
    reg.register(_tool("l1", tags=("lens",)))
    reg.register(_tool("both", tags=("guard", "lens")))
    guard_names = [t.name for t in reg.list(tag="guard")]
    assert guard_names == ["g1", "both"]


# ─── MCP projection ──────────────────────────────────────────────────────────

def test_as_mcp_tools_list_shape():
    reg = ToolRegistry()
    reg.register(_tool(
        "sample",
        description="A sample tool.",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        annotations=ToolAnnotations(read_only=True, idempotent=True),
    ))
    result = reg.as_mcp_tools_list()
    assert len(result) == 1
    entry = result[0]
    assert entry["name"] == "sample"
    assert entry["description"] == "A sample tool."
    assert entry["inputSchema"] == {"type": "object", "properties": {"q": {"type": "string"}}}
    assert entry["annotations"] == {
        "readOnly": True,
        "idempotent": True,
        "destructive": False,
        "openWorld": False,
    }


def test_as_mcp_tools_list_default_annotations():
    """Tools registered without explicit annotations get the safe default
    (all False — treat as unknown)."""
    reg = ToolRegistry()
    reg.register(_tool("noannot"))
    entry = reg.as_mcp_tools_list()[0]
    assert entry["annotations"] == {
        "readOnly": False,
        "idempotent": False,
        "destructive": False,
        "openWorld": False,
    }


def test_as_mcp_tools_list_order_matches_registration():
    reg = ToolRegistry()
    reg.register(_tool("z"))
    reg.register(_tool("a"))
    reg.register(_tool("m"))
    names = [e["name"] for e in reg.as_mcp_tools_list()]
    assert names == ["z", "a", "m"]
