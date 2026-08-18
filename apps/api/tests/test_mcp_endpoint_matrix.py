"""MCP endpoint x auth x workspace-state matrix (api-matrix).

Exercises POST /guard/mcp end-to-end against a real Postgres. The one that
would have caught 89cc839: test_initialize_when_workspace_missing_guardconfig.

Runs under `pytest -m matrix` in the nightly api-matrix job. Skips locally
when Postgres is not reachable.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.crypto import encrypt as _encrypt
from app.core.database import SessionLocal
from app.main import app
from app.models.workspace import Workspace
from app.modules.agent_identity.models import AgentIdentity

MCP_URL = "/guard/mcp"
API_PREFIX = "cond_api_"


def _db_available():
    try:
        with SessionLocal() as db:
            db.query(Workspace).limit(1).all()
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


def _rpc(method, params=None, mid=1):
    return {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}


def _mint_identity(db, workspace_id):
    plaintext = API_PREFIX + secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    tag = workspace_id.hex[:8]
    db.add(AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name="matrix-test-" + tag,
        provider="conduct",
        token_prefix=plaintext[:13],
        token_encrypted=_encrypt({"token": plaintext}),
        token_type="api",
        token_name="test-oauth",
        created_by_clerk_user_id="user_test_" + tag,
        created_at=now,
        last_used_at=now,
        expires_at=None,
    ))
    db.commit()
    return plaintext


@pytest.fixture
def workspace_no_config():
    ws_id = uuid.uuid4()
    tag = ws_id.hex[:8]
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        db.add(Workspace(
            id=ws_id,
            name="mcp-matrix-" + tag,
            owner_id="user_test_" + tag,
            plan="free",
            is_approved=True,
            created_at=now,
            updated_at=now,
        ))
        db.commit()
        token = _mint_identity(db, ws_id)
    yield ws_id, token
    with SessionLocal() as db:
        ws = db.get(Workspace, ws_id)
        if ws is not None:
            db.delete(ws)
            db.commit()


@requires_db
@pytest.mark.matrix
def test_missing_token_returns_401():
    r = TestClient(app).post(MCP_URL, json=_rpc("initialize"))
    assert r.status_code == 401


@requires_db
@pytest.mark.matrix
def test_invalid_token_returns_401():
    r = TestClient(app).post(MCP_URL,
        headers={"Authorization": "Bearer cond_api_definitely-not-real"},
        json=_rpc("initialize"))
    assert r.status_code == 401


@requires_db
@pytest.mark.matrix
def test_initialize_when_workspace_missing_guardconfig(workspace_no_config):
    _ws_id, token = workspace_no_config
    r = TestClient(app).post(MCP_URL,
        headers={"Authorization": "Bearer " + token},
        json=_rpc("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "test"}}))
    assert r.status_code == 200, "regression: 89cc839 loop is back"
    assert "WWW-Authenticate" not in r.headers
    body = r.json()
    assert body.get("result", {}).get("protocolVersion") == "2024-11-05"


@requires_db
@pytest.mark.matrix
def test_tools_list_returns_non_empty(workspace_no_config):
    _ws_id, token = workspace_no_config
    c = TestClient(app)
    c.post(MCP_URL, headers={"Authorization": "Bearer " + token},
           json=_rpc("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "test"}}))
    r = c.post(MCP_URL, headers={"Authorization": "Bearer " + token},
               json=_rpc("tools/list", mid=2))
    assert r.status_code == 200
    tools = r.json().get("result", {}).get("tools", [])
    assert len(tools) >= 5
    names = {t["name"] for t in tools}
    assert {"guard_check", "guard_activity", "guard_status"}.issubset(names)


@requires_db
@pytest.mark.matrix
def test_guard_discover_returns_full_inventory_with_governed_flag(workspace_no_config):
    """Regression 971cdce: payload uses `agents` (not `shadow_agents`) with per-entry `governed` flag."""
    from app.modules.guard.models import DiscoveredAgent
    ws_id, token = workspace_no_config
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(DiscoveredAgent(id=uuid.uuid4(), workspace_id=ws_id, name="gov-agent",
            framework="claude-code", source="ai-tool", location="-",
            under_guard=True, proxy_routed=False, first_seen_at=now))
        db.add(DiscoveredAgent(id=uuid.uuid4(), workspace_id=ws_id, name="shadow-agent",
            framework="cursor", source="config", location="/tmp/x",
            under_guard=False, proxy_routed=False, first_seen_at=now))
        db.commit()

    c = TestClient(app)
    c.post(MCP_URL, headers={"Authorization": "Bearer " + token},
           json=_rpc("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "test"}}))
    r = c.post(MCP_URL, headers={"Authorization": "Bearer " + token},
               json=_rpc("tools/call", {"name": "guard_discover", "arguments": {}}, mid=2))
    assert r.status_code == 200
    text = r.json()["result"]["content"][0]["text"]
    assert '"governed": true' in text
    assert '"governed": false' in text
    assert '"shadow_agents"' not in text


@requires_db
@pytest.mark.matrix
def test_notifications_initialized_is_204(workspace_no_config):
    _ws_id, token = workspace_no_config
    r = TestClient(app).post(MCP_URL,
        headers={"Authorization": "Bearer " + token},
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    assert r.status_code == 204


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-m", "matrix"]))
