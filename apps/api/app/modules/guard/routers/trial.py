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
from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, TRIAL_PLAN, seed_trial
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


# ─── /guard/trial/provision — self-service curl-install endpoint (#1712 Track 1) ─
#
# `curl -fsSL conduct.ai/install | sh` posts an email + optional company to
# this endpoint. Unauthenticated (no Clerk session, no Bearer token) but
# email is REQUIRED — this is a signup form, not an identity-anonymous
# mint. We provision a trial workspace + agent identity token and return
# them so the shell script can drop `~/.conduct/env` on the caller's laptop.
#
# The email is stashed on workspace.owner_id as a plain string (not yet a
# Clerk user id). A later `conduct claim` / magic-link flow can bind the
# workspace to a real Clerk account.
#
# Anti-abuse:
#   - IP rate-limit: 5 provisions per hour (Redis atomic INCR)
#   - Email idempotency: repeat POST with same email within the trial
#     window returns the SAME trial token instead of minting a second
#     workspace. Protects platform-key spend and keeps ~/.conduct/env
#     stable when the user re-runs the installer.


import re as _re

from fastapi import HTTPException, Request

from app.guard.receipts import web_base_url as _web_base_url

_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PROVISION_IP_CAP = 5   # per hour
_PROVISION_IP_WINDOW_SEC = 3600


class TrialProvisionIn(BaseModel):
    email: str
    company: str
    # Optional caller-provided source tag (marketing attribution, referrer).
    # Ignored by the provisioning path — stored in preferences for later
    # analytics without altering the trial contract itself.
    source: str | None = None


class TrialProvisionOut(BaseModel):
    workspace_id: str
    agent_token: str
    gateway_url: str
    workspace_url: str


def _redis_or_none():
    """Best-effort Redis handle — fail-open on outage (matches trial_upstream
    convention). No throttle when Redis is down is preferable to blocking
    installs entirely."""
    try:
        from app.modules.guard.trial_upstream import _redis_client
        return _redis_client()
    except Exception:
        return None


def _ip_of(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _throttle_by_ip(ip: str) -> bool:
    """Return True if under the per-hour cap; False if the cap is hit.
    Fails open when Redis is unreachable."""
    r = _redis_or_none()
    if r is None:
        return True
    key = f"guard:provision:ip:{ip}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
    try:
        pipe = r.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, _PROVISION_IP_WINDOW_SEC)
        count, _ = pipe.execute()
        return int(count or 0) <= _PROVISION_IP_CAP
    except Exception:
        return True


def _find_existing_trial_by_email(db: Session, email: str) -> str | None:
    """Return the workspace_id of an active trial owned by this email, or None.

    An 'active' trial here = plan free_trial + owner_id matches email + trial
    identity still `active` (not swept by teardown). Same email posting twice
    within the trial window gets the same workspace back — idempotent."""
    row = db.execute(
        text("""
            SELECT w.id
            FROM workspaces w
            JOIN agent_identities ai
              ON ai.workspace_id = w.id
             AND ai.name = :name
             AND ai.lifecycle_state = 'active'
             AND (ai.expires_at IS NULL OR ai.expires_at > :now)
            WHERE w.owner_id = :owner AND w.plan = :plan
            ORDER BY w.created_at DESC
            LIMIT 1
        """),
        {
            "owner": email, "plan": TRIAL_PLAN,
            "name": TRIAL_IDENTITY_NAME,
            "now": datetime.now(timezone.utc),
        },
    ).fetchone()
    return str(row.id) if row else None


@router.post("/provision", response_model=TrialProvisionOut)
def provision_trial(
    body: TrialProvisionIn,
    request: Request,
    db: Session = Depends(get_db),
) -> TrialProvisionOut:
    """Anonymous trial workspace provisioning.

    Called by `scripts/install.sh` (curl | sh). Returns the trial agent
    token so the shell script can drop it in ``~/.conduct/env``.
    """
    # `seed_trial` is imported at module top; local re-imports here would
    # shadow patches (used by tests) — keep the top-level binding.
    from app.models.workspace import Workspace as _WS
    import uuid as _uuid

    email = (body.email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="invalid_email")

    company = (body.company or "").strip()
    if not company:
        raise HTTPException(status_code=422, detail="company_required")

    ip = _ip_of(request)
    if not _throttle_by_ip(ip):
        raise HTTPException(
            status_code=429,
            detail=f"provision_rate_limited: {_PROVISION_IP_CAP}/hour per IP",
        )

    # Idempotency: same email within trial lifetime → return existing token.
    ws_id = _find_existing_trial_by_email(db, email)
    if ws_id is None:
        ws = _WS(
            id=_uuid.uuid4(),
            name=f"{company[:60]} · trial",
            owner_id=email,
            plan="free",           # seed_trial flips to free_trial
            is_approved=True,
            preferences={
                # Signup metadata — surfaced in trial ops dashboards and
                # available for later SDR follow-up. Kept in a namespaced
                # sub-object so downstream preference keys don't collide.
                "trial_signup": {
                    "email": email,
                    "company": company,
                    "source": (body.source or "curl-install")[:60],
                    "ip": ip,
                    "at": datetime.now(timezone.utc).isoformat(),
                },
            },
        )
        db.add(ws)
        db.flush()
        ws_id = str(ws.id)
        seed_trial(db, ws_id)
        db.commit()
        log.info(
            "guard.trial.provisioned",
            workspace_id=ws_id, email=email, company=company, ip=ip,
        )
    else:
        # Idempotent re-provision — no side effects, just re-reveal the
        # existing token below. seed_trial(); is a no-op on an already-seeded
        # workspace but we skip it entirely to avoid extra writes.
        log.info(
            "guard.trial.provision_replayed",
            workspace_id=ws_id, email=email, ip=ip,
        )

    # Fetch + decrypt the trial identity token to return to the caller.
    row = _load_trial_identity(db, ws_id)
    if row is None:
        # seed_trial should have written one; if not, something is very wrong.
        raise HTTPException(status_code=500, detail="trial_seed_failed")
    try:
        token = decrypt(row.token_encrypted)["token"]
    except Exception:
        raise HTTPException(status_code=500, detail="trial_token_decrypt_failed")

    # Anthropic SDK does `POST {base}/v1/messages`, so ANTHROPIC_BASE_URL
    # must land on the vendor-specific route (`/proxy/anthropic`), not the
    # bare `/proxy` root. Endpoint paths for other providers live under
    # `/proxy/openai` and `/proxy/perplexity` — install.sh only wires
    # Anthropic today; users who want OpenAI/Perplexity edit their env
    # file directly.
    return TrialProvisionOut(
        workspace_id=ws_id,
        agent_token=token,
        gateway_url=f"{settings.conduct_proxy_url.rstrip('/')}/anthropic",
        workspace_url=f"{_web_base_url()}/theguard",
    )
