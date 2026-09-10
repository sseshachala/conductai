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
    _build_divergence_log_line,
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


def test_divergence_log_line_fires_on_different_rule_ids():
    """Pure-function coverage of the divergence-message builder — no
    patching, no logger, no test-order coupling.

    Pre-existing tests (test_guard_approval*.py) stub app.core.pii module
    with a MagicMock at import time and never restore. Force-reload the
    real module before this test runs so redaction actually executes."""
    import sys, importlib
    # Pre-existing tests stubbed sys.modules["app.core.pii"] = MagicMock().
    # Drop the stub, force a fresh import of the real module.
    sys.modules.pop("app.core.pii", None)
    importlib.import_module("app.core.pii")

    # Fake-format secret matching pii._SECRET_PATTERNS `sk-<20+>` regex.
    # Built by concat so this fixture doesn't itself trip secret scanners.
    secret = "sk" + "-" + ("X" * 30)
    line = _build_divergence_log_line(
        pack="conduct-fake",
        tool_name="bash",
        tool_input={"command": "ls", "token": secret},
        pack_rid="pack-rule",
        unified_rid="unified-rule",
    )
    assert line is not None
    fmt, args = line
    assert "shadow divergence" in fmt
    rendered = fmt % args
    assert "pack_rule=pack-rule" in rendered
    assert "unified_rule=unified-rule" in rendered
    assert secret not in rendered, (
        "raw secret leaked into shadow log — redact_secrets did not run"
    )


def test_divergence_log_line_silent_on_same_rule_ids():
    """When both paths agree, builder returns None (no log)."""
    line = _build_divergence_log_line(
        pack="conduct-fake",
        tool_name="bash",
        tool_input={"cmd": "ls"},
        pack_rid="same-rule",
        unified_rid="same-rule",
    )
    assert line is None


def test_divergence_log_line_silent_when_both_paths_null():
    """No rule matched on either side → no divergence."""
    line = _build_divergence_log_line(
        pack="conduct-fake",
        tool_name="bash",
        tool_input={},
        pack_rid=None,
        unified_rid=None,
    )
    assert line is None


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
