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
from uuid import uuid4

import pytest

from tests.guard._gateway_profiles_v2_helpers import (  # noqa: F401 — fixtures
    ENV,
    _make_session_stub,
    _sample_working_copy,
    _uncertified_working_copy,
    app_with_overrides,
    client_and_db,
)


# ─── Tests ────────────────────────────────────────────────────────────


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
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["errors"]
    assert "errors.pydantic.dev" not in resp.text
    assert "input_value" not in resp.text


@pytest.mark.parametrize("field,value", [
    ("model_alias", ""), ("model_alias", " "),
    ("max_attempts", 6), ("timeout_seconds", 601),
])
def test_save_reports_invalid_profile_field(client_and_db, field, value):
    client, session_holder, ws = client_and_db
    session_holder["db"] = _make_session_stub()
    created = client.post(f"/workspaces/{ws}/gateway-profiles-v2", json={"name": "Case 3"})
    assert created.status_code == 201
    working_copy = _sample_working_copy(uuid4())
    working_copy[field] = value
    resp = client.put(f"/workspaces/{ws}/gateway-profiles-v2/{created.json()['id']}",
                      json={"working_copy": working_copy})
    assert resp.status_code == 400
    errors = resp.json()["detail"]["errors"]
    assert [error["path"] for error in errors] == [field]
    assert errors[0]["target_index"] is None
    assert "errors.pydantic.dev" not in resp.text


def test_save_keeps_capability_validation_deferred_to_publish(client_and_db):
    client, session_holder, ws = client_and_db
    session_holder["db"] = _make_session_stub()
    created = client.post(f"/workspaces/{ws}/gateway-profiles-v2", json={"name": "draft"})
    assert created.status_code == 201
    profile_id = created.json()["id"]
    resp = client.put(f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}",
                      json={"working_copy": _uncertified_working_copy(uuid4())})
    assert resp.status_code == 200
    resp = client.post(f"/workspaces/{ws}/gateway-profiles-v2/{profile_id}/publish", json={})
    assert resp.status_code == 400
    assert resp.json()["detail"]["summary"] == "capability check failed"


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
