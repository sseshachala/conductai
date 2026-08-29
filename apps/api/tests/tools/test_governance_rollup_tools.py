"""Registration + dispatch parity for the three governance rollup tools
(#1295 + #1420). First tools registered under the free-function convention
(no Executor._tool_* shim). Verifies the ToolDef reaches the registry,
dispatch goes through the LensAdapter, and the return shape matches what
Lens chat expects.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.mcp.lens_adapter import dispatch as lens_dispatch
from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # side-effect: populate registry
from app.tools.registry import default_registry


_CTX = MCPContext(workspace_id="00000000-0000-0000-0000-000000000000", surface="lens")

_ALLOW = PolicyDecision(action=PolicyAction.ALLOW, source="rule")


def test_governance_tools_registered():
    """All three tools appear in default_registry with the lens tag."""
    for name in ("get_governance_summary", "get_soc2_status", "get_ai_rollout_status"):
        tool = default_registry.get(name)
        assert tool is not None, f"{name} not registered"
        assert "lens" in tool.tags
        assert tool.annotations.read_only, f"{name} should be read_only"


def test_get_governance_summary_dispatch():
    """get_governance_summary calls _compute_framework_coverage and
    serialises the result."""
    from app.routers.governance import FrameworksOut
    fake_result = FrameworksOut(installed=[], bonus=[], total_rules=0, rules_with_framework=0)

    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         patch("app.tools.registrations.lens._run_framework_coverage",
               return_value=fake_result) as mock_helper:
        result = lens_dispatch("get_governance_summary", "{}", _CTX)

    mock_helper.assert_called_once_with(_CTX.workspace_id)
    payload = json.loads(result)
    assert payload["installed"] == []
    assert payload["bonus"] == []
    assert payload["total_rules"] == 0


def test_get_soc2_status_installed_row():
    """When SOC2 is in the installed list, status='installed' + row fields."""
    from app.routers.governance import FrameworkRow, FrameworksOut
    fake = FrameworksOut(
        installed=[FrameworkRow(
            framework="SOC2", rules_count=42, controls=["CC6.1", "CC8.1"], packs=["conduct-soc2"],
        )],
        bonus=[], total_rules=42, rules_with_framework=42,
    )
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         patch("app.tools.registrations.lens._run_framework_coverage", return_value=fake):
        result = lens_dispatch("get_soc2_status", "{}", _CTX)
    payload = json.loads(result)
    assert payload["status"] == "installed"
    assert payload["framework"] == "SOC2"
    assert payload["rules_count"] == 42
    assert payload["controls"] == ["CC6.1", "CC8.1"]


def test_get_soc2_status_not_covered_returns_recommended_pack():
    """Framework not present in installed or bonus → status='not_covered'
    with the recommended pack surfaced."""
    from app.routers.governance import FrameworksOut
    empty = FrameworksOut(installed=[], bonus=[], total_rules=0, rules_with_framework=0)
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         patch("app.tools.registrations.lens._run_framework_coverage", return_value=empty):
        result = lens_dispatch("get_soc2_status", '{"framework": "HIPAA"}', _CTX)
    payload = json.loads(result)
    assert payload["status"] == "not_covered"
    assert payload["framework"] == "HIPAA"
    assert payload["recommended_pack"] == "conduct-hipaa"


def test_get_ai_rollout_status_unpublished():
    """No WorkspaceInstructions row → published=False, zero content."""

    class _Q:
        def filter(self, *_a, **_k): return self
        def first(self): return None

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_ai_rollout_status
        out = get_ai_rollout_status(_CTX)

    assert out["published"] is False
    assert out["content_length"] == 0
    assert out["version"] is None
    assert out["updated_at"] is None
    assert out["updated_by"] is None


def test_get_ai_rollout_status_published():
    """WorkspaceInstructions row exists → published=True with metadata."""
    from datetime import datetime, timezone

    class _Row:
        content = "Use only approved models. Do not paste secrets."
        version = "v3"
        updated_at = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
        updated_by = "admin@example.com"

    class _Q:
        def filter(self, *_a, **_k): return self
        def first(self): return _Row()

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_ai_rollout_status
        out = get_ai_rollout_status(_CTX)

    assert out["published"] is True
    assert out["content_length"] == len(_Row.content)
    assert out["version"] == "v3"
    assert out["updated_at"] == "2026-08-15T12:00:00+00:00"
    assert out["updated_by"] == "admin@example.com"
