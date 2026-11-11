"""Dedicated read-only audit-feed service token (cond_feed_*)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_user_id, get_workspace_id
from app.core.database import get_db
from app.main import app
from app.mcp.server import MCPContext, dispatch
from app.modules.agent_identity import feed_tokens
from app.modules.agent_identity.credentials import token_hash
from app.modules.agent_identity.models import AgentCredentialSession, AgentIdentity
from app.tools.registry import default_registry
from tests.test_audit_export import WS  # noqa: F401  (also registers the JSONB/sqlite shim)


@pytest.fixture
def db_session():
    tables = [AgentIdentity.__table__, AgentCredentialSession.__table__]
    swapped = [(c, c.type) for t in tables for c in t.columns if isinstance(c.type, PGUUID)]
    for c, _ in swapped:
        c.type = sa.Uuid(as_uuid=True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for t in tables:
        t.create(engine)
    Session = sessionmaker(bind=engine)
    yield Session
    for c, t in swapped:
        c.type = t


def _mint(Session, **kw):
    db = Session()
    row, token = feed_tokens.mint(db, WS, kw.pop("name", "splunk-prod"), "user_admin", **kw)
    return db, row, token


def test_token_is_stored_hashed_and_resolves(db_session):
    db, row, token = _mint(db_session)
    assert token.startswith("cond_feed_")
    session = db.query(AgentCredentialSession).one()
    assert session.access_token_hash == token_hash(token)
    assert token not in (row.token_encrypted or "") and token not in row.token_prefix
    assert row.token_type == "feed"
    assert feed_tokens.resolve(token, db).id == row.id
    assert feed_tokens.resolve(token + "x", db) is None
    assert feed_tokens.resolve("cond_agt_whatever", db) is None


def test_revoked_and_expired_tokens_stop_resolving(db_session):
    db, row, token = _mint(db_session)
    feed_tokens.revoke(db, row)
    assert feed_tokens.resolve(token, db) is None
    db2, _, token2 = _mint(db_session, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert feed_tokens.resolve(token2, db2) is None


def test_token_survives_creator_leaving(db_session):
    # No member linkage is consulted: creator id is informational only.
    db, row, token = _mint(db_session)
    assert row.created_by_clerk_user_id == "user_admin"
    assert feed_tokens.resolve(token, db) is not None


def _scoped_ctx():
    return MCPContext(workspace_id=WS, token_scope="audit_feed", collector_id="c1", collector_label="splunk")


def test_scoped_token_can_only_call_the_feed_tool():
    ctx = _scoped_ctx()
    for name in ("export_audit_log", "get_audit_feed_status", "list_workflows", "invite_member", "guard_check"):
        res = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": name, "arguments": {}}}, ctx, default_registry)
        assert res["result"]["isError"] is True
        assert "scoped to the audit feed" in res["result"]["content"][0]["text"]


def test_scoped_token_tools_list_is_filtered():
    res = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, _scoped_ctx(), default_registry)
    assert [t["name"] for t in res["result"]["tools"]] == ["get_audit_feed"]


def test_unknown_scope_gets_no_tools():
    ctx = MCPContext(workspace_id=WS, token_scope="something_else")
    res = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "get_audit_feed", "arguments": {}}}, ctx, default_registry)
    assert res["result"]["isError"] is True


def test_feed_tool_labels_service_collector_and_skips_user_permission():
    from app.tools.registrations.lens import audit_export as tool
    from app.modules.guard import audit_export as ax
    page = {"events": [], "next_cursor": ax.encode_cursor(datetime.now(timezone.utc), uuid.uuid4()),
            "has_more": False, "lag_seconds": 0}
    with patch("app.core.database.SessionLocal"), patch("app.core.workspace_context.set_workspace_rls"), \
            patch("app.core.auth.check_permission") as perm, \
            patch("app.modules.guard.routers.policies_helpers._write_audit") as audit, \
            patch.object(ax, "feed_page", return_value=page), \
            patch.object(ax, "record_feed_pull") as rec:
        out = tool.get_audit_feed(_scoped_ctx())
    assert out["kind"] == "audit_feed"
    perm.assert_not_called()
    assert audit.call_args.kwargs["actor_id"] == "feed-token:c1"
    assert rec.call_args.kwargs["service_label"] == "splunk"


def test_feed_tool_without_scope_still_requires_permission():
    from app.tools.registrations.lens import audit_export as tool
    ctx = MCPContext(workspace_id=WS, clerk_user_id="u1")
    with patch("app.core.database.SessionLocal"), \
            patch("app.core.auth.check_permission", side_effect=HTTPException(403)):
        assert tool.get_audit_feed(ctx)["status_code"] == 403


def test_status_labels_service_token_collectors():
    import fakeredis
    from app.modules.guard import audit_export as ax
    r = fakeredis.FakeRedis(decode_responses=True)
    page = {"events": [], "next_cursor": ax.encode_cursor(datetime.now(timezone.utc), uuid.uuid4())}
    ax.record_feed_pull(WS, "feed-token:c1", page, client=r, service_label="splunk")
    ax.record_feed_pull(WS, "user_1", page, client=r)
    by_id = {c["actor_id"]: c for c in ax.feed_status(WS, client=r)["collectors"]}
    assert by_id["feed-token:c1"]["collector_type"] == "service_token" and by_id["feed-token:c1"]["label"] == "splunk"
    assert by_id["user_1"]["collector_type"] == "user"


def test_other_token_resolvers_reject_feed_tokens(db_session):
    from unittest.mock import MagicMock
    from app.core.auth import resolve_agent_token
    _, _, token = _mint(db_session)
    other = MagicMock()
    other.execute.return_value.fetchone.return_value = None
    assert resolve_agent_token(token, other) is None


# ── admin endpoints ──────────────────────────────────────────────────────────

def _declared_permissions(path_suffix):
    out = {}
    from app.modules.agent_identity.router import router
    for route in router.routes:
        if getattr(route, "path", "").endswith(path_suffix):
            perms = {getattr(d.call, "__conduct_permission__", None) for d in route.dependant.dependencies}
            for m in route.methods:
                out[m] = perms
    return out


def test_every_endpoint_requires_workspace_edit_permission():
    perms = _declared_permissions("/audit-feed-tokens") | _declared_permissions("/audit-feed-tokens/{token_id}")
    assert set(perms) == {"POST", "GET", "DELETE"}
    assert all("platform.workspace.edit" in p for p in perms.values())


@pytest.fixture
def client(db_session):
    def _db():
        s = db_session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_workspace_id] = lambda: WS
    app.dependency_overrides[get_user_id] = lambda: "user_admin"
    with patch("app.modules.guard.routers.policies_helpers._write_audit"):
        yield TestClient(app, raise_server_exceptions=False)
    for dep in (get_db, get_workspace_id, get_user_id):
        app.dependency_overrides.pop(dep, None)


def test_issue_list_revoke_roundtrip(client):
    c = client
    created = c.post(f"/workspaces/{WS}/audit-feed-tokens", json={"name": "splunk"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["token"].startswith("cond_feed_") and body["status"] == "active"
    listed = c.get(f"/workspaces/{WS}/audit-feed-tokens").json()
    assert len(listed) == 1, listed
    assert "token" not in listed[0] and listed[0]["scope"] == "audit_feed"
    assert c.delete(f"/workspaces/{WS}/audit-feed-tokens/{body['id']}").status_code == 204
    assert c.get(f"/workspaces/{WS}/audit-feed-tokens").json()[0]["status"] == "revoked"
    assert c.delete(f"/workspaces/{WS}/audit-feed-tokens/{uuid.uuid4()}").status_code == 404
