"""#1737 PRs 3+4 — guard_check `pack:` arg deprecation + shadow divergence log.

Verifies:
- Deprecation suffix appears on responses when a caller passes `pack:` (PR 3)
- Server-side warning is logged for the deprecated call (PR 3)
- Shadow log fires only when pack-scoped vs unified match diverges (PR 4)
- Shadow log routes tool_input through redact_secrets (reviewer edit 3)
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.modules.guard.mcp_impls import (
    _PACK_ARG_DEPRECATION_SUFFIX,
    GuardCtx,
    _shadow_log_pack_divergence,
    guard_check_impl,
)


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


def test_pack_arg_returns_deprecation_suffix_on_error_path():
    """`_get_rules_for_pack` returns a string when the pack isn't installed;
    the suffix must be appended so the caller sees the deprecation notice.
    Direct-patch LOG.warning — caplog is flaky across CI/local logging configs."""
    ctx = _ctx()
    logged: list[str] = []

    def _capture(msg, *args, **_kw):
        logged.append(msg % args if args else msg)

    with patch(
        "app.modules.guard.mcp_impls._get_rules_for_pack",
        return_value="ERROR — pack 'conduct-fake' is not installed",
    ), patch("app.modules.guard.mcp_impls.LOG.warning", side_effect=_capture):
        result = guard_check_impl(
            ctx,
            tool_name="bash",
            tool_input={"command": "ls"},
            pack="conduct-fake",
        )

    assert result.startswith("ERROR — pack 'conduct-fake' is not installed")
    assert result.endswith(_PACK_ARG_DEPRECATION_SUFFIX)
    assert any("pack: arg is deprecated" in m for m in logged)


def test_shadow_log_fires_on_divergent_match():
    """When pack-scoped and unified paths produce different rule matches,
    the shadow log emits a warning with redacted input. Patch LOG.warning
    directly — caplog capture is flaky across CI/local logging configs."""
    pack_rules = [{"id": "pack-rule", "action": "warn"}]
    unified_rules = [{"id": "unified-rule", "action": "block"}]
    db = MagicMock()
    ws_uuid = uuid.uuid4()

    def match_side(_tool, _input, rules):
        return {"rule_id": rules[0]["id"]} if rules else None

    # Fake-format secret matching pii._SECRET_PATTERNS `sk-<20+>` regex.
    # Built by concat so this fixture doesn't itself trip secret scanners.
    secret = "sk" + "-" + ("X" * 30)

    logged: list[str] = []

    def _capture(msg, *args, **_kw):
        logged.append(msg % args if args else msg)

    with patch("app.modules.guard.mcp_impls._get_rules", return_value=unified_rules), \
         patch("app.modules.guard.mcp_impls._match_policy", side_effect=match_side), \
         patch("app.modules.guard.mcp_impls.LOG.warning", side_effect=_capture):
        _shadow_log_pack_divergence(
            db, ws_uuid, "conduct-fake", "bash",
            {"command": "ls", "token": secret},
            pack_rules,
        )

    assert any("shadow divergence" in m for m in logged)
    assert any("pack_rule=pack-rule" in m for m in logged)
    assert any("unified_rule=unified-rule" in m for m in logged)
    assert not any(secret in m for m in logged), (
        "raw secret leaked into shadow log — redact_secrets did not run"
    )


def test_shadow_log_silent_on_matching_result():
    """When pack-scoped and unified paths agree, no divergence log."""
    rules = [{"id": "same-rule", "action": "warn"}]
    db = MagicMock()
    logged: list[str] = []

    def _capture(msg, *args, **_kw):
        logged.append(msg % args if args else msg)

    with patch("app.modules.guard.mcp_impls._get_rules", return_value=rules), \
         patch(
             "app.modules.guard.mcp_impls._match_policy",
             return_value={"rule_id": "same-rule"},
         ), patch("app.modules.guard.mcp_impls.LOG.warning", side_effect=_capture):
        _shadow_log_pack_divergence(
            db, uuid.uuid4(), "conduct-fake", "bash", {"cmd": "ls"}, rules,
        )
    assert not any("shadow divergence" in m for m in logged)


def test_no_pack_arg_no_deprecation_suffix():
    """Absent `pack:`, no suffix and no warning."""
    ctx = _ctx()
    # No rules → returns "ok"
    with patch("app.modules.guard.mcp_impls._get_rules", return_value=[]):
        # _record_event and GuardConfig lookup happen inside; keep DB permissive.
        ctx.db.query.return_value.filter.return_value.first.return_value = None
        with patch("app.modules.guard.mcp_impls._record_event"):
            result = guard_check_impl(
                ctx,
                tool_name="bash",
                tool_input={"command": "ls"},
            )
    assert result == "ok"
    assert _PACK_ARG_DEPRECATION_SUFFIX not in result
