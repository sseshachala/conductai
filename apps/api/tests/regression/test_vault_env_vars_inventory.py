"""#2054 Phase 3 — env_vars catch-all inventory endpoint.

Discovery-only. Every test seeds a workspace, injects a mix of env_vars
bag contents (with and without canonical mappings, with and without
collisions), calls the endpoint, and asserts on the metadata report.

Guardrails checked:
- No values leaked in the response.
- Fields with a mapping get a suggested_reroute.
- Fields without a mapping (custom vars) get suggested_reroute=None so
  the operator knows to leave them in the bag.
- Fields whose reroute would collide with an existing row are flagged
  with field_already_present so the operator knows which cases need
  manual resolution vs. a clean move.
- Cross-workspace rows never surface.
"""
from __future__ import annotations

import uuid

import pytest

from tests.regression.conftest import requires_db


pytestmark = requires_db


# ─── Seed helpers ────────────────────────────────────────────────────────


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


# ─── Tests ───────────────────────────────────────────────────────────────


def test_inventory_empty_when_no_env_vars_rows(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_env_vars_rows"] == 0
        assert body["environments"] == []
    finally:
        _cleanup(ws_id, env_id)


def test_inventory_lists_canonical_mapped_field_as_reroutable(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {
            "ANTHROPIC_API_KEY": "sk-anything",  # value never leaves the server
        })
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_env_vars_rows"] == 1
        assert body["reroutable_field_count"] == 1
        env = body["environments"][0]
        row = env["env_vars_rows"][0]
        f0 = row["fields"][0]
        assert f0["name"] == "ANTHROPIC_API_KEY"
        assert f0["suggested_reroute"] == {"handle": "anthropic", "field": "api_key"}
        assert f0["collision"] is None
    finally:
        _cleanup(ws_id, env_id)


def test_inventory_leaves_custom_variables_alone(client, seeded_workspace):
    """The epic explicitly warns against blindly unpacking every row — a
    variable with no canonical mapping (a user's own env var) should be
    reported as unreroutable so it stays in the ``env_vars`` bag."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {"MY_CUSTOM_VAR": "42"})
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["unreroutable_field_count"] == 1
        assert body["reroutable_field_count"] == 0
        f = body["environments"][0]["env_vars_rows"][0]["fields"][0]
        assert f["name"] == "MY_CUSTOM_VAR"
        assert f["suggested_reroute"] is None
    finally:
        _cleanup(ws_id, env_id)


def test_inventory_flags_collision_when_target_handle_already_has_field(
    client, seeded_workspace,
):
    """The classic P1 shape: an ``env_vars`` bag holds an ANTHROPIC_API_KEY
    while a real openai row already has ``api_key`` populated. Migration
    can't silently overwrite — the report must flag this."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {"ANTHROPIC_API_KEY": "sk-bag"})
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-canonical"})
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["collision_count"] == 1
        assert body["reroutable_field_count"] == 0
        f = body["environments"][0]["env_vars_rows"][0]["fields"][0]
        assert f["collision"] is not None
        assert f["collision"]["handle"] == "anthropic"
        assert f["collision"]["field"] == "api_key"
        assert f["collision"]["field_already_present"] is True
    finally:
        _cleanup(ws_id, env_id)


def test_inventory_soft_collision_when_target_handle_exists_but_field_free(
    client, seeded_workspace,
):
    """An openai row already exists but doesn't have api_key populated.
    Report still flags the row-level collision so the operator knows the
    reroute lands into an existing bucket (not a clean create), but
    marks field_already_present=False so they can distinguish safe merge
    from destructive overwrite."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {"ANTHROPIC_API_KEY": "sk-bag"})
        _seed_integration(ws_id, env_id, "anthropic", {"organization": "org-only"})
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        f = body["environments"][0]["env_vars_rows"][0]["fields"][0]
        assert f["collision"] is not None
        assert f["collision"]["field_already_present"] is False
    finally:
        _cleanup(ws_id, env_id)


def test_inventory_does_not_leak_credential_values(client, seeded_workspace):
    """Sanity: the response body must never contain any credential value."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {
            "ANTHROPIC_API_KEY": "sk-should-never-appear-in-body",
            "MY_CUSTOM_VAR": "42-also-secret",
        })
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        raw = r.text
        assert "sk-should-never-appear-in-body" not in raw
        assert "42-also-secret" not in raw
    finally:
        _cleanup(ws_id, env_id)


def test_inventory_isolates_by_workspace(client, seeded_workspace):
    """A separate workspace's env_vars rows must never appear in the caller's
    inventory even though we know their env_id."""
    ws_a, _t = seeded_workspace
    env_a = _seed_environment(ws_a)

    from datetime import datetime, timezone
    from app.core.database import SessionLocal
    from app.models.workspace import Workspace
    from app.models.environment import Environment

    ws_b = uuid.uuid4()
    env_b = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Workspace(
            id=ws_b,
            name=f"cross-{ws_b.hex[:8]}",
            owner_id=f"user_test_cross_{ws_b.hex[:8]}",
            plan="free",
            is_approved=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.add(Environment(id=env_b, workspace_id=ws_b, name="cross-env"))
        db.commit()

    try:
        _seed_integration(ws_b, env_b, "env_vars", {"ANTHROPIC_API_KEY": "sk-other"})
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_a}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_env_vars_rows"] == 0
    finally:
        _cleanup(ws_a, env_a)
        with SessionLocal() as db:
            from app.models.integration import Integration
            db.query(Integration).filter(Integration.workspace_id == ws_b).delete()
            db.query(Environment).filter(Environment.id == env_b).delete()
            db.query(Workspace).filter(Workspace.id == ws_b).delete()
            db.commit()
