"""Clerk backend API helpers (#1712 Track 1 PR 5 unification).

Server-to-server calls to `https://api.clerk.com/v1/*`. Same auth pattern
as `apps/api/app/routers/projects.py::_clerk_headers` (Bearer with
`settings.clerk_secret_key`). Split out here so the curl-install trial
provisioning path can create Clerk users + sign-in tokens without pulling
projects.py's org-and-invitation surface as a dependency.

All helpers fail loudly with ClerkError so callers can distinguish
"Clerk said no" (e.g. duplicate email) from generic 500s. Callers should
check `settings.clerk_secret_key` before calling — no-op if unset (local
dev without a Clerk instance).
"""
from __future__ import annotations

from typing import Optional

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

CLERK_API = "https://api.clerk.com/v1"


class ClerkError(Exception):
    """Raised when the Clerk API returns a non-2xx response."""

    def __init__(self, status: int, message: str, body: str = ""):
        super().__init__(f"Clerk {status}: {message}")
        self.status = status
        self.message = message
        self.body = body


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.clerk_secret_key}",
        "Content-Type": "application/json",
    }


def find_user_by_email(email: str) -> Optional[str]:
    """Return the Clerk user_id for a given email, or None if no user
    exists with that primary email. Raises ClerkError on 5xx / auth errors.
    Returns None on 200-with-empty-list — that's "not found", not an error.
    """
    if not settings.clerk_secret_key:
        return None
    try:
        r = httpx.get(
            f"{CLERK_API}/users",
            headers=_headers(),
            params={"email_address": email},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        log.warning("clerk.find_user.network", email=email, err=str(exc))
        raise ClerkError(status=0, message=f"network: {exc}") from exc
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise ClerkError(status=r.status_code, message="find_user_by_email failed", body=r.text[:500])
    users = r.json() or []
    if not users:
        return None
    # Clerk returns most-recent-first. The email match is exact via query
    # param, so first result is the caller's user.
    return users[0].get("id")


def create_user(email: str) -> str:
    """Create a Clerk user for `email`. Returns the new `user_id`.

    - `skip_password_requirement=True` — no password on file; sign-in
      happens via magic-link / OAuth / sign-in token.
    - `skip_password_checks=True` — belt-and-braces, some Clerk instances
      require this to accept passwordless creation.

    Raises ClerkError if Clerk rejects (422 typically means email already
    exists — callers should look-up-first via `find_user_by_email`)."""
    if not settings.clerk_secret_key:
        raise ClerkError(status=0, message="clerk_secret_key not configured")
    try:
        r = httpx.post(
            f"{CLERK_API}/users",
            headers=_headers(),
            json={
                "email_address": [email],
                "skip_password_requirement": True,
                "skip_password_checks": True,
            },
            timeout=15,
        )
    except httpx.HTTPError as exc:
        log.warning("clerk.create_user.network", email=email, err=str(exc))
        raise ClerkError(status=0, message=f"network: {exc}") from exc
    if r.status_code >= 400:
        raise ClerkError(status=r.status_code, message="create_user failed", body=r.text[:500])
    data = r.json()
    user_id = data.get("id")
    if not user_id:
        raise ClerkError(status=r.status_code, message="create_user missing id", body=r.text[:500])
    log.info("clerk.user_created", email=email, user_id=user_id)
    return user_id


def mint_sign_in_token(clerk_user_id: str, expires_in_seconds: int = 86400) -> Optional[str]:
    """Return a one-time sign-in URL (or None if Clerk isn't configured
    or the mint failed). The URL takes the recipient straight to a
    logged-in dashboard session — great for CLI installers that want to
    hand the user a "click to view your workspace" link."""
    if not settings.clerk_secret_key:
        return None
    try:
        r = httpx.post(
            f"{CLERK_API}/sign_in_tokens",
            headers=_headers(),
            json={"user_id": clerk_user_id, "expires_in_seconds": expires_in_seconds},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        log.warning("clerk.mint_sign_in_token.network", user_id=clerk_user_id, err=str(exc))
        return None
    if r.status_code >= 400:
        log.warning(
            "clerk.mint_sign_in_token.failed",
            user_id=clerk_user_id, status=r.status_code, body=r.text[:200],
        )
        return None
    return r.json().get("url") or r.json().get("token")
