"""Vault env-var round-trip regression tests (#2054 Phase 1).

Every test hits the real FastAPI app through TestClient with a real Postgres
session, seeds a fresh workspace + environment, exercises the endpoint, and
asserts on the resulting DB rows.

Guardrails these tests defend:

- No-edit save preserves credential identity (the epic reproduction).
- Multi-field credentials keep untouched fields on a partial save.
- Canonical env-var name mapping still works for brand-new rows.
- Omitting a credential from the payload does NOT delete it.
- Explicit deletion refuses credentials referenced by Gateway / MCP / workflow.
- Concurrent edits reject stale revisions.
- Partial identity (handle without field or vice versa) is rejected.
- Duplicate targets in one payload are rejected.
- Cross-workspace writes are refused.
- Uppercase arbitrary env-var names round-trip without lowercasing.
- Clearing a field (value=None) leaves the row and other fields intact.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.regression.conftest import requires_db


pytestmark = requires_db


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


# ─── 1. No-edit round trip preserves custom handle (epic reproduction) ──


def test_no_edit_save_preserves_custom_handle(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "openai-primary", {"api_key": "sk-original"})

        # 1) List — client sees the row with its identity + revision.
        r = client.get(f"/credentials/env-vars/{env_id}?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["handle"] == "openai-primary"
        assert rows[0]["field"] == "api_key"
        assert rows[0]["value"] == "sk-original"
        assert rows[0]["revision"] == 1

        # 2) Save unchanged — client echoes identity + revision back.
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": rows[0]["key"],
                "value": rows[0]["value"],
                "handle": rows[0]["handle"],
                "field": rows[0]["field"],
                "expected_revision": rows[0]["revision"],
            }],
        )
        assert r.status_code == 200, r.text

        # 3) The original row is intact. No env_vars catch-all row created.
        original = _list_row(ws_id, env_id, "openai-primary")
        assert original is not None, "no-edit save destroyed the openai-primary row"
        assert _decrypted(original) == {"api_key": "sk-original"}
        assert original.revision == 2  # bumped even on no-value-change save

        catchall = _list_row(ws_id, env_id, "env_vars")
        assert catchall is None, "no-edit save leaked into env_vars catch-all"
    finally:
        _cleanup(ws_id, env_id)


# ─── 2. Multi-field credential preserves untouched fields ────────────────


def test_save_preserves_untouched_fields_on_multi_field_handle(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "git", {"token": "ghp_orig", "provider": "github"})

        # Payload only carries the `token` field — resave should not wipe `provider`.
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": "GITHUB_TOKEN",
                "value": "ghp_orig",
                "handle": "git",
                "field": "token",
                "expected_revision": 1,
            }],
        )
        assert r.status_code == 200, r.text

        row = _list_row(ws_id, env_id, "git")
        assert _decrypted(row) == {"token": "ghp_orig", "provider": "github"}
    finally:
        _cleanup(ws_id, env_id)


# ─── 3. Canonical alias mapping still works for brand-new rows ──────────


def test_slack_alias_normalization_still_works_for_new_rows(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{"key": "SLACK_TOKEN", "value": "xoxb-1"}],
        )
        assert r.status_code == 200, r.text

        row = _list_row(ws_id, env_id, "slack")
        assert row is not None
        assert _decrypted(row) == {"token": "xoxb-1"}
    finally:
        _cleanup(ws_id, env_id)


# ─── 4. Omitting a credential does NOT delete it ────────────────────────


def test_omitting_credential_does_not_delete_it(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-ant-original"})
        _seed_integration(ws_id, env_id, "openai", {"api_key": "sk-oai-original"})

        # Payload only touches openai — anthropic must survive.
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": "OPENAI_API_KEY",
                "value": "sk-oai-updated",
                "handle": "openai",
                "field": "api_key",
                "expected_revision": 1,
            }],
        )
        assert r.status_code == 200, r.text

        anth = _list_row(ws_id, env_id, "anthropic")
        assert anth is not None, "omission-based delete regression — anthropic vanished"
        assert _decrypted(anth) == {"api_key": "sk-ant-original"}
    finally:
        _cleanup(ws_id, env_id)


# ─── 5. Explicit deletion refuses referenced credentials ────────────────


def test_explicit_deletion_refuses_referenced_credential(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-ant"})

        # Seed a gateway_profile that references the credential.
        from app.core.database import SessionLocal
        from app.models.gateway_profile import GatewayProfile

        gp_id = uuid.uuid4()
        vault_ref = f"vault://{env_id}/anthropic"
        with SessionLocal() as db:
            db.add(GatewayProfile(
                id=gp_id,
                workspace_id=ws_id,
                environment_id=env_id,
                name="prod-profile",
                cond_code="testcode1",
                config={"targets": [{"credential_ref": vault_ref}]},
            ))
            db.commit()

        r = client.delete(
            f"/credentials/env-vars/{env_id}/handles/anthropic"
            f"?workspace_id={ws_id}&expected_revision=1",
        )
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["detail"]["code"] == "credential_referenced"
        assert "prod-profile" in body["detail"]["references"]["gateway_profiles"]

        # Row still exists.
        assert _list_row(ws_id, env_id, "anthropic") is not None

        # Cleanup: drop the profile before _cleanup runs.
        with SessionLocal() as db:
            db.query(GatewayProfile).filter(GatewayProfile.id == gp_id).delete()
            db.commit()
    finally:
        _cleanup(ws_id, env_id)


def test_explicit_deletion_with_force_true_deletes_referenced(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-ant"})

        from app.core.database import SessionLocal
        from app.models.gateway_profile import GatewayProfile

        gp_id = uuid.uuid4()
        vault_ref = f"vault://{env_id}/anthropic"
        with SessionLocal() as db:
            db.add(GatewayProfile(
                id=gp_id,
                workspace_id=ws_id,
                environment_id=env_id,
                name="prod-profile-force",
                cond_code="testcode2",
                config={"targets": [{"credential_ref": vault_ref}]},
            ))
            db.commit()

        r = client.delete(
            f"/credentials/env-vars/{env_id}/handles/anthropic"
            f"?workspace_id={ws_id}&expected_revision=1&force=true",
        )
        assert r.status_code == 200, r.text
        assert _list_row(ws_id, env_id, "anthropic") is None

        with SessionLocal() as db:
            db.query(GatewayProfile).filter(GatewayProfile.id == gp_id).delete()
            db.commit()
    finally:
        _cleanup(ws_id, env_id)


# ─── 6. Concurrent edits reject stale revision ──────────────────────────


def test_concurrent_edits_reject_stale_revision(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "linear", {"api_key": "lin-orig"})

        # First writer succeeds with revision=1 → bumps to 2.
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": "LINEAR_API_KEY", "value": "lin-writer-a",
                "handle": "linear", "field": "api_key", "expected_revision": 1,
            }],
        )
        assert r.status_code == 200, r.text

        # Second writer, still holding revision=1, must be refused.
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": "LINEAR_API_KEY", "value": "lin-writer-b",
                "handle": "linear", "field": "api_key", "expected_revision": 1,
            }],
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "stale_revision"
        assert r.json()["detail"]["current_revision"] == 2

        # Writer A's value stuck.
        assert _decrypted(_list_row(ws_id, env_id, "linear")) == {"api_key": "lin-writer-a"}
    finally:
        _cleanup(ws_id, env_id)


# ─── 7. Partial identity is rejected ────────────────────────────────────


def test_rejects_partial_identity(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{"key": "X", "value": "y", "handle": "openai"}],  # no field
        )
        assert r.status_code == 422, r.text
    finally:
        _cleanup(ws_id, env_id)


# ─── 8. Duplicate (handle, field) targets in one payload rejected ──────


def test_rejects_duplicate_handle_field_in_payload(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[
                {"key": "OPENAI_API_KEY", "value": "one", "handle": "openai", "field": "api_key"},
                {"key": "OPENAI_API_KEY", "value": "two", "handle": "openai", "field": "api_key"},
            ],
        )
        assert r.status_code == 422, r.text
        assert "duplicate target" in r.json()["detail"].lower()
    finally:
        _cleanup(ws_id, env_id)


# ─── 9. Cross-workspace writes refused ──────────────────────────────────


def test_rejects_cross_workspace_write(client, seeded_workspace):
    ws_id_a, _ta = seeded_workspace
    env_a = _seed_environment(ws_id_a)

    # Seed a second workspace + env that's NOT the caller's.
    from app.core.database import SessionLocal
    from app.models.workspace import Workspace
    from app.models.environment import Environment

    ws_id_b = uuid.uuid4()
    env_b = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Workspace(
            id=ws_id_b,
            name=f"cross-ws-{ws_id_b.hex[:8]}",
            owner_id=f"user_test_cross_{ws_id_b.hex[:8]}",
            plan="free",
            is_approved=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.add(Environment(id=env_b, workspace_id=ws_id_b, name="cross-env"))
        db.commit()

    try:
        # Caller identifies as ws_id_a but targets ws_id_b's environment.
        r = client.put(
            f"/credentials/env-vars/{env_b}?workspace_id={ws_id_a}",
            json=[{"key": "OPENAI_API_KEY", "value": "sk-oai"}],
        )
        assert r.status_code == 404, r.text
    finally:
        _cleanup(ws_id_a, env_a)
        with SessionLocal() as db:
            db.query(Environment).filter(Environment.id == env_b).delete()
            db.query(Workspace).filter(Workspace.id == ws_id_b).delete()
            db.commit()


# ─── 10. Uppercase arbitrary env-var name preserved ─────────────────────


def test_uppercase_arbitrary_env_var_name_preserved(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{"key": "MY_CUSTOM_VAR", "value": "42"}],
        )
        assert r.status_code == 200, r.text

        row = _list_row(ws_id, env_id, "env_vars")
        assert row is not None
        # Casing MUST survive round trip — the old fallback lowercased it.
        assert _decrypted(row) == {"MY_CUSTOM_VAR": "42"}

        # List returns the same casing back to the client.
        r = client.get(f"/credentials/env-vars/{env_id}?workspace_id={ws_id}")
        assert r.status_code == 200
        assert r.json()[0]["key"] == "MY_CUSTOM_VAR"
    finally:
        _cleanup(ws_id, env_id)


# ─── 11. Clearing a field leaves row + other fields intact ──────────────


def test_clear_field_leaves_row_and_other_fields_intact(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "git", {"token": "ghp", "provider": "github"})

        # value=None → clear only the `token` field.
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": "GITHUB_TOKEN", "value": None,
                "handle": "git", "field": "token", "expected_revision": 1,
            }],
        )
        assert r.status_code == 200, r.text

        row = _list_row(ws_id, env_id, "git")
        assert row is not None, "clear should not delete the row"
        assert _decrypted(row) == {"provider": "github"}
    finally:
        _cleanup(ws_id, env_id)
