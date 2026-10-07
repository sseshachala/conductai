"""Shared seed / cleanup / decrypt helpers for the vault env-var
round-trip regression tests (``test_vault_env_vars_roundtrip*.py``).
"""
from __future__ import annotations

import uuid

# ─── Helpers ──────────────────────────────────────────────────────────


def _seed_environment(workspace_id: uuid.UUID) -> uuid.UUID:
    from app.core.database import SessionLocal
    from app.models.environment import Environment

    env_id = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Environment(
            id=env_id,
            workspace_id=workspace_id,
            name=f"chaos-{env_id.hex[:8]}",
        ))
        db.commit()
    return env_id


def _seed_integration(
    workspace_id: uuid.UUID,
    env_id: uuid.UUID,
    handle: str,
    fields: dict[str, str],
    *,
    service: str | None = None,
) -> uuid.UUID:
    from app.core.crypto import encrypt
    from app.core.database import SessionLocal
    from app.models.integration import Integration

    row_id = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Integration(
            id=row_id,
            workspace_id=workspace_id,
            environment_id=env_id,
            service=service or handle,
            handle=handle,
            auth_method="api_key",
            encrypted_credentials=encrypt(fields),
            revision=1,
        ))
        db.commit()
    return row_id


def _cleanup(workspace_id: uuid.UUID, env_id: uuid.UUID) -> None:
    from app.core.database import SessionLocal
    from app.models.environment import Environment
    from app.models.integration import Integration

    with SessionLocal() as db:
        db.query(Integration).filter(Integration.workspace_id == workspace_id).delete()
        db.query(Environment).filter(Environment.id == env_id).delete()
        db.commit()


def _list_row(workspace_id: uuid.UUID, env_id: uuid.UUID, handle: str):
    from app.core.database import SessionLocal
    from app.models.integration import Integration

    with SessionLocal() as db:
        return db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.environment_id == env_id,
            Integration.handle == handle,
        ).first()


def _decrypted(row) -> dict[str, str]:
    from app.core.crypto import decrypt
    if not row or not row.encrypted_credentials:
        return {}
    return decrypt(row.encrypted_credentials)


def _list_with_reveal(client, workspace_id, env_id):
    """Test helper: list metadata + reveal each field. Used by older
    "no-edit save" tests that were written against the pre-audit list
    response; new tests should call the reveal endpoint explicitly."""
    r = client.get(f"/credentials/env-vars/{env_id}?workspace_id={workspace_id}")
    assert r.status_code == 200, r.text
    rows = []
    for meta in r.json():
        if meta.get("unreadable"):
            continue
        rr = client.post(
            f"/credentials/env-vars/{env_id}/reveal?workspace_id={workspace_id}",
            json={"handle": meta["handle"], "field": meta["field"]},
        )
        assert rr.status_code == 200, rr.text
        rows.append({**meta, "value": rr.json()["value"]})
    return rows
