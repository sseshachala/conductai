"""Registration + behavior for `list_capabilities` — Lens's self-introspection
tool. Answers "what can you do?" by reading the live default_registry.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # populate registry
from app.tools.registrations.lens.capabilities import list_capabilities
from app.tools.registry import default_registry


_CTX = MCPContext(workspace_id="00000000-0000-0000-0000-000000000000", surface="lens")


def test_list_capabilities_registered() -> None:
    tool = default_registry.get("list_capabilities")
    assert tool is not None
    assert "lens" in tool.tags
    assert tool.annotations.read_only is True


def test_returns_all_lens_tools_without_filter() -> None:
    out = list_capabilities(_CTX)
    assert isinstance(out, dict)
    assert out["domain"] is None
    assert out["count"] == len(out["tools"])
    assert out["count"] > 20, "expected many lens tools registered"
    names = {t["name"] for t in out["tools"]}
    # `list_capabilities` reports itself — trivial invariant that catches
    # a registration regression.
    assert "list_capabilities" in names


def test_domain_filter_narrows() -> None:
    out = list_capabilities(_CTX, domain="run")
    assert out["domain"] == "run"
    assert out["count"] > 0
    for t in out["tools"]:
        hay = (t["name"] + " " + t["description"] + " " + " ".join(t["tags"])).lower()
        assert "run" in hay


def test_domain_filter_no_match_returns_empty() -> None:
    out = list_capabilities(_CTX, domain="does-not-exist-nowhere-xyz")
    assert out["count"] == 0
    assert out["tools"] == []


def test_shape_is_stable() -> None:
    out = list_capabilities(_CTX, domain="workflow")
    for t in out["tools"]:
        assert set(t.keys()) == {"name", "description", "tags", "read_only"}
        assert isinstance(t["name"], str)
        assert isinstance(t["read_only"], bool)
