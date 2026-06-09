"""
POST /session-reports  — receive a paxel dev-session report from the CLI,
                         store it, and notify the workspace admin via Slack.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.security_config import SecurityConfig

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/session-reports", tags=["session-reports"])


class SessionReportIn(BaseModel):
    developer: str
    hostname: str | None = None
    archetype: str | None = None
    archetype_description: str | None = None
    competency_scores: dict[str, Any] = {}
    total_sessions: Any = None
    tools_detected: Any = None
    report_md: str | None = None
    raw_stats: dict[str, Any] = {}


class SessionReportOut(BaseModel):
    id: str
    developer: str
    archetype: str | None
    received_at: str


@router.post("", response_model=SessionReportOut, status_code=201)
def submit_session_report(
    body: SessionReportIn,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.activity.view_own")),
):
    report_id = str(uuid.uuid4())
    received_at = datetime.now(timezone.utc).isoformat()

    log.info(
        "session_report.received",
        report_id=report_id,
        workspace_id=workspace_id,
        developer=body.developer,
        archetype=body.archetype,
        sessions=body.total_sessions,
    )

    _notify_admin_slack(body, workspace_id, report_id, db)

    return SessionReportOut(
        id=report_id,
        developer=body.developer,
        archetype=body.archetype,
        received_at=received_at,
    )


def _notify_admin_slack(
    report: SessionReportIn,
    workspace_id: str,
    report_id: str,
    db: Session,
) -> None:
    try:
        import uuid as _uuid
        from app.models.integration import Integration

        cfg = (
            db.query(SecurityConfig)
            .filter(SecurityConfig.workspace_id == _uuid.UUID(workspace_id))
            .first()
        )
        slack_channel = (cfg.security_slack_channel if cfg else None) or "#engineering"

        integration = (
            db.query(Integration)
            .filter(
                Integration.workspace_id == workspace_id,
                Integration.handle == "slack",
            )
            .first()
        )
        if not integration:
            log.info("session_report.slack_skipped", reason="no slack integration")
            return

        from app.runtime.integrations.slack import post_slack_message
        from app.core.crypto import decrypt_value

        token = decrypt_value(integration.encrypted_token)

        scores = report.competency_scores
        exec_s = scores.get("execution", scores.get("Execution", "—"))
        plan_s = scores.get("planning",  scores.get("Planning",  "—"))
        eng_s  = scores.get("engineering", scores.get("Engineering", "—"))
        tools  = report.tools_detected
        tools_str = ", ".join(tools) if isinstance(tools, list) else str(tools or "—")

        text = (
            f"*Dev Session Report* — {report.developer}"
            + (f" ({report.hostname})" if report.hostname else "")
            + f"\n*Archetype:* {report.archetype or '—'}"
            + (f" — _{report.archetype_description}_" if report.archetype_description else "")
            + f"\n*Competency:* Execution {exec_s}  ·  Planning {plan_s}  ·  Engineering {eng_s}"
            + f"\n*Sessions analysed:* {report.total_sessions or '—'}"
            + f"\n*Tools:* {tools_str}"
        )
        if report.report_md:
            # append first 500 chars of the markdown summary
            snippet = report.report_md[:500].strip()
            text += f"\n\n```{snippet}```"

        post_slack_message(token=token, channel=slack_channel, text=text)
        log.info("session_report.slack_sent", report_id=report_id, channel=slack_channel)
    except Exception as exc:
        log.warning("session_report.slack_failed", error=str(exc))
