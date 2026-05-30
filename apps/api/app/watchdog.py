"""
Watchdog daemon — scans for stale workers and approval timeouts, writes
WatchdogEvent records, and sends Slack alerts when configured.

Slack config is per-workspace:
  - Token:   the workspace's Slack integration (handle='slack', service='slack')
             decrypted via app.core.crypto.decrypt
  - Channel: workspace.preferences["watchdog_channel"]

Both must be present for a workspace to receive Slack alerts.
"""
import time
from datetime import datetime, timedelta, timezone

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_slack_config(db, workspace_id: str) -> tuple[str, str] | None:
    """
    Return (token, channel) for the workspace's Slack integration, or None
    if either the integration or the watchdog_channel preference is missing.
    """
    from app.core.crypto import decrypt
    from app.models.integration import Integration
    from app.models.workspace import Workspace

    row = (
        db.query(Integration)
        .filter(
            Integration.workspace_id == workspace_id,
            Integration.service == "slack",
            Integration.encrypted_credentials.isnot(None),
        )
        .first()
    )
    if not row:
        return None

    try:
        creds = decrypt(row.encrypted_credentials)
    except Exception:
        return None

    token = creds.get("token") or creds.get("bot_token") or ""
    if not token:
        return None

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    channel = (ws.preferences or {}).get("watchdog_channel", "") if ws else ""
    if not channel:
        return None

    return token, channel


def _send_slack_alert(token: str, channel: str, event_type: str, run_id: str, workflow_name: str, workspace_id: str, detail: str) -> None:
    from app.runtime.integrations.slack import post_message

    run_url = f"{settings.app_url}/workflows/{workspace_id}/runs/{run_id}"
    text = f":warning: Conduct Watchdog — {event_type.replace('_', ' ').title()}"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":warning: *Watchdog alert: {event_type.replace('_', ' ')}*\n"
                    f"*Agent:* {workflow_name}\n"
                    f"{detail}\n"
                    f"<{run_url}|View run>"
                ),
            },
        }
    ]
    try:
        post_message(token=token, channel=channel, text=text, blocks=blocks)
        log.info("watchdog.slack_sent", event_type=event_type, run_id=run_id)
    except Exception:
        log.exception("watchdog.slack_failed", event_type=event_type, run_id=run_id)


def _already_emitted(db, run_id, event_type: str, dedup_window_hours: int = 2) -> bool:
    from app.models.watchdog_event import WatchdogEvent

    cutoff = _now() - timedelta(hours=dedup_window_hours)
    return (
        db.query(WatchdogEvent)
        .filter(
            WatchdogEvent.run_id == run_id,
            WatchdogEvent.event_type == event_type,
            WatchdogEvent.created_at >= cutoff,
        )
        .first()
    ) is not None


def _has_open_approval_gate(db, run_id) -> bool:
    """
    Return True if the run has an unresolved approval gate in run_events.

    An open gate means there is an approval_requested event with no matching
    approval_received event for the same block_id.

    This check is defensive: approval runs are already in status='paused' so
    they should be caught by the approval_timeout scan instead of stale_worker.
    However, race conditions between the worker writing locked_at and updating
    status to 'paused' mean a run can briefly appear as status='running' while
    an approval gate has already been emitted. Skipping these prevents false
    stale_worker alerts.
    """
    from sqlalchemy import text

    row = db.execute(
        text(
            """
            SELECT 1
            FROM run_events re1
            WHERE re1.run_id = :rid
              AND re1.kind = 'approval_requested'
              AND NOT EXISTS (
                  SELECT 1
                  FROM run_events re2
                  WHERE re2.run_id = :rid
                    AND re2.kind = 'approval_received'
                    AND re2.block_id = re1.block_id
              )
            LIMIT 1
            """
        ),
        {"rid": str(run_id)},
    ).first()
    return row is not None


def scan(db) -> dict:
    """
    Scan the DB for stale workers and approval timeouts.
    Writes WatchdogEvent rows and sends per-workspace Slack alerts.
    Returns counts for logging.
    """
    from app.models.run import Run
    from app.models.watchdog_event import WatchdogEvent
    from app.models.workflow import Workflow, WorkflowVersion

    now = _now()
    stale_cutoff = now - timedelta(minutes=settings.watchdog_stale_minutes)
    approval_cutoff = now - timedelta(minutes=settings.watchdog_approval_timeout_minutes)

    # Cache per-workspace Slack config so we only decrypt once per scan cycle
    _slack_cache: dict[str, tuple[str, str] | None] = {}

    def slack_for(workspace_id: str) -> tuple[str, str] | None:
        if workspace_id not in _slack_cache:
            _slack_cache[workspace_id] = _get_slack_config(db, workspace_id)
        return _slack_cache[workspace_id]

    stale_flagged = 0
    approval_flagged = 0

    # ── Stale workers ──────────────────────────────────────────────────────────
    stale_runs = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"), Workflow.workspace_id.label("ws_id"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(
            Run.status == "running",
            Run.locked_at.isnot(None),
            Run.locked_at < stale_cutoff,
        )
        .all()
    )

    for run, wf_id, wf_name, ws_id in stale_runs:
        if _already_emitted(db, run.id, "stale_worker"):
            continue

        # Skip runs that have an open approval gate — they are not stale workers.
        # Approval runs should be status='paused' already, but a race between
        # locked_at being set and status being updated can briefly surface them
        # here. The approval_timeout scan will handle them correctly.
        if _has_open_approval_gate(db, run.id):
            continue

        minutes_stale = int((now - run.locked_at).total_seconds() / 60)
        db.add(WatchdogEvent(
            workspace_id=str(ws_id),
            run_id=run.id,
            workflow_id=wf_id,
            event_type="stale_worker",
            severity="warning",
            payload={"minutes_stale": minutes_stale, "locked_by": run.locked_by, "workflow_name": wf_name},
        ))
        stale_flagged += 1

        slack = slack_for(str(ws_id))
        if slack:
            _send_slack_alert(
                token=slack[0], channel=slack[1],
                event_type="stale_worker", run_id=str(run.id),
                workflow_name=wf_name, workspace_id=str(ws_id),
                detail=f"Run has been stuck for *{minutes_stale} minutes* (worker: {run.locked_by or 'unknown'}).",
            )

    # ── Approval timeouts ─────────────────────────────────────────────────────
    approval_runs = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"), Workflow.workspace_id.label("ws_id"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(
            Run.status == "paused",
            Run.paused_at.isnot(None),
            Run.paused_at < approval_cutoff,
        )
        .all()
    )

    for run, wf_id, wf_name, ws_id in approval_runs:
        if _already_emitted(db, run.id, "approval_timeout"):
            continue

        minutes_waiting = int((now - run.paused_at).total_seconds() / 60)
        db.add(WatchdogEvent(
            workspace_id=str(ws_id),
            run_id=run.id,
            workflow_id=wf_id,
            event_type="approval_timeout",
            severity="warning",
            payload={"minutes_waiting": minutes_waiting, "workflow_name": wf_name},
        ))
        approval_flagged += 1

        slack = slack_for(str(ws_id))
        if slack:
            _send_slack_alert(
                token=slack[0], channel=slack[1],
                event_type="approval_timeout", run_id=str(run.id),
                workflow_name=wf_name, workspace_id=str(ws_id),
                detail=f"Approval has been pending for *{minutes_waiting} minutes*.",
            )

    # ── Repeated failures (≥3 in 1 hour per workflow) ────────────────────────
    repeated_flagged = 0
    one_hour_ago = now - timedelta(hours=1)

    repeated_rows = db.execute(text("""
        SELECT wf.id AS wf_id, wf.name AS wf_name, wf.workspace_id AS ws_id,
               COUNT(r.id) AS fail_count
        FROM runs r
        JOIN workflow_versions wv ON wv.id = r.workflow_version_id
        JOIN workflows wf ON wf.id = wv.workflow_id
        WHERE r.status = 'failed'
          AND r.completed_at >= :cutoff
        GROUP BY wf.id, wf.name, wf.workspace_id
        HAVING COUNT(r.id) >= 3
    """), {"cutoff": one_hour_ago}).fetchall()

    for row in repeated_rows:
        ws_id = str(row.ws_id)
        wf_id = row.wf_id
        # Dedup per workflow (run_id=None signals workflow-level event)
        recent = db.query(WatchdogEvent).filter(
            WatchdogEvent.workspace_id == ws_id,
            WatchdogEvent.workflow_id == wf_id,
            WatchdogEvent.event_type == "repeated_failure",
            WatchdogEvent.created_at >= one_hour_ago,
        ).first()
        if recent:
            continue

        db.add(WatchdogEvent(
            workspace_id=ws_id,
            run_id=None,
            workflow_id=wf_id,
            event_type="repeated_failure",
            severity="warning",
            payload={"fail_count": row.fail_count, "window_minutes": 60, "workflow_name": row.wf_name},
        ))
        repeated_flagged += 1

        slack = slack_for(ws_id)
        if slack:
            _send_slack_alert(
                token=slack[0], channel=slack[1],
                event_type="repeated_failure", run_id="",
                workflow_name=row.wf_name, workspace_id=ws_id,
                detail=f"*{row.fail_count} failures in the last hour* for this agent.",
            )

    # ── Credential expiry (401s in block_failed events in last hour) ──────────
    credential_flagged = 0

    cred_rows = db.execute(text("""
        SELECT DISTINCT wf.workspace_id AS ws_id, wf.id AS wf_id, wf.name AS wf_name,
                        re.run_id, re.payload
        FROM run_events re
        JOIN runs r ON r.id = re.run_id
        JOIN workflow_versions wv ON wv.id = r.workflow_version_id
        JOIN workflows wf ON wf.id = wv.workflow_id
        WHERE re.kind = 'block_failed'
          AND re.created_at >= :cutoff
          AND (
            re.payload::text ILIKE '%401%'
            OR re.payload::text ILIKE '%unauthorized%'
            OR re.payload::text ILIKE '%Bad credentials%'
          )
    """), {"cutoff": one_hour_ago}).fetchall()

    seen_ws: set[str] = set()
    for row in cred_rows:
        ws_id = str(row.ws_id)
        if ws_id in seen_ws:
            continue
        seen_ws.add(ws_id)

        recent = db.query(WatchdogEvent).filter(
            WatchdogEvent.workspace_id == ws_id,
            WatchdogEvent.event_type == "credential_expiry",
            WatchdogEvent.created_at >= one_hour_ago,
        ).first()
        if recent:
            continue

        db.add(WatchdogEvent(
            workspace_id=ws_id,
            run_id=row.run_id,
            workflow_id=row.wf_id,
            event_type="credential_expiry",
            severity="warning",
            payload={"workflow_name": row.wf_name, "hint": "Reconnect GitHub or Slack in Settings"},
        ))
        credential_flagged += 1

        slack = slack_for(ws_id)
        if slack:
            _send_slack_alert(
                token=slack[0], channel=slack[1],
                event_type="credential_expiry", run_id=str(row.run_id),
                workflow_name=row.wf_name, workspace_id=ws_id,
                detail="A block returned *401 Unauthorized* — reconnect GitHub or Slack in Settings.",
            )

    db.commit()
    return {
        "stale_flagged": stale_flagged,
        "approval_flagged": approval_flagged,
        "repeated_flagged": repeated_flagged,
        "credential_flagged": credential_flagged,
    }


def watchdog_loop() -> None:
    log.info(
        "watchdog.started",
        stale_minutes=settings.watchdog_stale_minutes,
        approval_timeout_minutes=settings.watchdog_approval_timeout_minutes,
        interval_seconds=settings.watchdog_interval_seconds,
    )

    while True:
        time.sleep(settings.watchdog_interval_seconds)
        try:
            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                counts = scan(db)
                if counts["stale_flagged"] or counts["approval_flagged"]:
                    log.warning("watchdog.issues_detected", **counts)
                else:
                    log.debug("watchdog.cycle_clean")
            except Exception:
                log.exception("watchdog.scan_error")
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()
        except Exception:
            log.exception("watchdog.loop_error")
