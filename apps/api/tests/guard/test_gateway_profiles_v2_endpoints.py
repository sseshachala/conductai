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


def _make_session_stub(*, profiles=None, revisions=None, bindings=None):
    """A hand-rolled fake Session covering the exact call patterns the
    router uses. Every method mutates ``storage`` in-place so subsequent
    queries reflect prior commits (mirroring real DB behavior for tests
    that chain create → update → publish)."""
    storage = {
        "profiles": list(profiles or []),
        "revisions": list(revisions or []),
        "bindings": list(bindings or []),
        "pending": [],  # objects added via db.add() before commit
    }

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

        def all(self):
            return self._session._match_all(self._model, self._filters)

        def one_or_none(self):
            matches = self._session._match_all(self._model, self._filters)
            if len(matches) > 1:
                raise AssertionError(f"expected 1, got {len(matches)}")
            return matches[0] if matches else None

        def scalar(self):
            matches = self._session._match_all(self._model, self._filters)
            return max((m.version for m in matches), default=None) if matches else None

    class _FakeSession:
        def __init__(self):
            self._storage = storage

        def query(self, model_or_column):
            # Some queries do db.query(func.max(GatewayProfileRevision.version))
            # — treat those specially by returning the version scalar.
            model = getattr(model_or_column, "class_", None) or model_or_column
            return _Query(model, self)

        def _match_all(self, model, filters):
            from app.models.gateway_profile import (
                GatewayProfile,
                GatewayProfileBinding,
                GatewayProfileRevision,
            )
            if model is GatewayProfile or getattr(model, "__name__", None) == "GatewayProfile":
                pool = self._storage["profiles"]
            elif model is GatewayProfileRevision:
                pool = self._storage["revisions"]
            elif model is GatewayProfileBinding:
                pool = self._storage["bindings"]
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
                GatewayProfileBinding,
                GatewayProfileRevision,
            )
            if not getattr(obj, "id", None):
                obj.id = uuid4()
            if not getattr(obj, "created_at", None):
                obj.created_at = datetime.now(timezone.utc)
            if not getattr(obj, "updated_at", None):
                obj.updated_at = datetime.now(timezone.utc)
            if isinstance(obj, GatewayProfile):
                self._storage["profiles"].append(obj)
            elif isinstance(obj, GatewayProfileRevision):
                if not obj.published_at:
                    obj.published_at = datetime.now(timezone.utc)
                self._storage["revisions"].append(obj)
            elif isinstance(obj, GatewayProfileBinding):
                if not getattr(obj, "updated_at", None):
                    obj.updated_at = datetime.now(timezone.utc)
                self._storage["bindings"].append(obj)

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
    assert body["bindings"] == []
    assert body["model_alias"] is None


def test_update_working_copy_rejects_invalid_schema(client_and_db):
    """Save is schema-validated — admins should see typos before publish."""
    client, session_holder, ws = client_and_db

    from app.models.gateway_profile import GatewayProfile as GatewayProfileRow

    profile_id = uuid4()
    session_holder["db"] = _make_session_stub(profiles=[
        SimpleNamespace(
            id=profile_id, workspace_id=ws, environment_id=None,
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
            name="p", schema_version="2", config={}, working_copy=None,
            model_alias=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ])

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/publish",
        json={"environment_id": str(ENV)},
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
            name="p", schema_version="2", config={},
            working_copy=_uncertified_working_copy(ENV),
            model_alias="coding",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ])

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/publish",
        json={"environment_id": str(ENV)},
    )
    assert resp.status_code == 400
    msg = resp.text.lower()
    assert "capability check failed" in msg
    assert "openrouter" in msg or "via-openrouter" in msg
    assert "anthropic_messages" in msg


def test_publish_happy_path_creates_revision_and_binding(client_and_db):
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    stub = _make_session_stub(profiles=[
        SimpleNamespace(
            id=profile_id, workspace_id=ws, environment_id=None,
            name="p", schema_version="2", config={},
            working_copy=_sample_working_copy(ENV),
            model_alias="coding",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ])
    session_holder["db"] = stub

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/publish",
        json={"environment_id": str(ENV)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["revisions"]) == 1
    assert body["revisions"][0]["version"] == 1
    # published_by comes from the require_permission dep — any non-empty
    # caller identity is fine for this test's purpose.
    assert body["revisions"][0]["published_by"]
    assert len(body["bindings"]) == 1
    binding = body["bindings"][0]
    assert binding["environment_id"] == str(ENV)
    assert binding["model_alias"] == "coding"
    assert binding["revision_id"] == body["revisions"][0]["id"]


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
    )

    resp = client.post(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/rollback",
        json={"environment_id": str(ENV), "revision_id": str(other_revision_id)},
    )
    assert resp.status_code == 404
    assert "revision not found" in resp.text


def test_delete_refuses_when_binding_still_active(client_and_db):
    """Rollback is the correct way to change what serves live traffic.
    Deleting a profile whose revision is still bound would leave clients
    without a served model — 409 forces the admin to unbind first."""
    client, session_holder, ws = client_and_db
    profile_id = uuid4()
    revision_id = uuid4()
    session_holder["db"] = _make_session_stub(
        profiles=[
            SimpleNamespace(
                id=profile_id, workspace_id=ws, environment_id=None,
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
        bindings=[
            SimpleNamespace(
                workspace_id=ws, environment_id=ENV,
                model_alias="coding", revision_id=revision_id,
                updated_at=datetime.now(timezone.utc),
            ),
        ],
    )

    resp = client.delete(
        f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}",
    )
    assert resp.status_code == 409
    assert "active bindings" in resp.text.lower()
