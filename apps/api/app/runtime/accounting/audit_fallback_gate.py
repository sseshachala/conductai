"""Completion gate for the audit-fallback deletion (#2229).

Answers the question: *is there any workspace whose current period still
has audit-only requests that the spend UI + Redis rebuild need the
audit-fallback code to see?*

Zero across every workspace ⇒ the ``NOT EXISTS`` branches in
``AccountingReader.spend_micros_by_workspace`` and
``BudgetLedger.reconcile`` are dead code. Ops can then merge the
deletion PR.

Non-zero ⇒ we post the workspace list to that workspace's Slack channel
so ops sees the tail. Never crashes the caller; the gate is
observational.

Semantics match the audit-fallback query itself so a zero return here
proves the fallback would contribute nothing on a live read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WorkspaceAuditOnlyCount:
    workspace_id: str
    audit_only_count: int


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
          AND a.cost_usd_after IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM llm_attempt_receipts r
            WHERE r.request_id = a.request_id
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
    where = ["a.ts >= :since", "a.cost_usd_after IS NOT NULL"]
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
        SELECT a.workspace_id::text AS workspace_id, COUNT(*) AS n
        FROM guard_audit_events a
        WHERE {' AND '.join(where)}
          AND NOT EXISTS (
            SELECT 1 FROM llm_attempt_receipts r
            WHERE r.request_id = a.request_id
          )
        GROUP BY a.workspace_id
        HAVING COUNT(*) > 0
        ORDER BY COUNT(*) DESC
        """
    )
    rows = db.execute(sql, params).all()
    return [
        WorkspaceAuditOnlyCount(workspace_id=row.workspace_id, audit_only_count=int(row.n))
        for row in rows
    ]


def report_gate_to_slack(
    db: Session,
    entries: list[WorkspaceAuditOnlyCount],
) -> int:
    """For every workspace with audit-only requests, post one alert to
    that workspace's Guard Slack channel. Returns the count of Slack
    posts fired (silently zero when no workspace has an ``alert_channel``
    configured).

    Uses the existing ``_send_guard_slack`` helper so the message flows
    through the same rate-limiting + auth path as guard block
    notifications. Failure is swallowed per-workspace.
    """
    if not entries:
        return 0
    from app.modules.guard.models import GuardConfig
    from app.modules.guard.routers.events import _send_guard_slack

    posted = 0
    for entry in entries:
        try:
            cfg = (
                db.query(GuardConfig)
                .filter(GuardConfig.workspace_id == entry.workspace_id)
                .first()
            )
            if cfg is None or not cfg.alert_channel:
                continue
            msg = (
                f":warning: accounting audit-fallback still load-bearing "
                f"— workspace `{entry.workspace_id}` has "
                f"{entry.audit_only_count} audit rows without matching "
                f"receipts in the current window. Tier 2 deletion (#2229) "
                f"is not safe to ship yet."
            )
            _send_guard_slack(db, cfg, msg)
            posted += 1
        except Exception:  # noqa: BLE001 — observability never crashes
            log.exception(
                "accounting.audit_fallback_gate.slack_notify_failed",
                workspace_id=entry.workspace_id,
            )
    return posted


def run_startup_gate(
    session_factory,
    *,
    since: Optional[datetime] = None,
) -> dict:
    """Boot-time check for the Tier 2 deletion completion gate.

    Emits one Slack alert per workspace whose ``guard_audit_events``
    still carry audit-only requests over the reporting window. Returns a
    summary dict for the caller to log.

    Called from ``app/main.py`` startup. Never raises.
    """
    since = since or datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    result = {
        "workspaces_scanned": 0,
        "workspaces_with_audit_only": 0,
        "total_audit_only_rows": 0,
        "slack_posts_fired": 0,
        "errors": 0,
    }
    db = session_factory()
    try:
        entries = audit_only_by_workspace(db, since=since)
        result["workspaces_scanned"] = 1  # scan is global; per-workspace count comes from entries
        result["workspaces_with_audit_only"] = len(entries)
        result["total_audit_only_rows"] = sum(e.audit_only_count for e in entries)
        if entries:
            log.warning(
                "accounting.audit_fallback_still_load_bearing",
                workspace_count=len(entries),
                total_audit_only_rows=result["total_audit_only_rows"],
            )
            result["slack_posts_fired"] = report_gate_to_slack(db, entries)
        else:
            log.info(
                "accounting.audit_fallback_gate_clean",
                message="No audit-only requests in current window; Tier 2 deletion is safe.",
            )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "accounting.audit_fallback_gate_failed",
            error=str(exc),
        )
        result["errors"] += 1
    finally:
        try:
            db.close()
        except Exception:
            pass
    return result
