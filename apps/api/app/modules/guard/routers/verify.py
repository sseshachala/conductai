"""
GET /guard/verify/evidence — OWASP Agentic Top 10 coverage + governance grade.

Reads existing guard_config, policies, signing keys, and recent audit events.
No new tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.models.workspace import Workspace
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardConfig,
    WorkspaceCustomRule,
    WorkspaceSigningKey,
    WorkspaceSkillPack,
)

router = APIRouter(prefix="/guard/verify", tags=["guard"])

# ── ASI control definitions ───────────────────────────────────────────────────

_CONTROLS = [
    ("ASI-01", "Prompt Injection",           "PreToolUse hook intercepts before LLM call"),
    ("ASI-02", "Insecure Tool Use",          "Guard proxy enforces tool-use policies"),
    ("ASI-03", "Excessive Agency",           "Turn budgets + max_cost_usd caps"),
    ("ASI-04", "Unauthorized Escalation",    "RBAC + require_permission() on all endpoints"),
    ("ASI-05", "Trust Boundary Violation",   "All LLM traffic routed through Guard proxy"),
    ("ASI-06", "Insufficient Logging",       "guard_audit_events with SHA-256 hash chain"),
    ("ASI-07", "Insecure Identity",          "agent_role_id + member tokens per agent"),
    ("ASI-08", "Policy Bypass",              "fail_mode=fail_closed blocks on Guard outage"),
    ("ASI-09", "Supply Chain Integrity",     "Signed policies (signing_key)"),
    ("ASI-10", "Behavioral Anomaly",         "Session scanning + violations_count tracking"),
]

_GRADES = [
    (85, "A"),
    (65, "B"),
    (45, "C"),
    (25, "D"),
    (0,  "F"),
]


def _grade(score: int) -> str:
    for threshold, letter in _GRADES:
        if score >= threshold:
            return letter
    return "F"


def _org_ws_subquery(db: Session, workspace_id: str):
    ws_uuid = uuid.UUID(workspace_id)
    ws = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
    if ws and ws.org_id:
        return db.query(Workspace.id).filter(Workspace.org_id == ws.org_id).subquery()
    if ws and ws.owner_id:
        return db.query(Workspace.id).filter(Workspace.owner_id == ws.owner_id).subquery()
    return db.query(Workspace.id).filter(Workspace.id == ws_uuid).subquery()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ControlStatus(BaseModel):
    id: str
    name: str
    status: str        # "active" | "partial" | "missing"
    control: str
    evidence_ref: Optional[str] = None


class EvidenceOut(BaseModel):
    grade: str
    coverage_pct: int
    passed: bool
    score: int
    blocked_24h: int
    events_24h: int
    controls: list[ControlStatus]
    generated_at: str
    workspace_id: str


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/evidence", response_model=EvidenceOut)
def get_verify_evidence(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Compute governance grade + OWASP ASI coverage. Reads existing tables only."""
    ws_uuid = uuid.UUID(workspace_id)
    org_ws  = _org_ws_subquery(db, workspace_id)
    now     = datetime.now(timezone.utc)
    since   = now - timedelta(hours=24)

    gc = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()

    signing_key = db.query(WorkspaceSigningKey).filter(
        WorkspaceSigningKey.workspace_id == ws_uuid
    ).first()

    policy_count = (
        db.query(WorkspaceCustomRule)
        .filter(WorkspaceCustomRule.workspace_id.in_(org_ws))
        .count()
        + db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id.in_(org_ws))
        .count()
    )

    events_24h = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= since,
        )
        .count()
    )

    blocked_24h = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= since,
            GuardAuditEvent.decision == "blocked",
        )
        .count()
    )

    # ── Score ──────────────────────────────────────────────────────────────
    score = 0
    guard_active = bool(gc and gc.enforcement_mode in ("block", "warn", "audit"))

    if gc:
        if gc.enforcement_mode == "block":
            score += 30
        elif gc.enforcement_mode == "warn":
            score += 15
        elif gc.enforcement_mode == "audit":
            score += 5

        if gc.fail_mode == "fail_closed":
            score += 15
        if gc.deny_on_error:
            score += 10

    if signing_key:
        score += 15

    if policy_count >= 5:
        score += 20
    elif policy_count > 0:
        score += 10

    if events_24h > 0:
        score += 10

    # ── Controls ───────────────────────────────────────────────────────────
    fail_closed = gc and gc.fail_mode == "fail_closed"

    def _status(asi: str) -> str:
        if asi in ("ASI-01", "ASI-02", "ASI-05"):
            return "active" if guard_active else "missing"
        if asi in ("ASI-03", "ASI-04"):
            return "active"
        if asi == "ASI-06":
            if guard_active and events_24h > 0:
                return "active"
            return "partial" if guard_active else "missing"
        if asi == "ASI-07":
            return "partial"
        if asi == "ASI-08":
            return "active" if fail_closed else "partial"
        if asi == "ASI-09":
            return "active" if signing_key else "missing"
        if asi == "ASI-10":
            return "partial"
        return "missing"

    controls = [
        ControlStatus(
            id=asi,
            name=name,
            status=_status(asi),
            control=control,
        )
        for asi, name, control in _CONTROLS
    ]

    active_count = sum(1 for c in controls if c.status == "active")
    coverage_pct = round(active_count / len(controls) * 100)
    grade        = _grade(score)

    return EvidenceOut(
        grade=grade,
        coverage_pct=coverage_pct,
        passed=(grade in ("A", "B")),
        score=score,
        blocked_24h=blocked_24h,
        events_24h=events_24h,
        controls=controls,
        generated_at=now.isoformat(),
        workspace_id=workspace_id,
    )
