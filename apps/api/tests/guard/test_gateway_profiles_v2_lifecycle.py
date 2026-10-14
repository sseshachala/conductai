"""Lifecycle contract tests for Gateway Profiles v2: always-editable working
copy, republish, unpublish, alias guard, soft delete, status fields.

Uses the same fake-session TestClient harness as
``test_gateway_profiles_v2_endpoints.py`` (no live Postgres).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from tests.guard._gateway_profiles_v2_helpers import (  # noqa: F401 — fixtures
    ENV,
    _make_session_stub,
    _sample_working_copy,
    app_with_overrides,
    client_and_db,
)

BASE = "/workspaces/{ws}/gateway-profiles-v2"


def _profile(ws, *, name="p", code="seedcode", wc=None, alias="coding",
             active=None, deleted_at=None):
    return SimpleNamespace(
        id=uuid4(), workspace_id=ws, environment_id=None,
        cond_code=code, active_revision_id=active, name=name,
        schema_version="2", config={},
        working_copy=wc if wc is not None else _sample_working_copy(ENV),
        model_alias=alias, deleted_at=deleted_at,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _rev(profile, version, snapshot=None):
    return SimpleNamespace(
        id=uuid4(), profile_id=profile.id, version=version,
        snapshot=snapshot if snapshot is not None else _sample_working_copy(ENV),
        published_by="admin", published_at=datetime.now(timezone.utc),
    )


def _stub(ws, profiles, revisions=()):
    return _make_session_stub(
        profiles=profiles, revisions=list(revisions),
        environments=[SimpleNamespace(id=ENV, workspace_id=ws)],
        integrations=[SimpleNamespace(workspace_id=ws, environment_id=ENV, handle="anthropic")],
    )


def _url(ws, pid, suffix=""):
    return f"{BASE.format(ws=ws)}/{pid}{suffix}"


def _published(ws, **kw):
    p = _profile(ws, **kw)
    r = _rev(p, 1, dict(p.working_copy))
    p.active_revision_id = r.id
    return p, r


# ─── Edit / republish ─────────────────────────────────────────────────


def test_edit_after_publish_keeps_live_revision_and_alias(client_and_db):
    client, holder, ws = client_and_db
    p, r = _published(ws)
    holder["db"] = _stub(ws, [p], [r])
    new_wc = {**_sample_working_copy(ENV), "model_alias": "other", "timeout_seconds": 30}
    resp = client.put(_url(ws, p.id), json={"working_copy": new_wc})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["active_revision_id"] == str(r.id)
    assert body["model_alias"] == "coding"  # live alias unchanged
    assert body["working_copy"]["model_alias"] == "other"
    assert body["status"] == "published"
    assert body["has_unpublished_changes"] is True


def test_republish_creates_v2_then_no_changes_409(client_and_db):
    client, holder, ws = client_and_db
    p, r = _published(ws)
    holder["db"] = _stub(ws, [p], [r])

    resp = client.post(_url(ws, p.id, "/publish"), json={})
    assert resp.status_code == 409
    assert "No changes since v1" in resp.text

    p.working_copy = {**_sample_working_copy(ENV), "timeout_seconds": 30}
    resp = client.post(_url(ws, p.id, "/publish"), json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert sorted(v["version"] for v in body["revisions"]) == [1, 2]
    v2 = next(v for v in body["revisions"] if v["version"] == 2)
    assert body["active_revision_id"] == v2["id"]
    assert body["status"] == "published"
    assert body["has_unpublished_changes"] is False

    resp = client.post(_url(ws, p.id, "/publish"), json={})
    assert resp.status_code == 409
    assert "No changes since v2" in resp.text


# ─── Alias guard ──────────────────────────────────────────────────────


def test_publish_alias_conflict_names_other_profile(client_and_db):
    client, holder, ws = client_and_db
    other, orev = _published(ws, name="claude-sonnet", code="othercode")
    mine = _profile(ws, name="my-imported-case1", code="mycode")
    holder["db"] = _stub(ws, [other, mine], [orev])
    resp = client.post(_url(ws, mine.id, "/publish"), json={})
    assert resp.status_code == 409
    assert "claude-sonnet" in resp.text and "othercode" in resp.text
    assert mine.active_revision_id is None


def test_publish_alias_conflict_ignores_deleted_and_unpublished(client_and_db):
    client, holder, ws = client_and_db
    gone = _profile(ws, name="gone", code="gonecode", deleted_at=datetime.now(timezone.utc))
    gone.active_revision_id = uuid4()  # pathological; deleted rows never conflict
    off = _profile(ws, name="off", code="offcode")
    off_rev = _rev(off, 1)
    mine = _profile(ws, name="mine", code="mycode")
    holder["db"] = _stub(ws, [gone, off, mine], [off_rev])
    resp = client.post(_url(ws, mine.id, "/publish"), json={})
    assert resp.status_code == 200, resp.text


def test_rollback_alias_conflict_409_and_same_profile_ok(client_and_db):
    client, holder, ws = client_and_db
    other, orev = _published(ws, name="claude-sonnet", code="othercode")
    mine = _profile(ws, name="mine", code="mycode")
    mrev = _rev(mine, 1)
    holder["db"] = _stub(ws, [other, mine], [orev, mrev])
    resp = client.post(_url(ws, mine.id, "/rollback"), json={"revision_id": str(mrev.id)})
    assert resp.status_code == 409
    assert "claude-sonnet" in resp.text and "othercode" in resp.text

    # Rolling back the profile that itself owns the alias is fine.
    resp = client.post(_url(ws, other.id, "/rollback"), json={"revision_id": str(orev.id)})
    assert resp.status_code == 200, resp.text


def test_rollback_reactivates_unpublished_profile(client_and_db):
    client, holder, ws = client_and_db
    p = _profile(ws)
    r = _rev(p, 1)
    holder["db"] = _stub(ws, [p], [r])
    resp = client.post(_url(ws, p.id, "/rollback"), json={"revision_id": str(r.id)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "published"


# ─── Unpublish ────────────────────────────────────────────────────────


def test_unpublish_clears_pointer_keeps_history(client_and_db):
    client, holder, ws = client_and_db
    p, r = _published(ws)
    holder["db"] = _stub(ws, [p], [r])
    resp = client.post(_url(ws, p.id, "/unpublish"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["active_revision_id"] is None
    assert body["status"] == "unpublished"
    assert body["has_unpublished_changes"] is False
    assert len(body["revisions"]) == 1
    assert body["working_copy"] == _sample_working_copy(ENV)

    assert client.post(_url(ws, p.id, "/unpublish")).status_code == 409


def test_unpublish_resyncs_cached_alias_to_working_copy(client_and_db):
    client, holder, ws = client_and_db
    p, r = _published(ws)
    holder["db"] = _stub(ws, [p], [r])
    edited = {**_sample_working_copy(ENV), "model_alias": "renamed"}
    assert client.put(_url(ws, p.id), json={"working_copy": edited}).json()["model_alias"] == "coding"

    body = client.post(_url(ws, p.id, "/unpublish")).json()

    assert body["model_alias"] == "renamed"
    assert body["has_unpublished_changes"] is True


def test_unpublish_draft_409(client_and_db):
    client, holder, ws = client_and_db
    p = _profile(ws)
    holder["db"] = _stub(ws, [p])
    assert client.post(_url(ws, p.id, "/unpublish")).status_code == 409


def test_unpublished_profile_no_longer_routes(client_and_db):
    """After unpublish, the rows routing sees (active_revision_id set,
    live) exclude the profile -> select_model 404s."""
    from app.modules.guard.gateway_model_selection import select_model

    client, holder, ws = client_and_db
    p, r = _published(ws)
    holder["db"] = _stub(ws, [p], [r])
    assert client.post(_url(ws, p.id, "/unpublish")).status_code == 200

    routable = [(p, r)] if p.active_revision_id is not None else []
    db = MagicMock()
    q = db.query.return_value
    q.join.return_value = q
    q.filter.return_value = q
    q.all.return_value = routable
    with pytest.raises(HTTPException) as err:
        select_model(db, ws, "coding", "anthropic_messages")
    assert err.value.status_code == 404
    # Routing query also excludes soft-deleted rows.
    assert any("deleted_at" in str(a) for a in q.filter.call_args.args)


# ─── Delete ───────────────────────────────────────────────────────────


def test_delete_draft_is_hard(client_and_db):
    client, holder, ws = client_and_db
    p = _profile(ws)
    db = holder["db"] = _stub(ws, [p])
    assert client.delete(_url(ws, p.id)).status_code == 204
    assert db._storage["profiles"] == []


def test_delete_published_409(client_and_db):
    client, holder, ws = client_and_db
    p, r = _published(ws)
    holder["db"] = _stub(ws, [p], [r])
    resp = client.delete(_url(ws, p.id))
    assert resp.status_code == 409
    assert "Unpublish before deleting" in resp.text
    assert p.deleted_at is None


def test_delete_unpublished_is_soft_and_hidden_everywhere(client_and_db):
    client, holder, ws = client_and_db
    from app.core.auth import get_user_id
    client.app.dependency_overrides[get_user_id] = lambda: "user_test"
    p = _profile(ws, name="reusable")
    r = _rev(p, 1)
    db = holder["db"] = _stub(ws, [p], [r])
    assert client.delete(_url(ws, p.id)).status_code == 204
    assert p.deleted_at is not None
    assert db._storage["profiles"] == [p]      # row kept
    assert db._storage["revisions"] == [r]     # revisions kept

    assert client.get(BASE.format(ws=ws)).json() == []
    wc = _sample_working_copy(ENV)
    calls = [
        ("get", _url(ws, p.id), None),
        ("get", _url(ws, p.id, "/export"), None),
        ("get", _url(ws, p.id, "/revisions"), None),
        ("get", _url(ws, p.id, f"/revisions/{r.id}"), None),
        ("get", _url(ws, p.id, "/rate-limits"), None),
        ("put", _url(ws, p.id, "/rate-limits"), {"rpm": 5}),
        ("put", _url(ws, p.id), {"working_copy": wc}),
        ("post", _url(ws, p.id, "/publish"), {}),
        ("post", _url(ws, p.id, "/unpublish"), None),
        ("post", _url(ws, p.id, "/rollback"), {"revision_id": str(r.id)}),
        ("post", _url(ws, p.id, "/test"), {"prompt": "hi", "provider": "openai"}),
        ("delete", _url(ws, p.id), None),
    ]
    for method, url, payload in calls:
        kw = {"json": payload} if payload is not None else {}
        resp = getattr(client, method)(url, **kw)
        assert resp.status_code == 404, (method, url, resp.status_code, resp.text)

    # Name is reusable after soft delete (create succeeds).
    resp = client.post(BASE.format(ws=ws), json={"name": "reusable", "working_copy": {}})
    assert resp.status_code == 201, resp.text


# ─── Status fields ────────────────────────────────────────────────────


def test_status_and_unpublished_changes_values(client_and_db):
    client, holder, ws = client_and_db
    draft = _profile(ws, name="d", code="dcode", wc={})
    draft.working_copy = None
    pub, prev = _published(ws, name="pub", code="pcode", alias="a1")
    unp = _profile(ws, name="u", code="ucode", alias="a2")
    urev = _rev(unp, 1)
    unp.working_copy = {**_sample_working_copy(ENV), "timeout_seconds": 99}
    holder["db"] = _stub(ws, [draft, pub, unp], [prev, urev])

    rows = {r["name"]: r for r in client.get(BASE.format(ws=ws)).json()}
    assert (rows["d"]["status"], rows["d"]["has_unpublished_changes"]) == ("draft", False)
    assert (rows["pub"]["status"], rows["pub"]["has_unpublished_changes"]) == ("published", False)
    assert (rows["u"]["status"], rows["u"]["has_unpublished_changes"]) == ("unpublished", True)
