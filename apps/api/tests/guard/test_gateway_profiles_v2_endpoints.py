"""Endpoint contract tests for the v2 CRUD + publish + rollback router (#2001).

Uses TestClient with the DB + auth dependencies overridden — no live
Postgres required. Session interactions are mocked; the tests lock the
router's logic (payload shapes, validation, atomic pointer semantics),
not the SQLAlchemy-Postgres integration (that's a nightly job).

What each test asserts:

- Draft can be created with an empty working_copy (validation defers
  to publish).
- Save (PUT) rejects a schema-invalid working_copy with 400 — admins
  see typos immediately.
- Publish rejects an empty working_copy with 400.
- Publish rejects an uncertified (target, operation) tuple with 400
  and a specific error message from the capability catalog.
- Publish happy path returns the profile with a new revision + binding.
- Rollback rejects a revision from a different profile with 404
  (defense-in-depth against silent cross-profile binding swap).
- Delete refuses if any binding still points at any revision (409).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


# ─── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def app_with_overrides():
    """Standalone FastAPI app mounting just the v2 router with
    dependencies overridden. Cleaner than mutating the real app —
    no order-dependent teardown against other tests."""
    from fastapi import FastAPI
    from app.core.auth import get_workspace_id, require_permission
    from app.core.database import get_db
    from app.routers.gateway_profiles_v2 import router

    ws = "22222222-2222-2222-2222-222222222222"

    app = FastAPI()
    app.include_router(router)

    session_holder: dict = {"db": None}

    def _get_db():
        return session_holder["db"]

    def _get_ws():
        return ws

    def _perm(*a, **kw):
        return "admin@example.com"

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_workspace_id] = _get_ws
    # ``require_permission`` returns a callable; we override the factory
    # to return a lambda so any permission string routes to the same
    # no-op check for these tests.
    def _require_permission_factory(*args, **kwargs):
        return _perm
    # Not all callers of require_permission are patched via
    # dependency_overrides — the dependency instance is baked into the
    # route by Depends(). Override by identity.
    for route in app.routes:
        for dep in getattr(route, "dependant", MagicMock(dependencies=[])).dependencies:
            if getattr(dep, "call", None) is None:
                continue
            call = dep.call
            if getattr(call, "__qualname__", "").startswith("require_permission"):
                app.dependency_overrides[call] = _perm

    return app, session_holder, ws


@pytest.fixture
def client_and_db(app_with_overrides):
    app, session_holder, ws = app_with_overrides
    return TestClient(app), session_holder, ws


def _sample_working_copy(env_id: UUID) -> dict:
    return {
        "schema_version": 2,
        "name": "prod",
        "model_alias": "coding",
        "accepts": ["anthropic_messages"],
        "timeout_seconds": 60,
        "max_attempts": 2,
        "targets": [
            {
                "id": "primary",
                "transport": "litellm_sdk",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "credential_ref": f"vault://{env_id}/anthropic",
            },
        ],
    }


def _uncertified_working_copy(env_id: UUID) -> dict:
    """OpenRouter passthrough claiming Anthropic Messages — not in the
    v2 launch capability catalog."""
    return {
        "schema_version": 2,
        "name": "openrouter-anthropic-messages",
        "model_alias": "coding",
        "accepts": ["anthropic_messages"],
        "timeout_seconds": 60,
        "max_attempts": 1,
        "targets": [
            {
                "id": "via-openrouter",
                "transport": "http_passthrough",
                "integration": "openrouter",
                "model": "anthropic/claude-sonnet",
                "credential_ref": f"vault://{env_id}/openrouter",
            },
        ],
    }


# ─── Session mock plumbing ────────────────────────────────────────────


def _make_session_stub(*, profiles=None, revisions=None, bindings=None,
                       environments=None, integrations=None, events=None):
    """A hand-rolled fake Session covering the exact call patterns the
    router uses. Every method mutates ``storage`` in-place so subsequent
    queries reflect prior commits (mirroring real DB behavior for tests
    that chain create → update → publish).

    Post-review adds environments + integrations pools so the new
    ownership checks (env belongs to workspace, credential exists) can
    resolve legitimately in the happy-path tests."""
    storage = {
        "profiles": list(profiles or []),
        "revisions": list(revisions or []),
        "environments": list(environments or []),
        "integrations": list(integrations or []),
        "pending": [],  # objects added via db.add() before commit
    }
    # v3 dropped bindings/events entirely; args kept for older callers.
    _ = bindings, events

    class _Query:
        def __init__(self, model, session):
            self._model = model
            self._session = session
            self._filters: list = []
            self._order_by: list = []

        def filter(self, *conds):
            self._filters.extend(conds)
            return self

        def order_by(self, *args):
            self._order_by.extend(args)
            return self

        def with_for_update(self):
            # SQLite/fake: no-op. Postgres serializes concurrent
            # publishes here; unit tests only need the surface.
            return self

        def all(self):
            return self._session._match_all(self._model, self._filters)

        def one_or_none(self):
            matches = self._session._match_all(self._model, self._filters)
            if len(matches) > 1:
                raise AssertionError(f"expected 1, got {len(matches)}")
            return matches[0] if matches else None

        def first(self):
            # cond_code uniqueness check uses .first(); same shape.
            matches = self._session._match_all(self._model, self._filters)
            return matches[0] if matches else None

        def scalar(self):
            matches = self._session._match_all(self._model, self._filters)
            return max((m.version for m in matches), default=None) if matches else None

        def count(self):
            return len(self._session._match_all(self._model, self._filters))

    class _FakeSession:
        def __init__(self):
            self._storage = storage

        def query(self, model_or_column):
            # Some queries do db.query(func.max(GatewayProfileRevision.version))
            # — treat those specially by returning the version scalar.
            model = getattr(model_or_column, "class_", None) or model_or_column
            return _Query(model, self)

        def _match_all(self, model, filters):
            from app.models.environment import Environment
            from app.models.integration import Integration
            from app.models.gateway_profile import (
                GatewayProfile,
                GatewayProfileRevision,
            )
            if model is GatewayProfile or getattr(model, "__name__", None) == "GatewayProfile":
                pool = self._storage["profiles"]
            elif model is GatewayProfileRevision:
                pool = self._storage["revisions"]
            elif model is Environment:
                pool = self._storage["environments"]
            elif model is Integration:
                pool = self._storage["integrations"]
            else:
                pool = []
            # Filter clauses are compiled SQLAlchemy comparators — treat
            # them opaquely by scanning attributes. We rely on the router
            # only using equality/eq filters (verified against the code).
            for cond in filters:
                left = getattr(cond, "left", None)
                right = getattr(cond, "right", None)
                if left is None or right is None:
                    continue
                attr = getattr(left, "name", None)
                if attr is None:
                    continue
                target = getattr(right, "value", right)
                pool = [
                    row for row in pool
                    if str(getattr(row, attr, None)) == str(target)
                ]
            return pool

        def add(self, obj):
            from app.models.gateway_profile import (
                GatewayProfile,
                GatewayProfileRevision,
            )
            if not getattr(obj, "id", None):
                obj.id = uuid4()
            if not getattr(obj, "created_at", None):
                obj.created_at = datetime.now(timezone.utc)
            if not getattr(obj, "updated_at", None):
                obj.updated_at = datetime.now(timezone.utc)
            if isinstance(obj, GatewayProfile):
                # v3: cond_code is now required on the row.
                if not getattr(obj, "cond_code", None):
                    obj.cond_code = "seedcode"
                if not hasattr(obj, "active_revision_id"):
                    obj.active_revision_id = None
                self._storage["profiles"].append(obj)
            elif isinstance(obj, GatewayProfileRevision):
                if not obj.published_at:
                    obj.published_at = datetime.now(timezone.utc)
                self._storage["revisions"].append(obj)

        def delete(self, obj):
            from app.models.gateway_profile import GatewayProfile
            if isinstance(obj, GatewayProfile):
                self._storage["profiles"] = [
                    p for p in self._storage["profiles"] if p.id != obj.id
                ]

        def commit(self):
            pass

        def flush(self):
            pass

        def refresh(self, obj):
            pass

    return _FakeSession()


# ─── Tests ────────────────────────────────────────────────────────────


ENV = UUID("11111111-1111-1111-1111-111111111111")


def test_create_draft_with_empty_working_copy_succeeds(client_and_db):
    """Publish is where validation lives; save must not gate."""
    client, session_holder, ws = client_and_db
    session_holder["db"] = _make_session_stub()

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2",
        json={"name": "new-draft", "working_copy": {}},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "new-draft"
    assert body["revisions"] == []
    assert body["model_alias"] is None
    assert body["active_revision_id"] is None
    assert body["cond_code"]   # server-generated, present in the response


def test_update_working_copy_rejects_invalid_schema(client_and_db):
    """Save is schema-validated — admins should see typos before publish."""
    client, session_holder, ws = client_and_db

    from app.models.gateway_profile import GatewayProfile as GatewayProfileRow

    profile_id = uuid4()
    session_holder["db"] = _make_session_stub(profiles=[
        SimpleNamespace(
            id=profile_id, workspace_id=ws, environment_id=None,
            cond_code="seedcode", active_revision_id=None,
            name="p", schema_version="2", config={}, working_copy=None,
            model_alias=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ])

    resp = client.put(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}",
        json={"working_copy": {"schema_version": 2}},  # missing everything else
    )
    assert resp.status_code == 400
    assert "schema invalid" in resp.text.lower()


def test_publish_rejects_empty_working_copy(client_and_db):
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    session_holder["db"] = _make_session_stub(profiles=[
        SimpleNamespace(
            id=profile_id, workspace_id=ws, environment_id=None,
            cond_code="seedcode", active_revision_id=None,
            name="p", schema_version="2", config={}, working_copy=None,
            model_alias=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ])

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/publish",
        json={},
    )
    assert resp.status_code == 400
    assert "working_copy is empty" in resp.text


def test_publish_rejects_uncertified_capability(client_and_db):
    """OpenRouter passthrough is not certified for Anthropic Messages in
    the v2 launch catalog — publish must fail loudly with the catalog
    version + the offending target id in the error string."""
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    session_holder["db"] = _make_session_stub(profiles=[
        SimpleNamespace(
            id=profile_id, workspace_id=ws, environment_id=None,
            cond_code="seedcode", active_revision_id=None,
            name="p", schema_version="2", config={},
            working_copy=_uncertified_working_copy(ENV),
            model_alias="coding",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ])

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/publish",
        json={},
    )
    assert resp.status_code == 400
    msg = resp.text.lower()
    assert "capability check failed" in msg
    assert "openrouter" in msg or "via-openrouter" in msg
    assert "anthropic_messages" in msg


def test_publish_happy_path_creates_revision_and_activates_it(client_and_db):
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    stub = _make_session_stub(
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
        # Publish now verifies the environment belongs to the workspace
        # and that every credential_ref points at a real Vault entry.
        environments=[
            SimpleNamespace(id=ENV, workspace_id=ws),
        ],
        integrations=[
            SimpleNamespace(workspace_id=ws, environment_id=ENV, handle="anthropic"),
        ],
    )
    session_holder["db"] = stub

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/publish",
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["revisions"]) == 1
    assert body["revisions"][0]["version"] == 1
    assert body["revisions"][0]["published_by"]
    # v3: no bindings; active_revision_id names the live revision.
    assert body["active_revision_id"] == body["revisions"][0]["id"]
    assert body["model_alias"] == "coding"


def test_rollback_rejects_cross_profile_revision_id(client_and_db):
    """Defense-in-depth: even if a caller submits a revision belonging
    to a different profile, the URL scope wins. 404 is the right
    signal — from the caller's perspective the revision doesn't exist
    for this profile."""
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    other_profile_id = uuid4()
    other_revision_id = uuid4()
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
                id=other_revision_id, profile_id=other_profile_id,
                version=1, snapshot=_sample_working_copy(ENV),
                published_by="someone-else", published_at=datetime.now(timezone.utc),
            ),
        ],
        environments=[
            SimpleNamespace(id=ENV, workspace_id=ws),
        ],
    )

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/rollback",
        json={"revision_id": str(other_revision_id)},
    )
    assert resp.status_code == 404
    assert "revision not found" in resp.text


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
