"""Shared fixtures, working-copy builders and session stub for the v2
gateway-profile endpoint contract tests
(``test_gateway_profiles_v2_endpoints*.py``).
"""
from __future__ import annotations

from datetime import datetime, timezone
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
    from app.core.auth import get_workspace_id
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


ENV = UUID("11111111-1111-1111-1111-111111111111")
