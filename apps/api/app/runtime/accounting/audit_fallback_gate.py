"""Completion gate for the audit-fallback deletion (#2229).

Answers the question: *is there any workspace whose current period still
has audit-only requests that the spend UI + Redis rebuild need the
audit-fallback code to see?*

Zero across every workspace ⇒ the ``NOT EXISTS`` branches in
``AccountingReader.spend_micros_by_workspace`` and
``BudgetLedger.reconcile`` are dead code. Ops can then merge the
deletion PR.

Non-zero => notify platform operators and keep the fallback. Hook estimates
without request IDs also contribute to the existing fallback; do not hide
them to make this gate pass. Never modifies accounting data.

Semantics match the audit-fallback query itself so a zero return here
proves the fallback would contribute nothing on a live read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WorkspaceAuditOnlyCount:
    workspace_id: str
    audit_only_count: int
    positive_cost_rows: int = 0
    request_linked_rows: int = 0


def reporting_window_start(now: Optional[datetime] = None) -> datetime:
    """Cover monthly budgets, MTD, last_24h and last_7d spend readers."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Reporting time must include a timezone")
    now = now.astimezone(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return min(month_start, now - timedelta(days=7))


def count_audit_only_requests(
    db: Session,
    *,
    workspace_id: str | uuid.UUID,
    since: datetime,
) -> int:
    """Return the number of ``guard_audit_events`` rows in the period
    that have NO matching ``llm_attempt_receipts`` row.

    This is the exact predicate the audit-fallback branches use — a zero
    return proves the fallback would contribute nothing for this
    workspace / window.
    """
    sql = text(
        """
        SELECT COUNT(*) FROM guard_audit_events a
        WHERE a.workspace_id = CAST(:ws AS uuid)
          AND a.ts >= :since
          AND a.cost_usd_after IS NOT NULL AND a.tool_call IS DISTINCT FROM 'session_usage'
          AND NOT EXISTS (
            SELECT 1 FROM llm_attempt_receipts r
            WHERE r.workspace_id = a.workspace_id
              AND r.request_id = a.request_id
          )
        """
    )
    row = db.execute(sql, {"ws": str(workspace_id), "since": since}).scalar()
    return int(row or 0)


def audit_only_by_workspace(
    db: Session,
    *,
    since: datetime,
    workspace_ids: Optional[Iterable[str | uuid.UUID]] = None,
) -> list[WorkspaceAuditOnlyCount]:
    """One entry per workspace whose ``guard_audit_events`` in the
    window has any audit-only request. Empty list ⇒ every workspace is
    clean and the audit fallback is safe to delete.

    ``workspace_ids`` filters to a subset; None scans every workspace
    that has audit rows in the window (bounded by the reporting period).
    """
    where = ["a.ts >= :since", "a.cost_usd_after IS NOT NULL", "a.tool_call IS DISTINCT FROM 'session_usage'"]
    params: dict = {"since": since}
    if workspace_ids is not None:
        ids = [str(w) for w in workspace_ids]
        if not ids:
            return []
        # ANY() with a parameter list plays cleanly with psycopg2.
        params["ws_ids"] = ids
        where.append("a.workspace_id::text = ANY(:ws_ids)")

    sql = text(
        f"""
        SELECT a.workspace_id::text AS workspace_id, COUNT(*) AS n,
               COUNT(*) FILTER (WHERE a.cost_usd_after > 0) AS positive_cost_rows,
               COUNT(*) FILTER (WHERE a.request_id IS NOT NULL) AS request_linked_rows
        FROM guard_audit_events a
        WHERE {' AND '.join(where)}
          AND NOT EXISTS (
            SELECT 1 FROM llm_attempt_receipts r
            WHERE r.workspace_id = a.workspace_id
              AND r.request_id = a.request_id
          )
        GROUP BY a.workspace_id
        HAVING COUNT(*) > 0
        ORDER BY COUNT(*) DESC
        """
    )
    rows = db.execute(sql, params).all()
    return [
        WorkspaceAuditOnlyCount(
            workspace_id=row.workspace_id,
            audit_only_count=int(row.n),
            positive_cost_rows=int(row.positive_cost_rows),
            request_linked_rows=int(row.request_linked_rows),
        )
        for row in rows
    ]


def report_gate_to_slack(entries: list[WorkspaceAuditOnlyCount]) -> bool:
    """Post one alert summarizing every dirty workspace to Conduct's
    ops channel — ``CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL`` (which is
    ``#conduct-alerts`` in prod). Returns True if the post landed,
    False on missing config or Slack failure.

    Signal audience: the Conduct team. Fleet-wide "our own accounting
    code is still load-bearing somewhere". Per-workspace notifications
    would spam customer channels with our internal migration state.

    Routes through ``post_platform_alert`` — same platform-operator
    credential path as the durable-audit + fail-open + trial-spend
    alerters. The database session must already be closed before calling.
    """
    if not entries:
        return False
    top = entries[:10]  # keep the message readable
    lines = [
        f"• `{e.workspace_id}` — {e.audit_only_count} audit-only requests"
        for e in top
    ]
    more = ""
    if len(entries) > len(top):
        more = f"\n… and {len(entries) - len(top)} more workspaces"
    text = (
        ":warning: *accounting audit-fallback still load-bearing*\n"
        f"{len(entries)} workspace(s) have audit rows without matching "
        f"receipts in the current window. Tier 2 deletion (#2229) is not "
        f"safe to ship yet.\n\n"
        + "\n".join(lines)
        + more
    )
    return _post_gate_alert(text)


def _post_gate_alert(message: str) -> bool:
    try:
        from app.modules.guard.observability.platform_slack import post_platform_alert

        return post_platform_alert(surface="audit_fallback_gate", text=message)
    except Exception as exc:  # noqa: BLE001 - observability never crashes
        log.warning(
            "accounting.audit_fallback_gate.slack_notify_failed",
            error_type=type(exc).__name__,
        )
        return False


def run_startup_gate(
    session_factory,
    *,
    since: Optional[datetime] = None,
    notify: bool = True,
) -> dict:
    """Boot-time check for the Tier 2 deletion completion gate.

    Emits one platform Slack alert if any workspace has audit-only rows.
    Query failures also alert and never report a clean completion gate.
    ``notify=False`` makes an operator check database-read-only with no
    external notifications. Closes the DB session before any Slack I/O.

    Called from ``app/main.py`` startup. Never raises.
    """
    since = since if since is not None else reporting_window_start()
    result = {
        "workspaces_with_audit_only": 0,
        "total_audit_only_rows": 0,
        "positive_cost_rows": 0,
        "request_linked_rows": 0,
        "slack_alert_sent": False,
        "errors": 0,
        "ready_for_removal": False,
        "since": since.isoformat(),
    }
    db = None
    entries: list[WorkspaceAuditOnlyCount] = []
    try:
        if since.tzinfo is None or since.utcoffset() is None:
            raise ValueError("since must include a timezone")
        db = session_factory()
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text("SET LOCAL statement_timeout = '20s'"))
        entries = audit_only_by_workspace(db, since=since)
        result["workspaces_with_audit_only"] = len(entries)
        result["total_audit_only_rows"] = sum(e.audit_only_count for e in entries)
        result["positive_cost_rows"] = sum(e.positive_cost_rows for e in entries)
        result["request_linked_rows"] = sum(e.request_linked_rows for e in entries)
    except Exception as exc:  # noqa: BLE001
        log.critical(
            "accounting.audit_fallback_gate_failed",
            error_type=type(exc).__name__,
        )
        result["errors"] += 1
    finally:
        if db is not None:
            try:
                db.close()
            except Exception as exc:  # noqa: BLE001
                result["errors"] += 1
                log.critical(
                    "accounting.audit_fallback_gate_close_failed",
                    error_type=type(exc).__name__,
                )

    if result["errors"]:
        if notify:
            result["slack_alert_sent"] = _post_gate_alert(
                ":warning: *accounting audit-fallback gate failed*\n"
                "Receipt coverage could not be verified. Keep the accounting "
                "fallback (#2229) until a successful zero-count check."
            )
    elif entries:
        log.critical(
            "accounting.audit_fallback_still_load_bearing",
            workspace_count=len(entries),
            total_audit_only_rows=result["total_audit_only_rows"],
            positive_cost_rows=result["positive_cost_rows"],
            request_linked_rows=result["request_linked_rows"],
            since=result["since"],
        )
        if notify:
            result["slack_alert_sent"] = report_gate_to_slack(entries)
    else:
        result["ready_for_removal"] = True
        log.info("accounting.audit_fallback_gate_clean", since=result["since"])
    return result
