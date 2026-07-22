"""
GET /guard/verify/evidence — OWASP Agentic Top 10 coverage + governance grade.
GET /guard/verify/chain   — Walk the SHA-256 hash chain and confirm integrity.
POST /guard/verify/run    — Run adversarial test battery and persist results.
GET /guard/verify/history — Fetch past battery run summaries.

Reads existing guard_config, policies, signing keys, and audit events.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.models.workspace import Workspace
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardConfig,
    GuardVerifyRun,
    WorkspaceCustomRule,
    WorkspaceSigningKey,
    WorkspaceSkillPack,
)
from app.modules.guard.test_battery import run_battery

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


# ── Chain integrity ───────────────────────────────────────────────────────────

class ChainVerifyOut(BaseModel):
    valid: bool
    events_checked: int
    broken_at: Optional[str] = None   # ISO timestamp of first broken link
    first_event: Optional[str] = None
    last_event: Optional[str] = None
    verified_at: str


@router.get("/chain", response_model=ChainVerifyOut)
def verify_chain(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Walk every audit event in insertion order and recompute the SHA-256 chain.
    Returns valid=True only when every entry_hash matches its recomputed value."""
    ws_uuid = uuid.UUID(workspace_id)
    org_ws  = _org_ws_subquery(db, workspace_id)

    rows = (
        db.query(
            GuardAuditEvent.ts,
            GuardAuditEvent.tool_call,
            GuardAuditEvent.decision,
            GuardAuditEvent.entry_hash,
        )
        .filter(GuardAuditEvent.workspace_id.in_(org_ws))
        .order_by(GuardAuditEvent.ts.asc())
        .yield_per(1000)
    )

    broken_at = None
    prev = ""
    count = 0
    first_event = None
    last_event = None
    for ev in rows:
        count += 1
        if first_event is None:
            first_event = ev.ts.isoformat()
        last_event = ev.ts.isoformat()
        expected = hashlib.sha256(
            f"{ev.ts.isoformat()}|{ev.tool_call or ''}|{ev.decision}|{prev}".encode()
        ).hexdigest()
        if ev.entry_hash and ev.entry_hash != expected:
            broken_at = ev.ts.isoformat()
            break
        prev = ev.entry_hash or prev

    return ChainVerifyOut(
        valid=broken_at is None,
        events_checked=count,
        broken_at=broken_at,
        first_event=first_event,
        last_event=last_event,
        verified_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Guard Verify v2 — adversarial battery ─────────────────────────────────────

class TestResult(BaseModel):
    asi: str
    name: str
    tool: str
    expected: str
    actual: str
    verdict: str
    matched_rule: Optional[str]


class VerifyRunOut(BaseModel):
    run_id: str
    score: int
    grade: str
    passed_tests: int
    total_tests: int
    results: list[TestResult]
    created_at: str


class VerifyRunSummary(BaseModel):
    run_id: str
    score: int
    grade: str
    passed_tests: int
    total_tests: int
    created_at: str


class VerifyHistoryOut(BaseModel):
    runs: list[VerifyRunSummary]


@router.post("/run", response_model=VerifyRunOut)
def run_verify_battery(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Execute the adversarial test battery against the workspace's compiled policy.

    Runs 10 simulated hook-level tool calls covering ASI-01 through ASI-10 and
    measures how many the current Guard configuration correctly intercepts.
    Persists the result as a GuardVerifyRun row and writes an audit event so
    the run appears in the Guard activity trail.

    Score = (passed / total) * 100. Grade via the same _grade() thresholds used
    by GET /guard/verify/evidence.
    """
    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)

    results = run_battery(db, workspace_id)

    total_tests  = len(results)
    passed_tests = sum(1 for r in results if r["verdict"] == "held")
    score        = round(passed_tests / total_tests * 100) if total_tests else 0
    grade        = _grade(score)

    run = GuardVerifyRun(
        workspace_id=ws_uuid,
        score=score,
        grade=grade,
        results=results,
        total_tests=total_tests,
        passed_tests=passed_tests,
    )
    db.add(run)

    # Write an audit event so the verify run appears in the Guard activity feed.
    audit = GuardAuditEvent(
        workspace_id=ws_uuid,
        ai_tool="guard.verify",
        tool_call="guard.verify",
        source="hook",
        decision="verify_run",
        input_summary=f"Verify battery: {passed_tests}/{total_tests} held (grade {grade})",
        ts=now,
    )
    db.add(audit)

    db.commit()
    db.refresh(run)

    return VerifyRunOut(
        run_id=str(run.id),
        score=run.score,
        grade=run.grade,
        passed_tests=run.passed_tests,
        total_tests=run.total_tests,
        results=[TestResult(**r) for r in run.results],
        created_at=run.created_at.isoformat(),
    )


@router.get("/history", response_model=VerifyHistoryOut)
def get_verify_history(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    limit: int = Query(default=30, ge=1, le=200),
):
    """Return recent Guard Verify battery runs for the workspace.

    Returns summary rows only (no per-test results) to keep the payload light.
    Use GET /guard/verify/run/{run_id} for full drill-down (future endpoint).
    """
    ws_uuid = uuid.UUID(workspace_id)

    rows = (
        db.query(GuardVerifyRun)
        .filter(GuardVerifyRun.workspace_id == ws_uuid)
        .order_by(GuardVerifyRun.created_at.desc())
        .limit(limit)
        .all()
    )

    return VerifyHistoryOut(
        runs=[
            VerifyRunSummary(
                run_id=str(r.id),
                score=r.score,
                grade=r.grade,
                passed_tests=r.passed_tests,
                total_tests=r.total_tests,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ]
    )
