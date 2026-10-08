"""OAuth-to-canonical-MCP journeys against an isolated PostgreSQL schema.

Identity/policy inputs and notification delivery use fixtures. Credentials,
membership, PKCE, rotation, HTTP and approval persistence use application code.
The approval endpoint receives an explicit fixture approver identity and role.
These tests are server integration evidence, not native-client acceptance.
"""
import base64
import hashlib
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import database as database_module
from app.core.config import settings
from app.mcp import http, server
from app.models.oauth import OauthAuthCode
from app.modules.agent_identity.models import AgentCredentialSession
from app.modules.agent_identity.credentials import token_hash
from app.modules.auth.oauth import authorize
from app.modules.auth.oauth.router import router as oauth_router, well_known_router as oauth_metadata_router
from app.guard.policy_types import PolicyAction, PolicyDecision
from app.tools.registry import ToolRegistry
from app.tools.types import ToolDef
from tests.test_credential_sessions_postgres import USER, WS, database  # noqa: F401

OTHER_WS = "22222222-2222-4222-8222-222222222222"
CALLBACK = "http://127.0.0.1:23514/oauth/callback"
VERIFIER = "acceptance-pkce-verifier-" + "x" * 40
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture
def journey(monkeypatch, request):
    if os.environ.get("MCP_ACCEPTANCE_REQUIRED") == "1" and not os.environ.get("CREDENTIAL_TEST_DATABASE_URL"):
        pytest.fail("MCP acceptance requires CREDENTIAL_TEST_DATABASE_URL")
    engine = request.getfixturevalue("database")
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    monkeypatch.setattr(authorize, "_verify_clerk_token", lambda _: {"sub": USER})
    monkeypatch.setattr(database_module, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr("app.core.auth.get_clerk_user_email", lambda _: None)
    state = {"action": PolicyAction.ALLOW, "calls": []}
    monkeypatch.setattr(server, "evaluate_composed", lambda _: PolicyDecision(
        action=state["action"], source="acceptance-fixture", rule_id="fixture-approval"))
    registry = ToolRegistry()

    def canary(marker, ctx):
        result = {"marker": marker, "workspace_id": ctx.workspace_id,
                  "actor_id": ctx.clerk_user_id, "session_id": ctx.session_id}
        state["calls"].append(result)
        return result

    registry.register(ToolDef(name="acceptance_canary", description="Isolated test canary",
                              input_schema={"type": "object", "properties": {"marker": {"type": "string"}},
                                            "required": ["marker"]}, impl=canary))
    monkeypatch.setattr(http, "default_registry", registry)
    app = FastAPI()
    app.include_router(oauth_router)
    app.include_router(oauth_metadata_router)
    app.include_router(http.router)
    app.include_router(http.well_known_router)

    def get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[database_module.get_db] = get_db
    with TestClient(app) as client:
        yield client, engine, state


def authorize_code(client, workspace=WS):
    response = client.post("/oauth/register", json={
        "client_name": "acceptance-public-client", "redirect_uris": [CALLBACK]})
    assert response.status_code == 200
    client_id = response.json()["client_id"]
    response = client.get("/oauth/authorize", params={
        "response_type": "code", "client_id": client_id, "redirect_uri": CALLBACK,
        "code_challenge": CHALLENGE, "code_challenge_method": "S256", "state": "fixture-state"},
        follow_redirects=False)
    assert response.status_code == 302
    request_id = parse_qs(urlsplit(response.headers["location"]).query)["request_id"][0]
    response = client.post("/oauth/authorize/confirm", json={
        "request_id": request_id, "clerk_token": "external-idp-fixture", "workspace_id": workspace})
    if response.status_code != 200:
        return response, None
    query = parse_qs(urlsplit(response.json()["redirect_url"]).query)
    assert query["state"] == ["fixture-state"]
    return response, {"grant_type": "authorization_code", "client_id": client_id,
                      "redirect_uri": CALLBACK, "code": query["code"][0], "code_verifier": VERIFIER}


def login(client, workspace=WS):
    response, data = authorize_code(client, workspace)
    assert response.status_code == 200
    response = client.post("/oauth/token", data=data)
    assert response.status_code == 200
    return response.json()


def rpc(client, access, method="tools/call", *, headers=None, params=None):
    return client.post("/mcp", headers={"Authorization": "Bearer " + access, **(headers or {})},
                       json={"jsonrpc": "2.0", "id": 1, "method": method,
                             "params": params if params is not None else {
                                 "name": "acceptance_canary", "arguments": {"marker": "fixture-marker"}}})


def result(response):
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1 and "error" not in body
    assert not body["result"].get("isError")
    return body["result"]


def test_oauth_connect_discover_invoke_and_attribution(journey):
    client, _, state = journey
    tokens = login(client)
    response = rpc(client, tokens["access_token"], "initialize", params={
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "acceptance-public-client", "version": "1"}})
    assert result(response)["protocolVersion"] == "2025-03-26"
    session = response.headers["Mcp-Session-Id"]
    assert result(rpc(client, tokens["access_token"], "tools/list"))["tools"][0]["name"] == "acceptance_canary"
    observed = result(rpc(client, tokens["access_token"], headers={"Mcp-Session-Id": session}))["structuredContent"]
    assert observed == {"workspace_id": WS, "actor_id": USER, "marker": "fixture-marker", "session_id": session}
    assert state["calls"] == [observed]


def test_refresh_rotates_access_and_rejects_replay(journey):
    client, _, _ = journey
    old = login(client)
    response = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": old["refresh_token"]})
    assert response.status_code == 200
    new = response.json()
    assert new["access_token"] != old["access_token"]
    result(rpc(client, new["access_token"]))
    assert rpc(client, old["access_token"]).status_code == 401
    assert client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": old["refresh_token"]}).status_code == 401


def test_expired_access_can_renew(journey):
    client, engine, _ = journey
    tokens = login(client)
    with Session(engine) as db:
        db.query(AgentCredentialSession).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.commit()
    assert rpc(client, tokens["access_token"]).status_code == 401
    response = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    result(rpc(client, response.json()["access_token"]))


def test_reconnect_does_not_invalidate_another_client(journey):
    client, _, _ = journey
    first, second = login(client), login(client)
    assert first["access_token"] != second["access_token"]
    for tokens in (first, second):
        assert client.delete("/mcp", headers={"Authorization": "Bearer " + tokens["access_token"]}).status_code == 204
        result(rpc(client, tokens["access_token"]))


def test_workspace_switch_requires_new_grant_not_headers(journey):
    client, engine, _ = journey
    with engine.begin() as db:
        db.execute(text("INSERT INTO workspaces VALUES (:ws, 'another-owner')"), {"ws": OTHER_WS})
        db.execute(text("INSERT INTO workspace_users VALUES (:ws, :actor)"), {"ws": OTHER_WS, "actor": USER})
    a, b = login(client), login(client, OTHER_WS)
    for tokens, expected in ((a, WS), (b, OTHER_WS)):
        output = result(rpc(client, tokens["access_token"], headers={
            "X-Workspace-Id": OTHER_WS if expected == WS else WS, "X-User-Id": "forged-actor"}))["structuredContent"]
        assert output["workspace_id"] == expected and output["actor_id"] == USER


def test_unmapped_workspace_cannot_issue_grant(journey):
    client, _, _ = journey
    response, _ = authorize_code(client, OTHER_WS)
    assert response.status_code == 403


@pytest.mark.parametrize("change", ["credential", "membership", "identity"])
def test_revocation_rejects_existing_mcp_session_and_refresh(journey, change):
    client, engine, state = journey
    tokens = login(client)
    connected = rpc(client, tokens["access_token"], "ping", params={})
    session = connected.headers["Mcp-Session-Id"]
    with engine.begin() as db:
        if change == "credential":
            db.execute(text("UPDATE agent_credential_sessions SET revoked_at = now()"))
        elif change == "membership":
            db.execute(text("DELETE FROM workspace_users"))
        else:
            db.execute(text("UPDATE agent_identities SET lifecycle_state = 'deactivated'"))
    response = rpc(client, tokens["access_token"], headers={"Mcp-Session-Id": session})
    assert response.status_code == 401 and "resource_metadata" in response.headers["WWW-Authenticate"]
    assert not state["calls"]
    assert client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}).status_code in (401, 403)


@pytest.mark.parametrize("bad", ["verifier", "callback", "expired", "replay"])
def test_authorization_code_security(journey, bad):
    client, engine, _ = journey
    _, data = authorize_code(client)
    if bad == "verifier":
        data["code_verifier"] = "incorrect-verifier"
    elif bad == "callback":
        data["redirect_uri"] = "https://unregistered.example/callback"
    elif bad == "expired":
        with Session(engine) as db:
            db.query(OauthAuthCode).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
            db.commit()
    else:
        assert client.post("/oauth/token", data=data).status_code == 200
    assert client.post("/oauth/token", data=data).status_code == 400


def test_transport_blocks_controlled_mutation_until_policy_allows(journey):
    client, _, state = journey
    tokens = login(client)
    state["action"] = PolicyAction.APPROVAL
    response = rpc(client, tokens["access_token"]).json()["result"]
    assert response["isError"] and response["_approvalPending"] and not state["calls"]
    state["action"] = PolicyAction.BLOCK
    assert rpc(client, tokens["access_token"]).json()["result"]["isError"]
    assert not state["calls"]
    state["action"] = PolicyAction.ALLOW
    result(rpc(client, tokens["access_token"]))
    assert len(state["calls"]) == 1


@pytest.mark.parametrize("issuer", ["https://api.conductai.ai", "https://conduct.company.example"])
def test_discovery_and_challenge_use_selected_deployment(monkeypatch, issuer):
    monkeypatch.setenv("CONDUCT_OAUTH_ISSUER", issuer)
    app = FastAPI()
    app.include_router(http.router)
    app.include_router(http.well_known_router)
    app.include_router(oauth_metadata_router)
    with TestClient(app) as client:
        resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
        assert resource["resource"] == issuer + "/mcp"
        assert resource["authorization_servers"] == [issuer]
        assert issuer + "/.well-known/oauth-protected-resource/mcp" in client.post("/mcp", json={}).headers["WWW-Authenticate"]
        assert client.get("/.well-known/oauth-authorization-server").json()["issuer"] == issuer


@pytest.fixture
def audited_journey(journey, monkeypatch):
    from app.modules.guard.models import GuardAuditArchiveSegment, GuardAuditEvent
    from app.modules.guard.routers import mcp_helpers as legacy_mcp
    from app.modules.guard.mcp_impls import guard_activity_impl
    from app.tools.registrations.guard import _wrap
    client, engine, _ = journey
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE guard_sessions (id uuid PRIMARY KEY)"))
        GuardAuditArchiveSegment.__table__.create(connection)
        GuardAuditEvent.__table__.create(connection)
    monkeypatch.setattr(legacy_mcp, "chain_hash_for_insert", lambda *args: (None, "fixture-chain"))
    monkeypatch.setattr(legacy_mcp, "get_policy_hash", lambda *args: "fixture-policy")
    registry = ToolRegistry()
    registry.register(ToolDef(name="guard_activity", description="Real activity audit canary",
                              input_schema={"type": "object"}, impl=_wrap(guard_activity_impl)))
    monkeypatch.setattr(http, "default_registry", registry)
    return client, engine


@pytest.fixture
def approval_journey(audited_journey, monkeypatch):
    from app.core import auth
    from app.modules.guard import approval, mcp_impls
    from app.modules.guard.models import GuardApprovalRequest, GuardConfig
    from app.modules.guard.routers import approvals
    from app.tools.registrations.guard import _wrap

    client, engine = audited_journey
    with engine.begin() as db:
        db.execute(text("CREATE TABLE runs (id uuid PRIMARY KEY)"))
        GuardConfig.__table__.create(db)
        GuardApprovalRequest.__table__.create(db)
        db.execute(text("CREATE TABLE acceptance_mutations ("
                        "workspace_id uuid PRIMARY KEY REFERENCES workspaces(id), value integer NOT NULL)"))
        db.execute(text("INSERT INTO acceptance_mutations VALUES (:ws, 0)"), {"ws": WS})
        db.execute(text("INSERT INTO workspace_users VALUES (:ws, 'acceptance-peer')"), {"ws": WS})
    with Session(engine) as db:
        db.add(GuardConfig(workspace_id=UUID(WS), invite_code="approval-fixture", enforcement_mode="block"))
        db.commit()
    rule = {"rule_id": "acceptance-peer-approval", "match_tool": "acceptance_mutation",
            "gates": ["action"], "action": "approval", "approval_type": "peer",
            "approval_timeout_sec": 60, "message": "Disposable test action needs peer approval"}
    monkeypatch.setattr(mcp_impls, "_get_rules", lambda *args, **kwargs: [rule])
    monkeypatch.setattr(approval, "dispatch_approval_notifications", lambda *args: None)
    monkeypatch.setattr(approval, "chain_hash_for_insert", lambda *args: (None, "fixture-chain"))
    monkeypatch.setattr(approval, "get_policy_hash", lambda *args: "fixture-policy")

    def protected_mutation(ctx, value):
        verdict = mcp_impls.guard_check_impl(ctx, tool_name="acceptance_mutation", tool_input={"value": value})
        if verdict != "ok":
            return {"executed": False, "gate": verdict}
        ctx.db.execute(text("UPDATE acceptance_mutations SET value = :value WHERE workspace_id = :ws"),
                       {"value": value, "ws": ctx.workspace_id})
        ctx.db.commit()
        return {"executed": True, "gate": verdict}

    registry = ToolRegistry()
    registry.register(ToolDef(name="acceptance_mutation", description="Isolated approval-gated action",
                              input_schema={"type": "object", "properties": {"value": {"type": "integer"}},
                                            "required": ["value"]}, impl=_wrap(protected_mutation)))
    monkeypatch.setattr(http, "default_registry", registry)
    monkeypatch.setattr(approvals, "get_clerk_user_email", lambda _: None)
    client.app.include_router(approvals.router)
    client.app.dependency_overrides[auth.get_workspace_id] = lambda: WS
    client.app.dependency_overrides[auth.get_user_id] = lambda: "acceptance-peer"
    client.app.dependency_overrides[auth.get_user_workspace_role] = lambda: "admin"
    return client, engine


@pytest.mark.parametrize("outcome", ["approved", "rejected", "timed_out"])
def test_mcp_persisted_approval_controls_actual_fixture_mutation(approval_journey, outcome):
    from app.core import auth
    from app.modules.guard.models import GuardApprovalRequest

    client, engine = approval_journey
    tokens = login(client)
    connected = rpc(client, tokens["access_token"], "initialize", params={
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "ChatGPT", "version": "1"}})
    session = connected.headers["Mcp-Session-Id"]
    params = {"name": "acceptance_mutation", "arguments": {"value": 7}}
    headers = {"Mcp-Session-Id": session}
    first = result(rpc(client, tokens["access_token"], params=params, headers=headers))["structuredContent"]
    assert not first["executed"] and "PENDING approval" in first["gate"]
    with Session(engine) as db:
        request = db.query(GuardApprovalRequest).one()
        request_id = str(request.id)
        assert request.status == "pending" and request.requester_user_id == USER
        assert request.tool_input == {"value": 7} and request.surface == "chatgpt"
        assert str(UUID(request.session_id)) == request.session_id
        assert db.execute(text("SELECT value FROM acceptance_mutations")).scalar_one() == 0
    second = result(rpc(client, tokens["access_token"], params=params, headers=headers))["structuredContent"]
    assert not second["executed"] and second["gate"] == first["gate"]
    with Session(engine) as db:
        assert db.query(GuardApprovalRequest).count() == 1

    client.app.dependency_overrides[auth.get_user_id] = lambda: USER
    assert client.post("/guard/approvals/" + request_id + "/decide", json={"decision": "approved"}).status_code == 403
    client.app.dependency_overrides[auth.get_user_id] = lambda: "acceptance-peer"
    client.app.dependency_overrides[auth.get_workspace_id] = lambda: OTHER_WS
    assert client.get("/guard/approvals/" + request_id).status_code == 404
    assert client.post("/guard/approvals/" + request_id + "/decide", json={"decision": "approved"}).status_code == 404
    client.app.dependency_overrides[auth.get_workspace_id] = lambda: WS

    if outcome == "timed_out":
        with Session(engine) as db:
            request = db.get(GuardApprovalRequest, UUID(request_id))
            request.timeout_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
    else:
        decided = client.post("/guard/approvals/" + request_id + "/decide", json={
            "decision": outcome, "reason": "Disposable lifecycle test"})
        assert decided.status_code == 200
        assert decided.json()["request"]["status"] == outcome

    retried = result(rpc(client, tokens["access_token"], params=params, headers=headers))["structuredContent"]
    assert retried["executed"] is (outcome == "approved")
    if outcome != "approved":
        assert retried["gate"].startswith("BLOCKED")
    with Session(engine) as db:
        assert db.query(GuardApprovalRequest).count() == 1
        assert db.get(GuardApprovalRequest, UUID(request_id)).status == outcome
        assert db.execute(text("SELECT value FROM acceptance_mutations")).scalar_one() == (
            7 if outcome == "approved" else 0)
    assert client.post("/guard/approvals/" + request_id + "/decide", json={"decision": "approved"}).status_code == 409


@pytest.mark.parametrize("name,surface", [
    ("ChatGPT", "chatgpt"), ("ChatGPT Work", "chatgpt-work"),
    ("codex", "codex"), ("Claude.ai", "claude.ai"),
    ("GitHub Copilot CLI", "copilot-cli"),
])
def test_initialized_client_attribution_reaches_audit_and_survives_refresh(audited_journey, name, surface):
    from app.modules.guard.models import GuardAuditEvent

    client, engine = audited_journey
    tokens = login(client)
    connected = rpc(client, tokens["access_token"], "initialize", params={
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": name, "version": "1"}},
        headers={"X-Claude-Surface": "codex", "User-Agent": "codex"})
    assert result(connected)["_surface"] == surface
    session = connected.headers["Mcp-Session-Id"]
    headers = {"Mcp-Session-Id": session, "X-Claude-Surface": "codex", "User-Agent": "codex"}
    with Session(engine) as db:
        credential = db.query(AgentCredentialSession).filter(
            AgentCredentialSession.access_token_hash == token_hash(tokens["access_token"])).one()
        credential_id, identity_id = credential.id, credential.agent_identity_id

    audit_session = None
    for phase in ("connect", "refresh"):
        marker = "synthetic-surface-" + phase
        result(rpc(client, tokens["access_token"], params={
            "name": "guard_activity", "arguments": {"summary": marker}}, headers=headers))
        with Session(engine) as db:
            event = db.query(GuardAuditEvent).filter(GuardAuditEvent.input_summary.contains(marker)).one()
            assert event.ai_tool == surface
            assert str(event.workspace_id) == WS
            assert event.clerk_user_id == USER and event.agent_identity_id == identity_id
            assert event.routing_meta["credential_session_id"] == credential_id
            assert str(UUID(event.hook_session_id)) == event.hook_session_id
            assert event.hook_session_id != session
            if audit_session is None:
                audit_session = event.hook_session_id
            assert event.hook_session_id == audit_session

        if phase == "connect":
            refreshed = client.post("/oauth/token", data={
                "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
            assert refreshed.status_code == 200
            assert rpc(client, tokens["access_token"], headers=headers).status_code == 401
            tokens = refreshed.json()

    with engine.begin() as db:
        db.execute(text("UPDATE agent_credential_sessions SET revoked_at = now() WHERE id = :id"),
                   {"id": credential_id})
    assert rpc(client, tokens["access_token"], headers=headers).status_code == 401
    with Session(engine) as db:
        assert db.query(GuardAuditEvent).count() == 2


@pytest.mark.parametrize("action", ["expire", "revoke"])
def test_native_credential_fixture_and_real_audit_roundtrip(audited_journey, monkeypatch, tmp_path, action):
    from app.modules.guard.models import GuardAuditEvent
    client, engine = audited_journey
    tokens = login(client)
    marker = "mcp-acceptance-" + "a" * 32
    with Session(engine) as db:
        credential = db.query(AgentCredentialSession).filter(
            AgentCredentialSession.access_token_hash == token_hash(tokens["access_token"])).one()
        credential_id, identity_id = credential.id, credential.agent_identity_id
        original_expiry = credential.expires_at
        schema = db.execute(text("SELECT current_schema()")).scalar()
    path = Path(__file__).resolve().parents[3] / "tools/mcp-acceptance/fixture.py"
    spec = importlib.util.spec_from_file_location("mcp_acceptance_fixture", path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    monkeypatch.setenv("MCP_ACCEPTANCE_DATABASE_URL", engine.url.set(
        query={"options": "-csearch_path=" + schema}).render_as_string(hide_password=False))
    monkeypatch.setenv("MCP_ACCEPTANCE_MARKER", marker)
    options = ["--workspace", WS, "--identity", identity_id, "--credential", credential_id,
               "--snapshot", str(tmp_path / "snapshot.json"), "--allow-disposable-fixture"]
    assert fixture.main([action, *options]) == 0
    assert rpc(client, tokens["access_token"]).status_code == 401
    if action == "expire":
        refreshed = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200
        result(rpc(client, refreshed.json()["access_token"], params={"name": "guard_activity", "arguments": {"summary": marker}}))
        with Session(engine) as db:
            event = db.query(GuardAuditEvent).one()
            assert event.clerk_user_id == USER and event.agent_identity_id == identity_id
            assert event.routing_meta["credential_session_id"] == credential_id
            renewed_expiry = db.get(AgentCredentialSession, credential_id).expires_at
            assert renewed_expiry > original_expiry
        assert rpc(client, tokens["access_token"]).status_code == 401
        assert client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}).status_code == 401
        assert fixture.main(["verify-refresh", *options]) == 0
    else:
        assert fixture.main(["verify-revoked", *options]) == 0
    assert fixture.main(["restore", *options]) == 0
    with Session(engine) as db:
        credential = db.get(AgentCredentialSession, credential_id)
        assert credential.expires_at == (renewed_expiry if action == "expire" else original_expiry)
        assert credential.revoked_at is None
