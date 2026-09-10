"""#1737 PR 5 — guard_test verb: pack-scoped dry-run.

Verifies:
- Missing/invalid pack args return ERROR strings
- Uninstalled pack returns ERROR listing what IS installed
- Matched rule returns WOULD-<VERDICT> string
- No rule match returns 'OK — no rule fired'
- Never writes to audit chain (no _record_event call)
- _build_rules is invoked with restrict_to_pack (proves isolation, no drift)
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.modules.guard.mcp_impls import GuardCtx, guard_test_impl


def _ctx() -> GuardCtx:
    return GuardCtx(
        db=MagicMock(),
        ws_uuid=uuid.uuid4(),
        workspace_id="ws-abc",
        clerk_user_id="user_test",
        user_email="test@example.com",
        ai_tool="claude-code",
        session_id="sess-1",
        resolved_token="cond_tok_test",
    )


def test_guard_test_requires_pack():
    result = guard_test_impl(_ctx(), tool_name="bash", tool_input={"command": "ls"})
    assert result.startswith("ERROR")
    assert "'pack' argument is required" in result


def test_guard_test_rejects_conduct_base():
    result = guard_test_impl(
        _ctx(), pack="conduct-base", tool_name="bash", tool_input={"cmd": "x"}
    )
    assert result.startswith("ERROR")
    assert "conduct-base" in result


def test_guard_test_requires_tool_name():
    ctx = _ctx()
    # Pretend the pack IS installed so we get past the install check.
    ctx.db.query.return_value.filter.return_value.first.return_value = MagicMock()
    result = guard_test_impl(ctx, pack="conduct-hipaa")
    assert result.startswith("ERROR")
    assert "tool_name" in result


def test_guard_test_returns_error_when_pack_not_installed():
    ctx = _ctx()

    # First query (single pack lookup) → None; second query (list others) → [].
    filter1 = MagicMock()
    filter1.first.return_value = None
    filter2 = MagicMock()
    filter2.all.return_value = []
    ctx.db.query.return_value.filter.side_effect = [filter1, filter2]

    result = guard_test_impl(
        ctx, pack="conduct-fake", tool_name="bash", tool_input={"c": "x"}
    )
    assert result.startswith("ERROR")
    assert "not installed" in result
    assert "conduct-fake" in result


def test_guard_test_returns_would_verdict_when_rule_matches():
    ctx = _ctx()
    # Pack is installed.
    ctx.db.query.return_value.filter.return_value.first.return_value = MagicMock()

    with patch(
        "app.modules.guard.policy_engine._build_rules",
        return_value=[{"id": "hipaa-x", "action": "block", "message": "PHI leak"}],
    ) as bm, \
         patch(
             "app.modules.guard.mcp_impls._project_rule",
             side_effect=lambda r: {"rule_id": r["id"], "action": r["action"], "message": r["message"]},
         ), \
         patch(
             "app.modules.guard.mcp_impls._match_policy",
             return_value={"rule_id": "hipaa-x", "action": "block", "message": "PHI leak"},
         ), \
         patch("app.modules.guard.mcp_impls._record_event") as rec:
        result = guard_test_impl(
            ctx, pack="conduct-hipaa", tool_name="bash", tool_input={"cmd": "cat /db"},
        )

    assert result.startswith("WOULD-BLOCK")
    assert "hipaa-x" in result
    assert "PHI leak" in result
    assert "conduct-hipaa" in result
    # Prove isolation: _build_rules called with restrict_to_pack
    _, kwargs = bm.call_args
    assert kwargs.get("restrict_to_pack") == "conduct-hipaa"
    # Prove dry-run: audit chain never touched
    rec.assert_not_called()


def test_guard_test_returns_ok_when_no_rule_fires():
    ctx = _ctx()
    ctx.db.query.return_value.filter.return_value.first.return_value = MagicMock()

    with patch(
        "app.modules.guard.policy_engine._build_rules", return_value=[]
    ), patch(
        "app.modules.guard.mcp_impls._match_policy", return_value=None
    ), patch("app.modules.guard.mcp_impls._record_event") as rec:
        result = guard_test_impl(
            ctx, pack="conduct-hipaa", tool_name="bash", tool_input={"cmd": "ls"},
        )
    assert result.startswith("OK")
    assert "conduct-hipaa" in result
    rec.assert_not_called()
