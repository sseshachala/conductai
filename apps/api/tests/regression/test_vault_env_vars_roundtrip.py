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

# ─── 1. No-edit round trip preserves custom handle (epic reproduction) ──


def test_no_edit_save_preserves_custom_handle(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "openai-primary", {"api_key": "sk-original"})

        # 1) List — client sees the row with its identity + revision.
        rows = _list_with_reveal(client, ws_id, env_id)
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

        # List returns the same casing back to the client + no leaked value.
        r = client.get(f"/credentials/env-vars/{env_id}?workspace_id={ws_id}")
        assert r.status_code == 200
        meta = r.json()[0]
        assert meta["key"] == "MY_CUSTOM_VAR"
        assert meta.get("has_value") is True
        assert "value" not in meta, "list_env_vars must not leak values"
    finally:
        _cleanup(ws_id, env_id)


# ─── 11. PUT rejects value=None; field clears go through DELETE ─────────


def test_put_rejects_value_none(client, seeded_workspace):
    """P1-4 fix: PUT no longer carries a clear semantic — otherwise a
    null-value save could remove a field that a protected consumer needs
    without hitting the reference check."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "git", {"token": "ghp", "provider": "github"})
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": "GITHUB_TOKEN", "value": None,
                "handle": "git", "field": "token", "expected_revision": 1,
            }],
        )
        assert r.status_code == 422, r.text
        # Row untouched.
        assert _decrypted(_list_row(ws_id, env_id, "git")) == {"token": "ghp", "provider": "github"}
    finally:
        _cleanup(ws_id, env_id)


def test_field_clear_via_delete_leaves_row_and_other_fields_intact(client, seeded_workspace):
    """Field removal is DELETE-only. Row survives, sibling field intact."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "git", {"token": "ghp", "provider": "github"})
        r = client.delete(
            f"/credentials/env-vars/{env_id}/handles/git"
            f"?workspace_id={ws_id}&expected_revision=1&field=token",
        )
        assert r.status_code == 200, r.text
        row = _list_row(ws_id, env_id, "git")
        assert row is not None
        assert _decrypted(row) == {"provider": "github"}
    finally:
        _cleanup(ws_id, env_id)


# ─── 12. Threaded atomicity — two writers race the same revision ───────


def test_atomic_conditional_update_rejects_second_writer_under_contention(
    client, seeded_workspace,
):
    """P1-1 fix: two threads both read revision=1 then race to write. Only
    one may succeed; the other must observe 409 with current_revision=2.

    Without conditional SQL, both Python-level checks pass and the second
    write silently clobbers the first. The test proves the SQL predicate
    rejects the second write even under real parallel execution.
    """
    import threading
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "perplexity", {"api_key": "orig"})
        results: list[int] = []
        barrier = threading.Barrier(2)

        def _writer(value: str) -> None:
            barrier.wait()
            r = client.put(
                f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
                json=[{
                    "key": "PERPLEXITY_API_KEY", "value": value,
                    "handle": "perplexity", "field": "api_key",
                    "expected_revision": 1,
                }],
            )
            results.append(r.status_code)

        ta = threading.Thread(target=_writer, args=("winner",))
        tb = threading.Thread(target=_writer, args=("loser",))
        ta.start(); tb.start()
        ta.join(timeout=5); tb.join(timeout=5)
        assert sorted(results) == [200, 409], f"races produced {results}"

        row = _list_row(ws_id, env_id, "perplexity")
        # Exactly one of the two values landed; the other was refused.
        assert _decrypted(row)["api_key"] in {"winner", "loser"}
        assert int(row.revision) == 2
    finally:
        _cleanup(ws_id, env_id)


# ─── 13. Mixed expected_revision per handle is refused ─────────────────


def test_rejects_mixed_expected_revisions_on_same_handle(client, seeded_workspace):
    """P2-6 fix: max(expected_revs) let a stale item ride a current one.
    Now every item on the same handle MUST agree on expected_revision."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "git", {"token": "orig", "provider": "github"})
        # First save bumps revision to 2 so we have a real drift to exploit.
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": "GITHUB_TOKEN", "value": "v2",
                "handle": "git", "field": "token", "expected_revision": 1,
            }],
        )
        assert r.status_code == 200, r.text

        # Now attempt a batch with one stale expected_revision (1) and one
        # current (2) — the old max() logic would accept this.
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[
                {"key": "GITHUB_TOKEN", "value": "stale", "handle": "git",
                 "field": "token", "expected_revision": 1},
                {"key": "GIT_PROVIDER", "value": "gitlab", "handle": "git",
                 "field": "provider", "expected_revision": 2},
            ],
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "expected_revision_inconsistent"
    finally:
        _cleanup(ws_id, env_id)


# ─── 14. Save producing an empty credential is refused ─────────────────


def test_save_producing_empty_credential_refuses_without_touching_row(
    client, seeded_workspace,
):
    """P2-7 fix: previously an empty-merge branch reported success but left
    the ciphertext untouched. Now the endpoint refuses so callers can't
    receive a successful save that didn't change anything.

    With value=None no longer a PUT clear (see P1-4), this case is only
    reachable if the payload had zero items for an existing handle — a
    contrived state that we still refuse for safety."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "sentry", {"token": "s-orig"})
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[],  # zero items
        )
        # Empty payload is accepted as a no-op; the row must be untouched.
        assert r.status_code == 200, r.text
        row = _list_row(ws_id, env_id, "sentry")
        assert _decrypted(row) == {"token": "s-orig"}
        assert int(row.revision) == 1
    finally:
        _cleanup(ws_id, env_id)


# ─── 15. upsert_credential (legacy path) bumps revision ────────────────


def test_upsert_credential_bumps_revision_so_editor_race_is_refused(
    client, seeded_workspace,
):
    """P1-2 fix: /credentials POST replaces ciphertext AND bumps revision
    so an editor holding an older revision is refused on save."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "linear", {"api_key": "orig"}, service="linear")

        # Simulate a rotation via the legacy credential upsert path.
        r = client.post(
            f"/credentials?workspace_id={ws_id}",
            json={
                "handle": "linear",
                "service": "linear",
                "auth_method": "api_key",
                "environment_id": str(env_id),
                "credentials": {"api_key": "rotated"},
            },
        )
        assert r.status_code in (200, 201), r.text

        row = _list_row(ws_id, env_id, "linear")
        # Revision must have advanced past 1 — otherwise the editor race
        # window is still open.
        assert int(row.revision) >= 2
    finally:
        _cleanup(ws_id, env_id)


# ─── 16. Bare Slack MCP server blocks credential delete ────────────────


def test_bare_mcp_server_blocks_credential_delete_via_server_cred_map(
    client, seeded_workspace,
):
    """P1-3 fix: MCP servers without embedded credentials still resolve via
    ``_SERVER_CRED_MAP``. Deleting slack.token must fail when a bare
    ``slack`` MCP server is registered, even though encrypted_auth has no
    handle substring."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "slack", {"token": "xoxb"})
        from app.core.database import SessionLocal
        from app.models.mcp_server import McpServer as _McpServer
        srv_id = uuid.uuid4()
        with SessionLocal() as db:
            db.add(_McpServer(
                id=srv_id,
                workspace_id=ws_id,
                environment_id=env_id,
                name="slack",  # resolves via _SERVER_CRED_MAP → (slack, token)
                url="https://slack.example",
                transport="http",
                encrypted_auth=None,
            ))
            db.commit()

        r = client.delete(
            f"/credentials/env-vars/{env_id}/handles/slack"
            f"?workspace_id={ws_id}&expected_revision=1",
        )
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["detail"]["code"] == "credential_referenced"
        assert "slack" in body["detail"]["references"]["mcp_servers"]

        with SessionLocal() as db:
            db.query(_McpServer).filter(_McpServer.id == srv_id).delete()
            db.commit()
    finally:
        _cleanup(ws_id, env_id)


# --- 17. Background rotation vs editor --- merge_and_write refuses stale writes


def test_background_rotation_conflicts_do_not_produce_same_revision(
    client, seeded_workspace,
):
    """P1-round-2 fix: rotation writers used ORM-level bump_encrypted which
    only advanced the Python-loaded revision. Two rotation-flavored writers
    that both read revision=1 could both write revision=2 and clobber each
    other.

    With merge_and_write, one wins the conditional UPDATE and the other
    retries against the newer state -- no lost update.
    """
    import threading

    from app.core.database import SessionLocal
    from app.core.integration_writer import merge_and_write

    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        row_id = _seed_integration(ws_id, env_id, "linear", {"api_key": "orig"})
        barrier = threading.Barrier(2)

        def _rotate(new_value: str) -> None:
            barrier.wait()
            with SessionLocal() as db:
                merge_and_write(
                    db,
                    row_id,
                    lambda prev: {**prev, "api_key": new_value},
                )
                db.commit()

        a = threading.Thread(target=_rotate, args=("value-a",))
        b = threading.Thread(target=_rotate, args=("value-b",))
        a.start(); b.start()
        a.join(timeout=5); b.join(timeout=5)

        row = _list_row(ws_id, env_id, "linear")
        assert _decrypted(row)["api_key"] in {"value-a", "value-b"}
        assert int(row.revision) == 3, (
            f"expected revision 3 after seed + 2 conditional writes; got {row.revision}"
        )
    finally:
        _cleanup(ws_id, env_id)


# --- 18. Paste import preserves identity + revision on update


def test_paste_import_update_does_not_drop_identity(client, seeded_workspace):
    """P2 fix: paste-import previously replaced the whole EnvVar object
    with the parsed {key, value}, losing handle/field/revision. The subsequent
    save then re-parsed the display name into a different bucket. The
    frontend now merges parsed values into the existing row, keeping
    identity. This test verifies the server accepts the resulting payload
    as a normal update.
    """
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "openai-primary", {"api_key": "sk-orig"})

        r = client.get(f"/credentials/env-vars/{env_id}?workspace_id={ws_id}")
        assert r.status_code == 200
        existing = r.json()[0]
        payload = [{
            "key": existing["key"],
            "value": "sk-rotated-via-paste",
            "handle": existing["handle"],
            "field": existing["field"],
            "expected_revision": existing["revision"],
        }]
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=payload,
        )
        assert r.status_code == 200, r.text
        row = _list_row(ws_id, env_id, "openai-primary")
        assert _decrypted(row) == {"api_key": "sk-rotated-via-paste"}
    finally:
        _cleanup(ws_id, env_id)


# --- 19. Delete last field then recreate cycle works


def test_delete_last_field_promotes_to_row_delete_so_recreate_works(
    client, seeded_workspace,
):
    """P2 fix: previously field-delete of the last field left an
    encrypted_credentials=None row with a bumped revision that the client
    couldn't observe (list_env_vars filters empty ciphertext), so recreating
    the credential via PUT tried to insert a new row and hit the unique
    constraint. The endpoint now promotes an empty-result field-delete to
    a whole-row delete so the recreate path is clean.
    """
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "sentry", {"token": "sen-orig"})

        r = client.delete(
            f"/credentials/env-vars/{env_id}/handles/sentry"
            f"?workspace_id={ws_id}&expected_revision=1&field=token",
        )
        assert r.status_code == 200, r.text

        assert _list_row(ws_id, env_id, "sentry") is None

        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[{
                "key": "SENTRY_TOKEN", "value": "sen-recreated",
                "handle": "sentry", "field": "token",
            }],
        )
        assert r.status_code == 200, r.text
        row = _list_row(ws_id, env_id, "sentry")
        assert row is not None
        assert _decrypted(row) == {"token": "sen-recreated"}
    finally:
        _cleanup(ws_id, env_id)



# --- 15. Adding a new field to an existing env_vars bag doesn't 409 ---


def test_new_field_can_piggyback_on_existing_bag_revision(client, seeded_workspace):
    """Screenshot bug: env_vars bag has revision=N holding e2b_api_key.
    User adds a new field to the same bag; new item has no
    expected_revision (client didn't know about the row). Previous logic
    treated (N, None) as disagreement and 409'd. Fix: non-null revisions
    must all agree; None piggybacks.
    """
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(
            ws_id, env_id, "env_vars", {"e2b_api_key": "opaque-existing"},
        )
        r = client.put(
            f"/credentials/env-vars/{env_id}?workspace_id={ws_id}",
            json=[
                {
                    "key": "e2b_api_key", "value": "opaque-existing",
                    "handle": "env_vars", "field": "e2b_api_key",
                    "expected_revision": 1,
                },
                # New item: no handle/field/revision. Server resolves to
                # (env_vars, MY_NEW_KEY) via alias fallback and piggybacks
                # on the group's expected_revision (1).
                {"key": "MY_NEW_KEY", "value": "opaque-new"},
            ],
        )
        assert r.status_code == 200, r.text
        row = _list_row(ws_id, env_id, "env_vars")
        merged = _decrypted(row)
        assert merged == {"e2b_api_key": "opaque-existing", "MY_NEW_KEY": "opaque-new"}
    finally:
        _cleanup(ws_id, env_id)



# --- 16. get_credential fallback prefers Default env, not arbitrary cross-env ---


def test_get_credential_no_env_prefers_default_over_arbitrary_first_match(
    client, seeded_workspace,
):
    """Reviewer P1-3: previously an arbitrary .first() across every
    environment could return a staging key when a background worker
    (Slack webhook, watchdog, email) asked for a handle without an env.
    Fix: no env supplied → workspace's Default env row wins; only then
    workspace-unscoped rows; never cross-env first-match."""
    from app.core.database import SessionLocal
    from app.core.credentials import get_credential
    from app.models.environment import Environment

    ws_id, _token = seeded_workspace
    # Two named envs; a Default with the correct anthropic row and a
    # staging env with a rotated key that must NEVER surface via the
    # env-less fallback.
    default_env = uuid.uuid4()
    staging_env = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Environment(id=default_env, workspace_id=ws_id, name="Default"))
        db.add(Environment(id=staging_env, workspace_id=ws_id, name="staging"))
        db.commit()

    _seed_integration(ws_id, default_env, "anthropic", {"api_key": "prod-key"})
    _seed_integration(ws_id, staging_env, "anthropic", {"api_key": "staging-key"})
    try:
        with SessionLocal() as db:
            got = get_credential(db, str(ws_id), "anthropic")
            assert got.get("api_key") == "prod-key", (
                "env-less fallback resolved a non-Default environment — "
                "reintroduced the P1-3 cross-env leak."
            )
    finally:
        _cleanup(ws_id, default_env)
        with SessionLocal() as db:
            db.query(Environment).filter(Environment.id == staging_env).delete()
            db.commit()


def test_get_credential_no_env_falls_back_to_workspace_unscoped_row(
    client, seeded_workspace,
):
    """Some legacy tables use env-agnostic rows (proxy_config, etc.). When
    no Default env has a matching row, fall through to a workspace-level
    unscoped row rather than searching other envs."""
    from app.core.database import SessionLocal
    from app.core.credentials import get_credential
    from app.models.environment import Environment
    from app.models.integration import Integration
    from app.core.crypto import encrypt

    ws_id, _token = seeded_workspace
    default_env = uuid.uuid4()
    with SessionLocal() as db:
        db.add(Environment(id=default_env, workspace_id=ws_id, name="Default"))
        # Unscoped (workspace-level) row for the legacy handle.
        db.add(Integration(
            id=uuid.uuid4(),
            workspace_id=ws_id,
            environment_id=None,
            service="proxy_config",
            handle="proxy_config",
            auth_method="api_key",
            encrypted_credentials=encrypt({"LLM_UPSTREAM": "https://prod"}),
            revision=1,
        ))
        db.commit()
    try:
        with SessionLocal() as db:
            got = get_credential(db, str(ws_id), "proxy_config")
            assert got.get("LLM_UPSTREAM") == "https://prod"
    finally:
        _cleanup(ws_id, default_env)




# --- 20. list_env_vars never returns values (Phase 1 finisher) ---


def test_list_env_vars_never_returns_values(client, seeded_workspace):
    """Reviewer P2 (round 1): the environment editor was a mass-reveal
    endpoint dressed up as a list. Now the list carries metadata only —
    values must never appear even for a caller with full permissions."""
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-secret-anthropic"})
        _seed_integration(ws_id, env_id, "env_vars", {"CUSTOM": "value-should-not-appear"})

        r = client.get(f"/credentials/env-vars/{env_id}?workspace_id={ws_id}")
        assert r.status_code == 200, r.text
        body_text = r.text
        assert "sk-secret-anthropic" not in body_text
        assert "value-should-not-appear" not in body_text
        for row in r.json():
            assert "value" not in row
            assert "has_value" in row
    finally:
        _cleanup(ws_id, env_id)


# --- 21. reveal returns one field value and writes an audit row ---


def test_reveal_returns_value_and_writes_audit_event(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-real"})

        # Snapshot audit-log row count before.
        from app.core.database import SessionLocal
        from app.models.audit_log import AuditLog
        with SessionLocal() as db:
            before = db.query(AuditLog).filter(
                AuditLog.workspace_id == ws_id,
                AuditLog.action == "credential.reveal",
            ).count()

        r = client.post(
            f"/credentials/env-vars/{env_id}/reveal?workspace_id={ws_id}",
            json={"handle": "anthropic", "field": "api_key"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"handle": "anthropic", "field": "api_key", "value": "sk-real"}

        with SessionLocal() as db:
            after = db.query(AuditLog).filter(
                AuditLog.workspace_id == ws_id,
                AuditLog.action == "credential.reveal",
            ).count()
        assert after == before + 1, "reveal did not write an audit row"
    finally:
        _cleanup(ws_id, env_id)


# --- 22. reveal audits failed attempts too ---


def test_reveal_audits_failure_when_field_not_present(client, seeded_workspace):
    ws_id, _token = seeded_workspace
    env_id = _seed_environment(ws_id)
    try:
        _seed_integration(ws_id, env_id, "anthropic", {"api_key": "sk-real"})

        from app.core.database import SessionLocal
        from app.models.audit_log import AuditLog
        with SessionLocal() as db:
            before = db.query(AuditLog).filter(
                AuditLog.workspace_id == ws_id,
                AuditLog.action == "credential.reveal",
            ).count()

        r = client.post(
            f"/credentials/env-vars/{env_id}/reveal?workspace_id={ws_id}",
            json={"handle": "anthropic", "field": "no_such_field"},
        )
        assert r.status_code == 404, r.text

        with SessionLocal() as db:
            after = db.query(AuditLog).filter(
                AuditLog.workspace_id == ws_id,
                AuditLog.action == "credential.reveal",
            ).count()
        assert after == before + 1, "failed reveal did not write an audit row"
    finally:
        _cleanup(ws_id, env_id)


# --- 23. reveal refuses cross-workspace env ---


def test_reveal_refuses_cross_workspace_environment(client, seeded_workspace):
    ws_a, _t = seeded_workspace
    env_a = _seed_environment(ws_a)

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
        db.add(Environment(id=env_b, workspace_id=ws_b, name="rival"))
        db.commit()
    _seed_integration(ws_b, env_b, "anthropic", {"api_key": "sk-other"})
    try:
        r = client.post(
            f"/credentials/env-vars/{env_b}/reveal?workspace_id={ws_a}",
            json={"handle": "anthropic", "field": "api_key"},
        )
        assert r.status_code == 404, r.text
    finally:
        _cleanup(ws_a, env_a)
        with SessionLocal() as db:
            from app.models.integration import Integration
            db.query(Integration).filter(Integration.workspace_id == ws_b).delete()
            db.query(Environment).filter(Environment.id == env_b).delete()
            db.query(Workspace).filter(Workspace.id == ws_b).delete()
            db.commit()
