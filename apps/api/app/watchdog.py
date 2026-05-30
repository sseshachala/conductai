"""
Watchdog daemon — scans for stale workers and approval timeouts, writes
WatchdogEvent records, and sends Slack alerts when configured.

Runs as a background daemon thread inside the worker process (alongside the
existing stale-run reaper). The reaper marks runs as failed after 20 min;
the watchdog flags them as stale at 15 min so the observability dashboard
shows issues before the reaper hard-kills them.

Slack alerting is opt-in: set WATCHDOG_SLACK_TOKEN + WATCHDOG_SLACK_CHANNEL
env vars. Both must be set for alerts to fire.
"""
import time
from datetime import datetime, timedelta, timezone

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slack_enabled() -> bool:
    return bool(settings.watchdog_slack_token and settings.watchdog_slack_channel)


def _send_slack_alert(event_type: str, run_id: str, workflow_name: str, workspace_id: str, detail: str) -> None:
    from app.runtime.integrations.slack import post_message

    run_url = f"{settings.app_url}/workflows/{workspace_id}/runs/{run_id}"
    text = f":warning: *Conduct Watchdog* — {event_type.replace('_', ' ').title()}"
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
        post_message(
            token=settings.watchdog_slack_token,
            channel=settings.watchdog_slack_channel,
            text=text,
            blocks=blocks,
        )
        log.info("watchdog.slack_sent", event_type=event_type, run_id=run_id)
    except Exception:
        log.exception("watchdog.slack_failed", event_type=event_type, run_id=run_id)


def _already_emitted(db, run_id, event_type: str, dedup_window_hours: int = 2) -> bool:
    """Return True if we already wrote this event for this run within the dedup window."""
    from app.models.watchdog_event import WatchdogEvent
    from sqlalchemy import and_

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


def scan(db) -> dict:
    """
    Scan the DB for stale workers and approval timeouts.
    Writes WatchdogEvent rows and sends Slack alerts.
    Returns counts for logging.
    """
    from app.models.run import Run
    from app.models.watchdog_event import WatchdogEvent
    from app.models.workflow import Workflow, WorkflowVersion

    now = _now()
    stale_cutoff = now - timedelta(minutes=settings.watchdog_stale_minutes)
    approval_cutoff = now - timedelta(minutes=settings.watchdog_approval_timeout_minutes)

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

        minutes_stale = int((now - run.locked_at).total_seconds() / 60)
        event = WatchdogEvent(
            workspace_id=str(ws_id),
            run_id=run.id,
            workflow_id=wf_id,
            event_type="stale_worker",
            severity="warning",
            payload={
                "minutes_stale": minutes_stale,
                "locked_by": run.locked_by,
                "workflow_name": wf_name,
            },
        )
        db.add(event)
        stale_flagged += 1

        if _slack_enabled():
            _send_slack_alert(
                event_type="stale_worker",
                run_id=str(run.id),
                workflow_name=wf_name,
                workspace_id=str(ws_id),
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
        event = WatchdogEvent(
            workspace_id=str(ws_id),
            run_id=run.id,
            workflow_id=wf_id,
            event_type="approval_timeout",
            severity="warning",
            payload={
                "minutes_waiting": minutes_waiting,
                "workflow_name": wf_name,
            },
        )
        db.add(event)
        approval_flagged += 1

        if _slack_enabled():
            _send_slack_alert(
                event_type="approval_timeout",
                run_id=str(run.id),
                workflow_name=wf_name,
                workspace_id=str(ws_id),
                detail=f"Approval has been pending for *{minutes_waiting} minutes*.",
            )

    db.commit()
    return {"stale_flagged": stale_flagged, "approval_flagged": approval_flagged}


def watchdog_loop() -> None:
    """Daemon thread entry point — runs scan() on a fixed interval."""
    log.info(
        "watchdog.started",
        stale_minutes=settings.watchdog_stale_minutes,
        approval_timeout_minutes=settings.watchdog_approval_timeout_minutes,
        interval_seconds=settings.watchdog_interval_seconds,
        slack_enabled=_slack_enabled(),
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
