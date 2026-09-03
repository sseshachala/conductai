"""Trial session endpoint for `/theguard/try` (epic #1567 PR 3).

`GET /guard/trial/session` — returns the caller workspace's trial state:
the pre-minted agent identity token, days remaining, gateway URL, and
today's cap usage. On-demand seeds if the workspace has no trial identity
yet (existing empty workspaces from before PR 1 merged).

The plaintext token is re-revealed every visit until the trial expires.
This is a bounded-cost trial identity capped by `TRIAL_DAILY_CAP` and
`AgentIdentity.expires_at`, so re-reveal is acceptable — production
identity tokens stay one-shot as before.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.config import settings
from app.core.crypto import decrypt
from app.core.database import get_db
from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, seed_trial
from app.modules.guard.trial_upstream import TRIAL_DAILY_CAP, get_trial_cap_used

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/trial", tags=["guard-trial"])


class TrialSessionOut(BaseModel):
    plan: str
    expired: bool
    ineligible: bool = False
    reason: str | None = None
    days_remaining: int
    token: str | None
    gateway_url: str
    cap_used: int
    cap_max: int


def _workspace_is_active(db: Session, workspace_id: str) -> bool:
    """A workspace is 'active' if it has ever run a workflow or wired any
    integration (vault key). Trial seeding is skipped for these — see PR 4
    cohort-2 fix."""
    has_run = db.execute(
        text("SELECT 1 FROM runs WHERE workspace_id = :ws LIMIT 1"),
        {"ws": workspace_id},
    ).fetchone()
    if has_run:
        return True
    has_creds = db.execute(
        text("SELECT 1 FROM integrations WHERE workspace_id = :ws LIMIT 1"),
        {"ws": workspace_id},
    ).fetchone()
    return bool(has_creds)


def _load_trial_identity(db: Session, workspace_id: str):
    return db.execute(
        text("""
            SELECT id, token_encrypted, expires_at
            FROM agent_identities
            WHERE workspace_id = :ws AND name = :name
              AND lifecycle_state = 'active'
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"ws": workspace_id, "name": TRIAL_IDENTITY_NAME},
    ).fetchone()


@router.get("/session", response_model=TrialSessionOut)
def get_trial_session(
    workspace_id: str = Depends(get_workspace_id),
    _perm: str = Depends(require_permission("platform.workflows.view")),
    db: Session = Depends(get_db),
) -> TrialSessionOut:
    plan_row = db.execute(
        text("SELECT plan FROM workspaces WHERE id = :ws"),
        {"ws": workspace_id},
    ).fetchone()
    plan = plan_row.plan if plan_row else ""

    identity = _load_trial_identity(db, workspace_id)
    if identity is None:
        # PR 4: active workspaces (any run or vault key) don't get a trial
        # identity minted for them. The page renders a "you're past the
        # trial" panel and points them at the real gateway path.
        if _workspace_is_active(db, workspace_id):
            log.info("guard.trial.refused_active_workspace", workspace_id=workspace_id)
            return TrialSessionOut(
                plan=plan, expired=False, ineligible=True, reason="active_workspace",
                days_remaining=0, token=None,
                gateway_url=settings.conduct_proxy_url,
                cap_used=0, cap_max=TRIAL_DAILY_CAP,
            )
        seed_trial(db, workspace_id)
        db.commit()
        identity = _load_trial_identity(db, workspace_id)
        # PR 5: re-read plan from DB — `seed_trial` only flips `free`, so a
        # paid empty workspace stays on its actual plan (e.g. 'pro').
        plan_row = db.execute(
            text("SELECT plan FROM workspaces WHERE id = :ws"),
            {"ws": workspace_id},
        ).fetchone()
        plan = plan_row.plan if plan_row else plan
        log.info("guard.trial.seed_on_demand", workspace_id=workspace_id)

    if identity is None:
        return TrialSessionOut(
            plan=plan, expired=True, days_remaining=0,
            token=None, gateway_url=settings.conduct_proxy_url,
            cap_used=0, cap_max=TRIAL_DAILY_CAP,
        )

    now = datetime.now(timezone.utc)
    expired = identity.expires_at is None or identity.expires_at <= now
    days_remaining = max(0, (identity.expires_at - now).days) if identity.expires_at else 0

    token = None
    if not expired:
        try:
            token = decrypt(identity.token_encrypted).get("token")
        except Exception as exc:
            log.error("guard.trial.decrypt_failed", workspace_id=workspace_id, err=str(exc))
            token = None

    return TrialSessionOut(
        plan=plan,
        expired=expired,
        days_remaining=days_remaining if not expired else 0,
        token=token,
        gateway_url=settings.conduct_proxy_url,
        cap_used=get_trial_cap_used(db, workspace_id, str(identity.id)),
        cap_max=TRIAL_DAILY_CAP,
    )


# ── Trial ops (A1 of #1587) ───────────────────────────────────────────────────

class TrialTopSpender(BaseModel):
    workspace_id: str
    workspace_name: str | None
    spend_usd: float
    cap_used: int


class TrialOpsOut(BaseModel):
    trial_workspaces_active_24h: int
    workspaces_at_cap: int
    spend_today_usd: float
    top_10_by_spend: list[TrialTopSpender]
    cap_max: int


@router.get("/ops", response_model=TrialOpsOut)
def get_trial_ops(
    _perm: str = Depends(require_permission("guard.spend.view_all")),
    db: Session = Depends(get_db),
) -> TrialOpsOut:
    """Platform-ops view of trial-key burn across all workspaces.

    Restricted to `guard.spend.view_all` (security+) — this crosses tenant
    boundaries by design. Every metric derives from `guard_audit_events`
    joined against the trial `AgentIdentity` name filter.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    active_24h = db.execute(
        text("""
            SELECT COUNT(DISTINCT ae.workspace_id)
            FROM guard_audit_events ae
            JOIN agent_identities ai ON ai.id = ae.agent_identity_id
            WHERE ai.name = :name AND ae.ts >= :cutoff
        """),
        {"name": TRIAL_IDENTITY_NAME, "cutoff": cutoff},
    ).scalar() or 0

    spend_today = db.execute(
        text("""
            SELECT COALESCE(SUM(ae.cost_usd_after), 0)
            FROM guard_audit_events ae
            JOIN agent_identities ai ON ai.id = ae.agent_identity_id
            WHERE ai.name = :name AND ae.ts >= :cutoff
        """),
        {"name": TRIAL_IDENTITY_NAME, "cutoff": cutoff},
    ).scalar() or 0.0

    top_rows = db.execute(
        text("""
            SELECT
                ae.workspace_id,
                w.name AS workspace_name,
                COALESCE(SUM(ae.cost_usd_after), 0) AS spend,
                COUNT(*) AS cap_used
            FROM guard_audit_events ae
            JOIN agent_identities ai ON ai.id = ae.agent_identity_id
            JOIN workspaces w ON w.id = ae.workspace_id
            WHERE ai.name = :name AND ae.ts >= :cutoff
            GROUP BY ae.workspace_id, w.name
            ORDER BY spend DESC, cap_used DESC
            LIMIT 10
        """),
        {"name": TRIAL_IDENTITY_NAME, "cutoff": cutoff},
    ).fetchall()

    at_cap = sum(1 for r in top_rows if r.cap_used >= TRIAL_DAILY_CAP)

    return TrialOpsOut(
        trial_workspaces_active_24h=int(active_24h),
        workspaces_at_cap=at_cap,
        spend_today_usd=float(spend_today),
        top_10_by_spend=[
            TrialTopSpender(
                workspace_id=str(r.workspace_id),
                workspace_name=r.workspace_name,
                spend_usd=float(r.spend),
                cap_used=int(r.cap_used),
            )
            for r in top_rows
        ],
        cap_max=TRIAL_DAILY_CAP,
    )
