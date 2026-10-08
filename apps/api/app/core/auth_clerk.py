"""Clerk REST user lookups (split from app.core.auth; re-exported there)."""
from functools import lru_cache

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger("app.core.auth")

# ponytail: shared client — connection pooling, avoids per-call TLS handshake
_clerk_http = httpx.Client(timeout=5)


@lru_cache(maxsize=512)
def get_clerk_user_email(user_id: str) -> str | None:
    """Fetch the primary email address for a Clerk user via the Clerk REST API.

    Result is cached in-process (LRU, 512 entries) — email addresses rarely
    change and the cache is only invalidated by process restart.
    """
    if not settings.clerk_secret_key or not user_id:
        return None
    try:
        r = _clerk_http.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
        )
        if not r.is_success:
            return None
        data = r.json()
        primary_id = data.get("primary_email_address_id")
        for e in data.get("email_addresses", []):
            if e.get("id") == primary_id:
                return e.get("email_address")
        emails = data.get("email_addresses", [])
        return emails[0].get("email_address") if emails else None
    except Exception as e:
        log.warning("clerk.user_email_fetch_failed", user_id=user_id, error=str(e))
        return None


@lru_cache(maxsize=512)
def find_clerk_user_id_by_email(email: str) -> str | None:
    """Return the Clerk user_id for the given email, or None if not found."""
    if not settings.clerk_secret_key or not email:
        return None
    try:
        r = _clerk_http.get(
            "https://api.clerk.com/v1/users",
            params={"email_address": email, "limit": 1},
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
        )
        if not r.is_success:
            return None
        users = r.json()
        return users[0]["id"] if users else None
    except Exception as e:
        log.warning("clerk.user_search_by_email_failed", email=email, error=str(e))
        return None


@lru_cache(maxsize=512)
def get_clerk_user_info(user_id: str) -> dict:
    """Return {email, name} for a Clerk user. Falls back to empty strings on failure."""
    if not settings.clerk_secret_key or not user_id:
        return {"email": None, "name": None}
    try:
        r = _clerk_http.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
        )
        if not r.is_success:
            return {"email": None, "name": None}
        data = r.json()
        primary_id = data.get("primary_email_address_id")
        email = None
        for e in data.get("email_addresses", []):
            if e.get("id") == primary_id:
                email = e.get("email_address")
                break
        if not email:
            emails = data.get("email_addresses", [])
            email = emails[0].get("email_address") if emails else None
        first = data.get("first_name") or ""
        last = data.get("last_name") or ""
        name = f"{first} {last}".strip() or None
        return {"email": email, "name": name}
    except Exception as e:
        log.warning("clerk.user_info_fetch_failed", user_id=user_id, error=str(e))
        return {"email": None, "name": None}
