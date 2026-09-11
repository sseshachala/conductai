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

from app.core.auth import get_workspace_id, require_permission, require_platform_operator
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
    _op: str = Depends(require_platform_operator()),
    db: Session = Depends(get_db),
) -> TrialOpsOut:
    """Platform-ops view of trial-key burn across all workspaces.

    Restricted to platform operators only (audit S05 — a tenant admin
    with `guard.spend.view_all` must NEVER be able to enumerate other
    tenants). Configure the allowlist via PLATFORM_OPERATOR_CLERK_IDS.
    Every metric derives from `guard_audit_events` joined against the
    trial `AgentIdentity` name filter.
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


# ─── /guard/trial/provision + /guard/trial/redeem — self-service signup ─────
#
# Hardened flow (audit S01 / S12). The old `/provision` endpoint took an
# email and immediately returned the caller's existing trial token if the
# address matched a Clerk user — trivially exploitable enumeration path.
#
# New two-step:
#   1. POST /guard/trial/provision  — mints a challenge + emails a
#      verification link. Returns a generic accepted response regardless
#      of whether the email exists in Clerk. Never leaks user existence.
#   2. POST /guard/trial/redeem     — validates the challenge (single
#      use, 30-min TTL). NEW emails get a workspace + trial token.
#      Existing emails get a sign-in link only — no token.
#
# Anti-abuse layered:
#   - Per-IP hourly cap (Redis) — trusted-proxy CIDR aware (audit S12)
#   - Per-email hourly cap (Redis)
#   - Global anonymous-flow budget (Redis)
#   - All three FAIL CLOSED when Redis is unreachable — no free
#     credential issuance without abuse controls in effect (audit S12).


import re as _re

from fastapi import HTTPException, Request

from app.core.email import send_template_email
from app.guard.receipts import web_base_url as _web_base_url
from app.modules.guard.trial_challenges import (
    check_email_rate as _check_email_rate,
    check_global_rate as _check_global_rate,
    client_ip_from as _client_ip_from,
    mint as _mint_challenge,
    redeem as _redeem_challenge,
)

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


class TrialProvisionAck(BaseModel):
    """Generic accepted response. Body is identical regardless of whether
    the email exists in Clerk — audit S01 requires that we NEVER leak
    user-existence to unauthenticated callers.
    """
    status: str = "accepted"
    message: str = "If the address is valid, a verification email is on the way."


class TrialRedeemIn(BaseModel):
    ct: str    # opaque challenge token from the verification email link


class TrialRedeemOut(BaseModel):
    # Either "new" (workspace + token returned) or "existing" (sign-in URL only).
    status: str
    workspace_id: str | None = None
    agent_token: str | None = None
    gateway_url: str | None = None
    proxy_base_url: str | None = None
    workspace_url: str | None = None
    sign_in_url: str | None = None
    # For the "existing" branch — where to send the user to log in.
    recovery_url: str | None = None


def _redis_or_fail_closed():
    """Return a Redis handle or None. Callers use None to reject the
    request — anonymous credential issuance without abuse controls in
    place is worse than a brief outage (audit S12).
    """
    try:
        from app.modules.guard.trial_upstream import _redis_client
        return _redis_client()
    except Exception:
        return None


def _throttle_by_ip(ip: str) -> bool:
    """Return True if under the per-hour cap; False if hit or Redis is
    unreachable. Fails CLOSED — audit S12 flagged the previous fail-open.
    """
    r = _redis_or_fail_closed()
    if r is None:
        return False
    key = f"guard:provision:ip:{ip}:{datetime.now(timezone.utc).strftime('%Y%m%d%H')}"
    try:
        pipe = r.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, _PROVISION_IP_WINDOW_SEC)
        count, _ = pipe.execute()
        return int(count or 0) <= _PROVISION_IP_CAP
    except Exception:
        return False


@router.post("/provision", response_model=TrialProvisionAck)
def provision_trial(
    body: TrialProvisionIn,
    request: Request,
    db: Session = Depends(get_db),
) -> TrialProvisionAck:
    """Kick off a verified trial signup (audit S01).

    Validates input, checks per-IP / per-email / global caps, mints a
    challenge, and emails a verification link. ALWAYS returns the same
    generic ack — no user-existence signal. Real token issuance happens
    in `/redeem` after the user clicks the emailed link.
    """
    from app.core.clerk import (
        ClerkError as _ClerkError,
        find_user_by_email as _clerk_find_user_by_email,
    )

    email = (body.email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="invalid_email")

    company = (body.company or "").strip()
    if not company:
        raise HTTPException(status_code=422, detail="company_required")

    ip = _client_ip_from(request)
    if not _throttle_by_ip(ip):
        raise HTTPException(status_code=429, detail="rate_limited")
    if not _check_email_rate(email):
        raise HTTPException(status_code=429, detail="rate_limited")
    if not _check_global_rate():
        raise HTTPException(status_code=429, detail="rate_limited")

    # Best-effort Clerk lookup — record whether the email is known so the
    # redeem path knows whether to mint a new workspace or return a
    # sign-in URL. Lookup failures are non-fatal: if Clerk is down, we
    # store existing_user_id=None and the redeem flow proceeds as "new"
    # (Clerk's create-user call at redeem time will 422 if it's actually
    # existing, and we can degrade to the sign-in path there).
    existing_user_id: str | None = None
    try:
        existing_user_id = _clerk_find_user_by_email(email)
    except _ClerkError as exc:
        log.warning("guard.trial.provision.clerk_lookup_failed", email=email, err=str(exc))

    token = _mint_challenge(email, company[:60], existing_user_id)
    if token is None:
        # Redis outage during mint — fail closed to match rate-limit behaviour.
        raise HTTPException(status_code=503, detail="verification_unavailable")

    verify_url = f"{_web_base_url()}/onboard/verify?ct={token}"
    sent = send_template_email(
        slug="trial_verify",
        to=email,
        context={"email": email, "verify_url": verify_url},
    )
    log.info(
        "guard.trial.provision.challenge_sent",
        email=email, company=company, ip=ip,
        existing_user=bool(existing_user_id), email_sent=sent,
    )
    return TrialProvisionAck()


@router.post("/redeem", response_model=TrialRedeemOut)
def redeem_trial(
    body: TrialRedeemIn,
    request: Request,
    db: Session = Depends(get_db),
) -> TrialRedeemOut:
    """Redeem a verified challenge (audit S01).

    Called by the web page the verification email links to. Atomic
    single-use consumption via Redis GETDEL — no double-redeem race even
    under concurrent clicks. NEW emails get a workspace + trial token.
    Existing emails get a sign-in URL only, never a token.
    """
    from app.core.clerk import (
        ClerkError as _ClerkError,
        create_user as _clerk_create_user,
        mint_sign_in_token as _clerk_mint_sign_in_token,
    )
    from app.modules.onboarding import provision_workspace_for_user

    # Per-IP throttle on redeem too — a leaked link is one thing, but a
    # botnet trying random challenge tokens against /redeem is another.
    ip = _client_ip_from(request)
    if not _throttle_by_ip(ip):
        raise HTTPException(status_code=429, detail="rate_limited")

    ct = (body.ct or "").strip()
    if not ct:
        raise HTTPException(status_code=422, detail="challenge_required")

    ch = _redeem_challenge(ct)
    if ch is None:
        # Unknown / expired / already redeemed — same generic response
        # regardless of which, so an attacker can't distinguish.
        raise HTTPException(status_code=410, detail="challenge_invalid_or_expired")

    _proxy_base = settings.conduct_proxy_url.rstrip("/")
    _web = _web_base_url()

    # Existing-email path — never issue an agent token here. The user
    # should sign in through their normal path; the verification just
    # confirmed the mailbox is reachable, not that they own the account
    # tied to it (the two are usually equivalent, but the security
    # invariant we care about is "no anonymous token issuance").
    if ch.existing_user_id:
        log.info("guard.trial.redeem.existing", email=ch.email, clerk_user_id=ch.existing_user_id, ip=ip)
        return TrialRedeemOut(
            status="existing",
            recovery_url=f"{_web}/sign-in",
        )

    # New-email path — create Clerk user + workspace atomically.
    try:
        clerk_user_id = _clerk_create_user(ch.email)
    except _ClerkError as exc:
        # 422 from Clerk means the address was actually taken between
        # mint and redeem (race with a browser signup). Degrade to the
        # existing-user response so we still never leak a token.
        if exc.status == 422:
            log.info("guard.trial.redeem.race_became_existing", email=ch.email, ip=ip)
            return TrialRedeemOut(status="existing", recovery_url=f"{_web}/sign-in")
        log.warning("guard.trial.redeem.clerk_create_failed", email=ch.email, status=exc.status, body=exc.body)
        if exc.status == 429:
            raise HTTPException(status_code=429, detail="rate_limited")
        raise HTTPException(status_code=502, detail="clerk_unavailable")

    # Shared onboarding — same function the `user.created` webhook uses.
    # Idempotent under the (extremely narrow) race where the webhook lands
    # before our commit: whoever wins, the loser returns the same row.
    ws_id_uuid = provision_workspace_for_user(db, clerk_user_id, name=ch.company[:60])
    db.commit()
    ws_id = str(ws_id_uuid)
    log.info("guard.trial.redeem.provisioned", workspace_id=ws_id, clerk_user_id=clerk_user_id, email=ch.email, ip=ip)

    row = _load_trial_identity(db, ws_id)
    if row is None:
        raise HTTPException(status_code=500, detail="trial_seed_failed")
    try:
        token = decrypt(row.token_encrypted)["token"]
    except Exception:
        raise HTTPException(status_code=500, detail="trial_token_decrypt_failed")

    sign_in_url = _clerk_mint_sign_in_token(clerk_user_id)
    return TrialRedeemOut(
        status="new",
        workspace_id=ws_id,
        agent_token=token,
        gateway_url=f"{_proxy_base}/anthropic",
        proxy_base_url=_proxy_base,
        workspace_url=f"{_web}/theguard",
        sign_in_url=sign_in_url,
    )
