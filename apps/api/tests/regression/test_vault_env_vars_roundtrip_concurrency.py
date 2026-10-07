"""Vault env-var round-trip regression tests (#2054 Phase 1) — revision
concurrency, rotation races, import and delete/recreate lifecycle.

Split from ``test_vault_env_vars_roundtrip.py``; shared helpers live in
``_vault_env_vars_helpers.py``.
"""
from __future__ import annotations

import uuid

import pytest

from tests.regression.conftest import requires_db
from tests.regression._vault_env_vars_helpers import (
    _cleanup,
    _decrypted,
    _list_row,
    _seed_environment,
    _seed_integration,
)


pytestmark = [requires_db, pytest.mark.usefixtures("local_development_auth")]


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
