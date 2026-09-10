"""#1752 — _project_rule must not drop match_ai_tool.

Regression test for the projection bug called out in reviewer edit 5 of
#1740. The server evaluates match_ai_tool correctly; the bug is only in
what the MCP surface projects back to callers. Downstream UI/Lens/CLI
consumers rely on the projected shape.
"""
from __future__ import annotations

from app.modules.guard.routers.mcp import _project_rule


def test_project_rule_preserves_match_ai_tool():
    rule = {
        "id": "surface-chat-no-write",
        "match_tool": "Write",
        "match_ai_tool": ["Write", "Edit"],
        "action": "block",
        "message": "chat surface must not write files",
        "pack": "conduct-surface",
    }
    out = _project_rule(rule)
    assert out["match_ai_tool"] == ["Write", "Edit"]
    assert out["rule_id"] == "surface-chat-no-write"
    assert out["match_tool"] == "Write"
    assert out["action"] == "block"


def test_project_rule_match_ai_tool_absent_is_none():
    """When the source rule has no match_ai_tool, projection returns None
    (not KeyError). Existing callers checking `.get('match_ai_tool')` keep
    working."""
    rule = {"id": "generic", "match_tool": "bash", "action": "warn"}
    out = _project_rule(rule)
    assert out["match_ai_tool"] is None
