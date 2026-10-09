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
