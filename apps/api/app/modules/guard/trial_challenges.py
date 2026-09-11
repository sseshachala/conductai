"""Trial-provisioning verification challenges (audit S01).

The unauthenticated `/guard/trial/provision` used to hand back an existing
user's decrypted trial token to any anonymous caller who guessed their
email. This module replaces that flow with a two-step verification:

1. `POST /guard/trial/provision` mints a challenge, emails the caller a
   link with an opaque token, and returns a generic accepted response
   regardless of whether the email exists in Clerk. The response body
   never leaks user existence.
2. `POST /guard/trial/redeem {ct}` validates the challenge and, only for
   verified NEW emails, mints a Clerk user + workspace + trial token.
   Existing-email challenges resolve to a sign-in link with no token.

Storage: Redis with a 30-minute TTL (self-cleaning, single-use, and the
same Redis we already require for the rate-limiter). Challenges are keyed
by SHA-256 of the raw token so the plaintext never lands in Redis.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import secrets
import time
from dataclasses import dataclass

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

_TTL_SECONDS = 30 * 60           # 30 min — long enough for the user to click the email link
_CHALLENGE_KEY_PREFIX = "guard:trial:challenge:"
_EMAIL_RATE_KEY_PREFIX = "guard:trial:email:"
_GLOBAL_RATE_KEY = "guard:trial:global"
_PER_EMAIL_CAP = 3               # per hour, per email address
_GLOBAL_CAP = 200                # per hour, all anonymous provisions combined


@dataclass
class Challenge:
    """One redemption record. Never serialised with the plaintext token."""

    email: str
    company: str
    existing_user_id: str | None    # populated at mint time if Clerk already knows the email
    created_at: float


def _redis():
    """Return a live Redis handle or None. Callers decide the fail-mode.

    The trial provision path fails CLOSED (no free credential issuance
    without abuse controls) — see audit S12. Other consumers may prefer
    fail-open; make that decision at the call site, never here.
    """
    try:
        from app.modules.guard.trial_upstream import _redis_client
        return _redis_client()
    except Exception as exc:
        log.warning("guard.trial.redis_unavailable", err=str(exc))
        return None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def check_email_rate(email: str) -> bool:
    """Return True if this email can mint another challenge in the current
    hour bucket. False if the per-email cap is exhausted. Fails CLOSED on
    Redis outage — see audit S12.
    """
    r = _redis()
    if r is None:
        return False
    bucket = time.strftime("%Y%m%d%H", time.gmtime())
    key = f"{_EMAIL_RATE_KEY_PREFIX}{email}:{bucket}"
    try:
        pipe = r.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, 3600)
        count, _ = pipe.execute()
        return int(count or 0) <= _PER_EMAIL_CAP
    except Exception as exc:
        log.warning("guard.trial.email_rate_check_failed", err=str(exc))
        return False


def check_global_rate() -> bool:
    """Global anonymous-flow budget. Fails CLOSED on Redis outage.

    A per-IP cap is not enough — a low-cost botnet spreads across enough
    IPs to defeat it. The global cap bounds worst-case Clerk-user-creation
    spend when the per-IP + per-email limits are all being pushed.
    """
    r = _redis()
    if r is None:
        return False
    bucket = time.strftime("%Y%m%d%H", time.gmtime())
    key = f"{_GLOBAL_RATE_KEY}:{bucket}"
    try:
        pipe = r.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, 3600)
        count, _ = pipe.execute()
        return int(count or 0) <= _GLOBAL_CAP
    except Exception as exc:
        log.warning("guard.trial.global_rate_check_failed", err=str(exc))
        return False


def mint(email: str, company: str, existing_user_id: str | None) -> str | None:
    """Store a fresh challenge in Redis, return the raw token. None on
    Redis outage — caller must fail closed.
    """
    r = _redis()
    if r is None:
        return None
    token = secrets.token_urlsafe(32)
    payload = json.dumps({
        "email": email,
        "company": company,
        "existing_user_id": existing_user_id,
        "created_at": time.time(),
    })
    try:
        r.setex(f"{_CHALLENGE_KEY_PREFIX}{_hash(token)}", _TTL_SECONDS, payload)
        return token
    except Exception as exc:
        log.warning("guard.trial.challenge_mint_failed", err=str(exc))
        return None


def redeem(token: str) -> Challenge | None:
    """Atomically consume a challenge. Returns the Challenge on success,
    None if the token is unknown, expired, or already redeemed.
    """
    r = _redis()
    if r is None:
        return None
    key = f"{_CHALLENGE_KEY_PREFIX}{_hash(token)}"
    try:
        # GETDEL is atomic — no double-redeem race even under concurrent clicks.
        raw = r.getdel(key)
    except Exception as exc:
        log.warning("guard.trial.challenge_redeem_failed", err=str(exc))
        return None
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return Challenge(
            email=data["email"],
            company=data["company"],
            existing_user_id=data.get("existing_user_id"),
            created_at=float(data.get("created_at", 0)),
        )
    except Exception as exc:
        log.warning("guard.trial.challenge_parse_failed", err=str(exc))
        return None


# ── Trusted-proxy X-Forwarded-For parsing (audit S12) ───────────────────────

def _parse_cidrs(raw: str) -> list[ipaddress._BaseNetwork]:
    out: list[ipaddress._BaseNetwork] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            log.warning("guard.trial.trusted_proxy_cidr_invalid", cidr=chunk)
    return out


def client_ip_from(request) -> str:
    """Extract the caller's IP, respecting only configured trusted proxies.

    Behaviour:
    - If TRUSTED_PROXY_CIDRS is unset, ignore X-Forwarded-For entirely and
      return request.client.host. Blind trust on the first XFF value lets
      any anonymous caller forge their IP against the per-IP limiter
      (audit S12).
    - If TRUSTED_PROXY_CIDRS is set, walk XFF from RIGHT to LEFT and skip
      addresses that fall inside a trusted CIDR. The first non-trusted
      address is the real client. If every hop is trusted (shouldn't
      happen), fall back to the leftmost XFF entry.
    """
    trusted = _parse_cidrs(settings.trusted_proxy_cidrs)
    if not trusted:
        return request.client.host if request.client else "unknown"

    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if not xff:
        return request.client.host if request.client else "unknown"

    hops = [h.strip() for h in xff.split(",") if h.strip()]
    for hop in reversed(hops):
        try:
            ip = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if not any(ip in net for net in trusted):
            return hop
    # Everything was trusted — fall back to the leftmost hop and log so
    # we notice a misconfigured CIDR list.
    log.warning("guard.trial.all_xff_hops_trusted", xff=xff)
    return hops[0]
