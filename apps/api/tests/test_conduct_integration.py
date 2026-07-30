"""Guard behavior of the conduct integration stub — the three action shapes
that security_loop uses. Real DB writes are exercised by the E2E workflow;
this suite only covers the input-validation branches so a regression can't
silently reintroduce the no-op behavior filed as #1012."""
from __future__ import annotations

from app.runtime.integrations import conduct


def test_missing_context_skips():
    r = conduct.execute("update_finding", {}, {}, db=None, workspace_id="")
    assert r["skipped"] is True
    assert "missing db" in r["reason"]


def test_unknown_action_skips():
    r = conduct.execute("bogus", {}, {}, db=object(), workspace_id="ws")
    assert r["skipped"] is True
    assert "not implemented" in r["reason"]


def test_update_finding_requires_finding_id():
    r = conduct.execute("update_finding", {}, {}, db=object(), workspace_id="ws")
    assert r["skipped"] is True
    assert "finding_id required" in r["reason"]


def test_update_finding_rejects_invalid_status():
    r = conduct.execute("update_finding", {"finding_id": "x", "status": "bogus"}, {}, db=object(), workspace_id="ws")
    assert r["skipped"] is True
    assert "invalid status" in r["reason"]


def test_trigger_fix_requires_finding_id():
    r = conduct.execute("trigger_fix", {}, {}, db=object(), workspace_id="ws")
    assert r["skipped"] is True
    assert "finding_id required" in r["reason"]


def test_tool_map_advertises_both_actions():
    assert "update_finding" in conduct.TOOL_MAP
    assert "trigger_fix" in conduct.TOOL_MAP
