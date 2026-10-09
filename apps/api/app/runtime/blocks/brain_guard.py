"""Guard verdict side effects for brain-block tool calls.

One place for what happens after a Guard rule matches a brain tool call
(built-in tools and MCP tools alike): a Guard audit row so the verdict
appears in the flight recorder (Guard → Activity), and a fan-out of
block/warn to the workspace's notification channels via the same
``notify_guard_block`` helper the proxy and MCP surfaces use.
"""
from __future__ import annotations

import uuid

import structlog

log = structlog.get_logger(__name__)


def decision_label(action: str) -> str:
    """Audit/notify decision for a rule action."""
    if action == "block":
        return "blocked"
    if action == "warn":
        return "warned"
    return "audited"


def record_runtime_guard_verdict(
    db,
    *,
    workspace_id: str,
    user_email: str | None,
    tool_name: str,
    action: str,
    rule_id: str | None,
    message: str,
    input_text: str,
    run_id: str | None,
    playbook_slug: str | None,
    workflow_id: str | None,
) -> None:
    """Write the Guard audit row and notify on block/warn. Never raises."""
    label = decision_label(action)
    try:
        from datetime import datetime, timezone

        from app.modules.guard.models import GuardAuditEvent

        db.add(GuardAuditEvent(
            workspace_id=uuid.UUID(workspace_id),
            user_email=user_email,
            ai_tool="conduct_runtime",
            tool_call=tool_name,
            source="runtime",
            decision=label,
            rule_id=rule_id,
            rule_message=message,
            input_summary=input_text[:500],
            conductai_run_id=str(run_id) if run_id else None,
            conductai_workflow=playbook_slug,
            conductai_workflow_id=str(workflow_id) if workflow_id else None,
            ts=datetime.now(timezone.utc),
        ))
        db.commit()
    except Exception as exc:
        log.warning("brain.guard.audit_write_failed", tool=tool_name, error=str(exc))
        db.rollback()

    # audit-only verdicts are too noisy to fan out.
    if action in ("block", "warn"):
        try:
            from app.modules.guard.routers.events import notify_guard_block

            notify_guard_block(
                db, workspace_id,
                decision=label,
                rule_id=rule_id,
                user_email=user_email,
                tool=tool_name,
                source="runtime",
            )
        except Exception as exc:
            log.warning("brain.guard.notify_failed", tool=tool_name, error=str(exc))


# ── Rule matching (moved from brain_block._execute_brain, #2400) ──────

_ACTION_PRIORITY = {"block": 0, "approval": 1, "warn": 2, "audit": 3}

# Only fire rules that ACTUALLY apply to this tool. "workflow" is a scope
# for workflow-level enforcement, not a tool alias — treating it as a
# wildcard here made every conduct-base workflow rule fire on every brain
# tool_use, blocking all read_file / write_file / search_code / run_shell.
_TOOL_ALIASES = {
    "run_shell": {"shell", "run_shell"},
    "read_file": {"filesystem-read", "read_file", "read"},
    "write_file": {"filesystem-write", "write_file", "write"},
    "edit": {"filesystem-write", "edit"},
    "search_code": {"filesystem-read", "search_code", "grep"},
}


def match_mcp_rule(rules: list[dict], server_name: str, tool_name: str,
                   input_text: str, tool_matches) -> dict | None:
    """Highest-priority rule matching an MCP call, or None.

    ``tool_matches`` is ``app.modules.guard.tool_groups.tool_matches``,
    imported lazily by the caller at the same point as before the split.
    """
    import re as _re
    _guard_hit = None
    _best_priority = 999
    for _rule in rules:
        # match_mcp_server — matches against server name prefix
        _ms = (_rule.get("match_mcp_server") or "").strip()
        if _ms and _ms != "*":
            if not _re.fullmatch(_ms, server_name, _re.IGNORECASE):
                continue
        # match_tool — matches against the MCP tool name (after the separator)
        _mt = (_rule.get("match_tool") or "").strip()
        if _mt and _mt != "*":
            _mt_allowed = [t.strip() for t in _mt.split(",")]
            if not tool_matches(tool_name, _mt):
                # Also try regex for patterns like delete_.*
                try:
                    if not any(_re.fullmatch(p, tool_name, _re.IGNORECASE) for p in _mt_allowed):
                        continue
                except _re.error:
                    continue
        # match_pattern — against serialised input
        _mp = _rule.get("match_pattern")
        if _mp:
            try:
                if not _re.search(_mp, input_text, _re.IGNORECASE):
                    continue
            except _re.error:
                continue
        _p = _ACTION_PRIORITY.get(_rule.get("action", "audit"), 3)
        if _p < _best_priority:
            _best_priority = _p
            _guard_hit = _rule
    return _guard_hit


def match_builtin_rule(rules: list[dict], tool_name: str, tool_input: dict | None,
                       input_text: str) -> dict | None:
    """Highest-priority rule matching a built-in tool call, or None."""
    import re as _re
    _best_priority = 999
    _guard_hit = None
    for _rule in rules:
        # Honour enforcement.runtime — a rule marked
        # not_supported was authored for a different
        # surface (e.g. surface-chat-no-bash targets
        # chat UIs, not workflow runtime).
        _enf = (_rule.get("enforcement") or {})
        if _enf.get("runtime") == "not_supported":
            continue

        _mt = (_rule.get("match_tool") or "").strip()
        if _mt and _mt != "*":
            _mt_allowed = {t.strip().lower() for t in _mt.split(",")}
            _tc_lower = tool_name.lower()
            _my_aliases = _TOOL_ALIASES.get(_tc_lower, {_tc_lower})
            if not (_mt_allowed & _my_aliases) and "*" not in _mt_allowed:
                continue

        _mp = _rule.get("match_pattern")
        _mpp = _rule.get("match_path_pattern")

        # Require SOME matcher — pattern, path pattern,
        # or specific (non-wildcard) tool. A rule with
        # only wildcards and no patterns would block
        # every tool_use, almost always a config error.
        if not _mp and not _mpp and (not _mt or _mt == "*"):
            continue
        if _mp:
            try:
                if not _re.search(_mp, input_text, _re.IGNORECASE):
                    continue
            except _re.error:
                continue

        # match_path_pattern applies to the tool_input's
        # path-like fields (path, file_path, filename).
        # Rules like no-path-traversal use this to catch a
        # parent-dir traversal to a system file — must be checked
        # separately from match_pattern which is content-side.
        if _mpp:
            _path_val = (tool_input or {}).get("path") \
                        or (tool_input or {}).get("file_path") \
                        or (tool_input or {}).get("filename") \
                        or ""
            if not _path_val:
                continue  # no path to check → rule doesn't apply
            try:
                if not _re.search(_mpp, str(_path_val), _re.IGNORECASE):
                    continue
            except _re.error:
                continue

        _p = _ACTION_PRIORITY.get(_rule.get("action", "audit"), 3)
        if _p < _best_priority:
            _best_priority = _p
            _guard_hit = _rule
    return _guard_hit
