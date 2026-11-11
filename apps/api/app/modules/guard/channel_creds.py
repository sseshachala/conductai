"""Vault-backed notification channels.

PagerDuty, webhook and email channels point at a Vault entry
(``Integration`` row) through ``guard_notification_channels.integration_id``
instead of carrying a secret in ``channel_ref``. The credential is resolved at
send time, so rotating it in the Vault updates every channel that references it.

Vault field names per service:

* ``pagerduty`` -> ``routing_key``
* ``webhook``   -> ``url`` (+ optional ``signing_secret``)
* ``email``     -> ``resend_api_key`` / ``sendgrid_api_key`` (existing service)

Legacy rows (a raw key/URL in ``channel_ref`` and no ``integration_id``) keep
working unchanged. Secrets are never returned by the API: ``public_ref`` masks
legacy refs and vault-backed rows only expose a non-secret label.

Webhook signing: when the Vault entry has ``signing_secret`` the request carries
``X-Conduct-Signature: t=<unix ts>,v1=<hex>`` where ``v1`` is
HMAC-SHA256(secret, ``"<ts>.<raw body>"``).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import uuid as _uuid
from urllib.parse import urlparse

import structlog
from fastapi import HTTPException

log = structlog.get_logger(__name__)

SIGNATURE_HEADER = "X-Conduct-Signature"
# channel_type -> Vault service it may reference. Slack keeps its own path.
VAULT_SERVICES = {"pagerduty": "pagerduty", "webhook": "webhook", "email": "email"}
_PD_KEY_RE = re.compile(r"^[A-Za-z0-9]{32}$")


def pagerduty_key_shape_ok(key: str) -> bool:
    """PagerDuty Events v2 routing keys are 32 alphanumeric characters."""
    return bool(_PD_KEY_RE.match((key or "").strip()))


def sign_webhook_body(secret: str, body: bytes, ts: int | None = None) -> str:
    """Return the ``X-Conduct-Signature`` header value for ``body``."""
    stamp = int(time.time()) if ts is None else int(ts)
    mac = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={mac}"


def json_body(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), default=str).encode()


def _load_integration(db, workspace_id, integration_id):
    from app.models.integration import Integration

    try:
        iid = integration_id if isinstance(integration_id, _uuid.UUID) else _uuid.UUID(str(integration_id))
    except (ValueError, TypeError):
        return None
    return db.query(Integration).filter(
        Integration.id == iid, Integration.workspace_id == workspace_id,
    ).first()


def vault_credentials(db, workspace_id, integration_id, service: str) -> dict:
    """Decrypt the referenced Vault entry. ``{}`` when missing/mismatched/empty."""
    if db is None or not integration_id:
        return {}
    try:
        from app.core.crypto import decrypt

        row = _load_integration(db, workspace_id, integration_id)
        if row is None or row.service != service or not row.encrypted_credentials:
            return {}
        return decrypt(row.encrypted_credentials) or {}
    except Exception as exc:  # log the type only, never the blob
        log.warning("guard.channel_creds.resolve_failed", err=type(exc).__name__)
        return {}


def _context(db, workspace_id, channel):
    """Fall back to the channel row's own session/workspace so callers that do
    not thread ``db`` through still resolve Vault entries."""
    if db is None:
        from sqlalchemy.orm import object_session

        db = object_session(channel)
    return db, (workspace_id or getattr(channel, "workspace_id", None))


def pagerduty_routing_key(db, workspace_id, channel) -> str:
    """Vault routing key if the channel has an entry, else the legacy raw ref."""
    iid = getattr(channel, "integration_id", None)
    if iid:
        db, workspace_id = _context(db, workspace_id, channel)
        return str(vault_credentials(db, workspace_id, iid, "pagerduty").get("routing_key") or "").strip()
    return (getattr(channel, "channel_ref", "") or "").strip()


def webhook_target(db, workspace_id, channel) -> tuple[str, str | None]:
    """(url, signing_secret) for a webhook channel; url ``""`` if unresolvable."""
    iid = getattr(channel, "integration_id", None)
    if iid:
        db, workspace_id = _context(db, workspace_id, channel)
        creds = vault_credentials(db, workspace_id, iid, "webhook")
        return str(creds.get("url") or "").strip(), (creds.get("signing_secret") or None)
    return (getattr(channel, "channel_ref", "") or "").strip(), None


# ── Save-time validation ─────────────────────────────────────────────────────

def prepare_channel_ref(db, workspace_id, channel_type: str, integration_id, channel_ref: str | None) -> str:
    """Validate a channel binding and return the ``channel_ref`` to store.

    Raises HTTPException 422 on an unusable combination. ``integration_id`` is
    already a UUID (or None).
    """
    from app.modules.guard.routers.notifications import _check_webhook_ref

    ref = (channel_ref or "").strip()
    if channel_type in ("slack", "email") and not ref:
        raise HTTPException(status_code=422, detail="channel_ref is required")

    if channel_type == "slack" and integration_id:
        row = _load_integration(db, workspace_id, integration_id)
        if row is None or row.service != "slack":
            raise HTTPException(
                status_code=422,
                detail="integration_id must be a slack Vault entry in this workspace",
            )

    if channel_type in VAULT_SERVICES and integration_id:
        service = VAULT_SERVICES[channel_type]
        row = _load_integration(db, workspace_id, integration_id)
        if row is None or row.service != service:
            raise HTTPException(
                status_code=422,
                detail=f"integration_id must be a {service} Vault entry in this workspace",
            )
        if channel_type == "email":
            return ref  # the recipient address
        if channel_type == "webhook":
            url = str(vault_credentials(db, workspace_id, row.id, "webhook").get("url") or "").strip()
            if not url:
                raise HTTPException(status_code=422, detail="Vault webhook entry has no URL")
            _check_webhook_ref("webhook", url)
        return f"vault:{row.handle}"[:200]

    if channel_type in ("pagerduty", "webhook"):
        if not ref:
            raise HTTPException(
                status_code=422,
                detail=f"pick a {channel_type} Vault entry (integration_id) or provide channel_ref",
            )
        _check_webhook_ref(channel_type, ref)
    return ref


# ── Response shaping (never return secrets) ──────────────────────────────────

def public_ref(channel_type: str, channel_ref: str, integration_id) -> str:
    """The ref safe to return from the API."""
    if channel_type == "pagerduty" and not integration_id:
        r = channel_ref or ""
        return f"{r[:4]}…{r[-4:]}" if len(r) > 8 else "…"
    if channel_type == "webhook" and not integration_id:
        try:
            p = urlparse(channel_ref)
            return f"{p.scheme}://{p.hostname}/…" if p.hostname else "webhook"
        except ValueError:
            return "webhook"
    return channel_ref


def vault_info(db, rows) -> dict[str, dict]:
    """integration_id -> {handle, service, environment_id, environment_name}."""
    from app.models.environment import Environment
    from app.models.integration import Integration

    ids = {r.integration_id for r in rows if getattr(r, "integration_id", None)}
    if not ids:
        return {}
    integs = db.query(Integration).filter(Integration.id.in_(ids)).all()
    env_ids = {i.environment_id for i in integs if i.environment_id}
    names: dict = {}
    if env_ids:
        names = {e.id: e.name for e in db.query(Environment).filter(Environment.id.in_(env_ids)).all()}
    return {
        str(i.id): {
            "handle": i.handle,
            "service": i.service,
            "environment_id": str(i.environment_id) if i.environment_id else None,
            "environment_name": names.get(i.environment_id) if i.environment_id else None,
        }
        for i in integs
    }


def serialize_extras(row, info: dict[str, dict]) -> dict:
    """Common response fields: masked ref + Vault provenance + legacy flag."""
    iid = str(row.integration_id) if row.integration_id else None
    v = info.get(iid) if iid else None
    return {
        "channel_ref": public_ref(row.channel_type, row.channel_ref, row.integration_id),
        "vault_handle": v["handle"] if v else None,
        "environment_id": v["environment_id"] if v else None,
        "environment_name": v["environment_name"] if v else None,
        # A typed secret/URL still lives on the row (pagerduty/webhook only).
        "legacy_ref": row.channel_type in ("pagerduty", "webhook") and not row.integration_id,
    }
