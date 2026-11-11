"""Move a legacy typed key/URL on a notification channel into the Vault.

A legacy PagerDuty / webhook row keeps its raw routing key or URL in
``channel_ref`` with no ``integration_id``. ``move_to_vault`` encrypts that
value into a Vault ``Integration`` of the right service (server-side, so the
secret never round-trips through the browser) and rebinds the row to
``vault:<handle>`` in the caller's transaction. An identical entry already in
the environment is reused instead of duplicated.

Callers own the commit. The raw value is never logged, audited or returned.
"""
from __future__ import annotations

import hashlib
import re
import uuid as _uuid

import structlog
from fastapi import HTTPException

from app.core.crypto import decrypt, encrypt
from app.models.audit_log import AuditLog
from app.models.integration import Integration
from app.modules.guard.channel_creds import VAULT_SERVICES
from app.modules.guard.models import GuardNotificationChannel

log = structlog.get_logger(__name__)

_HANDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
# channel_type -> Vault field that holds the legacy raw value
_FIELD = {"pagerduty": "routing_key", "webhook": "url"}
AUDIT_ACTION = "guard.channel.moved_to_vault"


def is_legacy(row: GuardNotificationChannel) -> bool:
    return (
        row.channel_type in _FIELD
        and not row.integration_id
        and bool((row.channel_ref or "").strip())
        and not (row.channel_ref or "").startswith("vault:")
    )


def auto_handle(channel_type: str, secret: str) -> str:
    """Deterministic handle for bulk moves; derived from a hash, not the secret."""
    return f"{channel_type}-{hashlib.sha256(secret.encode()).hexdigest()[:8]}"


def _same(blob: str | None, fields: dict) -> bool:
    try:
        return bool(blob) and (decrypt(blob) or {}) == fields
    except Exception:
        return False


def move_to_vault(
    db,
    workspace_id,
    row: GuardNotificationChannel,
    environment_id,
    handle: str,
    *,
    actor_id: str | None,
) -> Integration:
    """Create/reuse the Vault entry and rebind ``row``. No commit."""
    from app.models.environment import Environment
    from app.modules.guard.routers.notifications import _check_webhook_ref

    if not is_legacy(row):
        raise HTTPException(status_code=409, detail="channel has no typed key to move")
    handle = (handle or "").strip()
    if not _HANDLE_RE.match(handle):
        raise HTTPException(status_code=422, detail="handle must be 1-100 chars: letters, digits, '.', '_' or '-'")
    try:
        env_id = environment_id if isinstance(environment_id, _uuid.UUID) else _uuid.UUID(str(environment_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="invalid environment_id")
    env = db.query(Environment).filter(Environment.id == env_id, Environment.workspace_id == workspace_id).first()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    service = VAULT_SERVICES[row.channel_type]
    secret = row.channel_ref.strip()
    if row.channel_type == "webhook":
        _check_webhook_ref("webhook", secret)  # 422 on non-public / non-https
    fields = {_FIELD[row.channel_type]: secret}

    candidates = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == env_id,
        Integration.service == service,
    ).order_by(Integration.created_at.asc()).all()
    entry = next((i for i in candidates if _same(i.encrypted_credentials, fields)), None)
    reused = entry is not None
    if entry is None:
        taken = db.query(Integration.id).filter(
            Integration.workspace_id == workspace_id,
            Integration.environment_id == env_id,
            Integration.handle == handle,
        ).first()
        if taken:
            raise HTTPException(status_code=409, detail=f"handle '{handle}' is already used in this environment")
        entry = Integration(
            workspace_id=workspace_id, environment_id=env_id, service=service, handle=handle,
            auth_method="api_key", encrypted_credentials=encrypt(fields), revision=1,
        )
        db.add(entry)
        db.flush()

    row.integration_id = entry.id
    row.channel_ref = f"vault:{entry.handle}"[:200]
    db.add(AuditLog(
        workspace_id=workspace_id, actor_id=actor_id, action=AUDIT_ACTION,
        resource_type="notification_channel", resource_id=str(row.id),
        meta={
            "channel_type": row.channel_type, "integration_id": str(entry.id),
            "handle": entry.handle, "environment_id": str(env_id), "reused_entry": reused,
        },
    ))
    log.info("guard.channel.moved_to_vault", channel_type=row.channel_type, reused=reused)
    return entry


def move_all_to_vault(db, workspace_id, environment_id, *, actor_id: str | None) -> dict:
    """Move every legacy row in the workspace; one savepoint per row.

    Rows that fail validation (e.g. egress-refused webhook) are skipped and
    reported by id with a reason that never includes the value.
    """
    rows = db.query(GuardNotificationChannel).filter(
        GuardNotificationChannel.workspace_id == workspace_id,
        GuardNotificationChannel.channel_type.in_(list(_FIELD)),
        GuardNotificationChannel.integration_id.is_(None),
    ).all()
    moved: list[str] = []
    skipped: list[dict] = []
    for row in rows:
        if not is_legacy(row):
            continue
        handle = auto_handle(row.channel_type, row.channel_ref.strip())
        try:
            with db.begin_nested():
                move_to_vault(db, workspace_id, row, environment_id, handle, actor_id=actor_id)
            moved.append(str(row.id))
        except HTTPException as exc:
            if exc.status_code == 404:  # bad environment applies to every row
                raise
            skipped.append({"id": str(row.id), "reason": str(exc.detail)})
    return {"moved": moved, "skipped": skipped}
