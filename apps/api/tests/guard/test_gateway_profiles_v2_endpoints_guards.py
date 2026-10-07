"""Endpoint contract tests for the v2 gateway-profile router (#2001) —
guard rails: delete refusal, cross-workspace URL rejection, publish-time
credential verification and snapshot workspace ownership.

Uses TestClient with DB + auth dependencies overridden (no live Postgres).
Split from ``test_gateway_profiles_v2_endpoints.py``; shared fixtures live in
``_gateway_profiles_v2_helpers.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from tests.guard._gateway_profiles_v2_helpers import (  # noqa: F401 — fixtures
    ENV,
    _make_session_stub,
    _sample_working_copy,
    app_with_overrides,
    client_and_db,
)


def test_delete_refuses_when_any_historical_revision_exists(client_and_db):
    """Review-fix: previously delete refused only when a binding was
    still active. But an unbound-yet-previously-published profile still
    has publish history — cascade-drop via ``ON DELETE CASCADE`` on the
    revisions FK would erase it. Contract is now stricter: refuse when
    any revision exists at all, so rollback remains possible against
    the history."""
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    revision_id = uuid4()
    session_holder["db"] = _make_session_stub(
        profiles=[
            SimpleNamespace(
                id=profile_id, workspace_id=ws, environment_id=None,
                cond_code="seedcode", active_revision_id=None,
                name="p", schema_version="2", config={}, working_copy=None,
                model_alias="coding",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ],
        revisions=[
            SimpleNamespace(
                id=revision_id, profile_id=profile_id, version=1,
                snapshot=_sample_working_copy(ENV),
                published_by="admin", published_at=datetime.now(timezone.utc),
            ),
        ],
        # Deliberately NO bindings — the revision alone is enough to
        # trigger the 409. Old code would have allowed delete here.
    )

    resp = client.delete(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}",
    )
    assert resp.status_code == 409
    # v3: either "revision history" or "published" wording is acceptable —
    # both call sites signal the same intent.
    assert "revision history" in resp.text.lower() or "published" in resp.text.lower()


def test_delete_allowed_on_pure_draft(client_and_db):
    """Complement: a profile with no revisions can still be deleted.
    Locks the "never published, never bound" happy path so the contract
    doesn't accidentally strand truly-empty drafts."""
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    session_holder["db"] = _make_session_stub(
        profiles=[
            SimpleNamespace(
                id=profile_id, workspace_id=ws, environment_id=None,
                cond_code="seedcode", active_revision_id=None,
                name="unused", schema_version="2", config={},
                working_copy=None, model_alias=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ],
    )
    resp = client.delete(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}",
    )
    assert resp.status_code == 204, resp.text


def test_cross_workspace_url_is_rejected(client_and_db):
    """P1 review fix: without the URL-workspace check, an authorized
    caller could substitute a different workspace UUID into the path
    and address that workspace's profiles. Locked with 404 (not 403)
    so the endpoint doesn't confirm the other workspace's resources
    exist."""
    client, session_holder, ws = client_and_db
    session_holder["db"] = _make_session_stub()

    other_ws = "99999999-9999-9999-9999-999999999999"
    resp = client.get(f"/workspaces/{other_ws}/gateway-profiles-v2")
    assert resp.status_code == 404
    # No mention of the other workspace's UUID in the response body —
    # an information-disclosure guard on top of the authorization guard.
    assert other_ws not in resp.text


def test_publish_rejects_helicone_missing_vendor_key(monkeypatch):
    """PR 5 review — publish must verify BOTH keys are present in the
    vault entry for two-key integrations. Row existence alone was the
    old bar; that let a stub row slip through and 500 at request time."""
    from fastapi import HTTPException
    from app.modules.guard.gateway_config import GatewayProfileV2
    from app.routers.gateway_profiles_v2 import _verify_credentials_exist

    profile = GatewayProfileV2.model_validate({
        "schema_version": 2, "name": "hel", "model_alias": "coding",
        "accepts": ["openai_chat_completions"], "timeout_seconds": 60,
        "max_attempts": 1,
        "targets": [{
            "id": "hel", "transport": "http_passthrough",
            "integration": "helicone_openai", "model": "gpt-4o",
            "credential_ref": f"vault://{ENV}/helicone",
        }],
    })

    fake_env = SimpleNamespace(id=ENV, workspace_id="ws")
    fake_cred = SimpleNamespace(workspace_id="ws", environment_id=ENV, handle="helicone")

    class _FakeDB:
        def query(self, model):
            model_name = model.__name__
            class _Q:
                def filter(self_inner, *a, **k): return self_inner
                def one_or_none(self_inner):
                    if model_name == "Environment": return fake_env
                    if model_name == "Integration": return fake_cred
                    return None
            return _Q()

    # Vault entry has ONLY the primary Helicone key — vendor key missing.
    monkeypatch.setattr(
        "app.core.credentials.get_vault_credential",
        lambda db, ws, env, sel: {"HELICONE_API_KEY": "sk-hel-only"},
    )

    try:
        _verify_credentials_exist(_FakeDB(), "ws", profile)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "OPENAI_API_KEY" in str(exc.detail)
        return
    raise AssertionError("expected publish to reject missing vendor key")


def test_publish_accepts_helicone_when_both_keys_present(monkeypatch):
    """Mirror of the above — vault entry has both keys → passes."""
    from app.modules.guard.gateway_config import GatewayProfileV2
    from app.routers.gateway_profiles_v2 import _verify_credentials_exist

    profile = GatewayProfileV2.model_validate({
        "schema_version": 2, "name": "hel", "model_alias": "coding",
        "accepts": ["openai_chat_completions"], "timeout_seconds": 60,
        "max_attempts": 1,
        "targets": [{
            "id": "hel", "transport": "http_passthrough",
            "integration": "helicone_openai", "model": "gpt-4o",
            "credential_ref": f"vault://{ENV}/helicone",
        }],
    })

    fake_env = SimpleNamespace(id=ENV, workspace_id="ws")
    fake_cred = SimpleNamespace(workspace_id="ws", environment_id=ENV, handle="helicone")

    class _FakeDB:
        def query(self, model):
            model_name = model.__name__
            class _Q:
                def filter(self_inner, *a, **k): return self_inner
                def one_or_none(self_inner):
                    if model_name == "Environment": return fake_env
                    if model_name == "Integration": return fake_cred
                    return None
            return _Q()

    monkeypatch.setattr(
        "app.core.credentials.get_vault_credential",
        lambda db, ws, env, sel: {
            "HELICONE_API_KEY": "sk-hel",
            "OPENAI_API_KEY":   "sk-openai",
        },
    )

    _verify_credentials_exist(_FakeDB(), "ws", profile)  # must not raise


def test_publish_rejects_missing_credential(client_and_db):
    """P1 review fix: publish must verify every target's credential_ref
    resolves to a real Vault entry. Otherwise the runtime discovers the
    gap on the first request and 5xxes the client, instead of the admin
    fixing it while the profile is still a draft."""
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    session_holder["db"] = _make_session_stub(
        profiles=[
            SimpleNamespace(
                id=profile_id, workspace_id=ws, environment_id=None,
                cond_code="seedcode", active_revision_id=None,
                name="p", schema_version="2", config={},
                working_copy=_sample_working_copy(ENV),
                model_alias="coding",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ],
        environments=[
            SimpleNamespace(id=ENV, workspace_id=ws),
        ],
        # No integrations seeded — credential lookup returns None.
    )
    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/publish",
        json={},
    )
    assert resp.status_code == 400
    body = resp.text.lower()
    assert "credential_ref" in body or "vault" in body


def test_snapshot_endpoint_verifies_profile_workspace_ownership(client_and_db):
    """Review fix: the snapshot endpoint's URL check verifies workspace,
    but the historical filter was ``id + profile_id`` only. A caller
    supplying another workspace's profile_id + revision_id could
    otherwise read that snapshot. Post-fix: _load_profile runs first
    and 404s on ownership mismatch, so an unknown profile_id → 404
    regardless of whether the revision id would match."""
    client, session_holder, ws = client_and_db
    other_workspace = "44444444-4444-4444-4444-444444444444"
    other_profile_id = uuid4()
    revision_id = uuid4()

    session_holder["db"] = _make_session_stub(
        profiles=[
            # Profile belongs to another workspace, not the caller's.
            SimpleNamespace(
                id=other_profile_id, workspace_id=other_workspace,
                environment_id=None,
                cond_code="othercod", active_revision_id=None,
                name="p", schema_version="2",
                config={}, working_copy=None, model_alias="coding",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ],
        revisions=[
            SimpleNamespace(
                id=revision_id, profile_id=other_profile_id, version=1,
                snapshot=_sample_working_copy(ENV),
                published_by="admin", published_at=datetime.now(timezone.utc),
            ),
        ],
    )

    resp = client.get(
        f"/workspaces/{ws}/gateway-profiles-v2/{other_profile_id}"
        f"/revisions/{revision_id}",
    )
    # Caller's URL workspace matches the authenticated one; profile
    # belongs to a different workspace → 404 at profile lookup, not
    # at revision lookup (which would have returned the snapshot).
    assert resp.status_code == 404
    # No mention of the historical revision id or the other workspace.
    assert other_workspace not in resp.text
