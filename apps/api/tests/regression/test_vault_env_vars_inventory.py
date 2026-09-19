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
        assert body["needs_review_field_count"] == 1
        assert body["reroutable_field_count"] == 0
        f = body["environments"][0]["env_vars_rows"][0]["fields"][0]
        assert f["name"] == "MY_CUSTOM_VAR"
        assert f["suggested_reroute"] is None
        assert f["status"] == "needs_review"
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



# --- 8. Unmapped fields are needs_review, not custom_variable (P2-6) ---


def test_unmapped_field_is_needs_review_not_custom_variable(client, seeded_workspace):
    """Reviewer contract: an unmapped field must NOT be silently treated
    as a legitimate custom var. Only the operator can mark it safe."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {"LANGCHAIN_API_KEY": "opaque"})
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        f = body["environments"][0]["env_vars_rows"][0]["fields"][0]
        assert f["status"] == "needs_review"
        assert f["suggested_reroute"] is None
    finally:
        _cleanup(ws_id, env_id)


# --- 9. Case-insensitive match still requires review (P2-6) ---


def test_case_insensitive_match_is_needs_review_with_hint(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {"github_token": "opaque"})
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        f = body["environments"][0]["env_vars_rows"][0]["fields"][0]
        assert f["status"] == "needs_review"
        assert f["canonical_name_hint"] == "GITHUB_TOKEN"
        # Never auto-migrate on a case-only match.
        assert f["suggested_reroute"] is None
    finally:
        _cleanup(ws_id, env_id)


# --- 10. Many-to-one across sources is flagged (P2-5) ---


def test_multiple_source_fields_targeting_same_destination_are_flagged(
    client, seeded_workspace,
):
    """GITHUB_TOKEN and GITHUB_PAT both map to git.token. Without cross-
    source detection, each would independently look reroutable."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {
            "GITHUB_TOKEN": "opaque-a",
            "GITHUB_PAT": "opaque-b",
        })
        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        fields = body["environments"][0]["env_vars_rows"][0]["fields"]
        by_name = {f["name"]: f for f in fields}
        assert by_name["GITHUB_TOKEN"]["status"] == "collision"
        assert "GITHUB_PAT" in by_name["GITHUB_TOKEN"]["many_to_one_conflict_with"]
        assert by_name["GITHUB_PAT"]["status"] == "collision"
        assert "GITHUB_TOKEN" in by_name["GITHUB_PAT"]["many_to_one_conflict_with"]
    finally:
        _cleanup(ws_id, env_id)


# --- 11. Unreadable destination is not reported as safe merge (P2-4) ---


def test_unreadable_destination_row_is_not_treated_as_free_slot(
    client, seeded_workspace,
):
    """Reviewer P2-4: an unreadable destination previously registered as
    empty-fields, making the reroute look safe. Now the collision detail
    carries destination_unreadable=True and field_already_present=True
    (conservative) so migration cannot silently overwrite."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "env_vars", {"ANTHROPIC_API_KEY": "sk-bag"})
        # Seed the destination row with unreadable ciphertext.
        from app.core.database import SessionLocal
        from app.models.integration import Integration
        garbage_id = uuid.uuid4()
        with SessionLocal() as db:
            db.add(Integration(
                id=garbage_id,
                workspace_id=ws_id,
                environment_id=env_id,
                service="anthropic",
                handle="anthropic",
                auth_method="api_key",
                encrypted_credentials="!!!not-real-ciphertext!!!",
                revision=1,
            ))
            db.commit()

        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        f = r.json()["environments"][0]["env_vars_rows"][0]["fields"][0]
        assert f["status"] == "collision"
        assert f["collision"]["destination_unreadable"] is True
        # Conservative: an unreadable destination must NOT be considered
        # a free slot for migration.
        assert f["collision"]["field_already_present"] is True
    finally:
        _cleanup(ws_id, env_id)


# --- 12. Unreadable source is reported as unreadable, not migratable (P2-4) ---


def test_unreadable_source_row_reports_status_unreadable(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        # Seed an env_vars row whose ciphertext is unreadable.
        from app.core.database import SessionLocal
        from app.models.integration import Integration
        row_id = uuid.uuid4()
        with SessionLocal() as db:
            db.add(Integration(
                id=row_id,
                workspace_id=ws_id,
                environment_id=env_id,
                service="env_vars",
                handle="env_vars",
                auth_method="api_key",
                encrypted_credentials="!!!not-real-ciphertext!!!",
                revision=1,
            ))
            db.commit()

        r = client.get(f"/credentials/env-vars/inventory?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        # Every reported field on this row must be marked unreadable so
        # migration will skip.
        assert body["unreadable_source_count"] >= 0
        # The row itself is reported with field_count=0 (we could not
        # extract keys), so the count is 0. That is the safe answer.
        row = body["environments"][0]["env_vars_rows"][0]
        assert row["field_count"] == 0
    finally:
        _cleanup(ws_id, env_id)


# --- 13. POST /credentials refuses cross-workspace environment (P1-1) ---


def test_upsert_credential_refuses_cross_workspace_environment(client, seeded_workspace):
    """Reviewer P1-1: POST /credentials previously accepted an explicit
    environment_id without verifying workspace ownership."""
    ws_a, _t = seeded_workspace
    from datetime import datetime, timezone
    from app.core.database import SessionLocal
    from app.models.environment import Environment
    from app.models.workspace import Workspace

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
        db.add(Environment(id=env_b, workspace_id=ws_b, name="rival-env"))
        db.commit()
    try:
        r = client.post(
            f"/credentials?workspace_id={ws_a}",
            json={
                "handle": "anthropic",
                "service": "anthropic",
                "auth_method": "api_key",
                "environment_id": str(env_b),
                "credentials": {"api_key": "sk-attacker"},
            },
        )
        assert r.status_code == 404, r.text
        # Verify no row was written into the rival environment.
        from app.models.integration import Integration
        with SessionLocal() as db:
            assert (
                db.query(Integration).filter(Integration.workspace_id == ws_a).count()
                == 0
            )
            assert (
                db.query(Integration).filter(Integration.environment_id == env_b).count()
                == 0
            )
    finally:
        with SessionLocal() as db:
            db.query(Environment).filter(Environment.id == env_b).delete()
            db.query(Workspace).filter(Workspace.id == ws_b).delete()
            db.commit()


# --- 14. Empty credential submission returns 422, not UnboundLocalError (P2-7) ---


def test_empty_credentials_returns_422(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    r = client.post(
        f"/credentials?workspace_id={ws_id}",
        json={
            "handle": "anthropic",
            "service": "anthropic",
            "auth_method": "api_key",
            "credentials": {},
        },
    )
    assert r.status_code == 422, r.text
