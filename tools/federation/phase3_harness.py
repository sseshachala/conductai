"""Real auth, database, JWT verification, MCP dispatch and Guard audit writes.

Only JWKS document retrieval is injected; no policy/auth/resolver stubs.
Run with the same disposable DB safeguards as phase2_harness.py.
"""
import json
import os
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import phase2_harness


def main():
    fixture = phase2_harness.main()
    if os.environ.get("FEDERATION_RESTRICTED_TEST") == "1":
        from sqlalchemy import event, text
        from app.core.database import engine
        with engine.begin() as db:
            if not db.execute(text("SELECT 1 FROM pg_roles WHERE rolname='conduct_federation_runtime'")).scalar():
                db.execute(text("CREATE ROLE conduct_federation_runtime NOLOGIN"))
            db.execute(text("GRANT USAGE ON SCHEMA public TO conduct_federation_runtime"))
            db.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO conduct_federation_runtime"))
            db.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO conduct_federation_runtime"))
        engine.dispose()
        def restricted_connection(connection, _record):
            cursor = connection.cursor()
            cursor.execute("SET ROLE conduct_federation_runtime")
            connection.commit()
            cursor.close()
        event.listen(engine, "connect", restricted_connection)
        with engine.connect() as db:
            assert db.execute(text("SELECT current_user")).scalar() == "conduct_federation_runtime"
            assert db.execute(text("SELECT row_security_active('federation_grants')")).scalar() is True
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.database import SessionLocal
    from app.models.audit_log import AuditLog
    from app.modules.guard.models import GuardAuditEvent
    from app.modules.auth.federation.router import router
    from app.modules.auth.federation.delegation_router import router as authorization_router
    from app.modules.auth.federation.delegation_models import FederationGrant
    from app.modules.auth.federation import verifier
    from app.modules.auth.federation.network import VerificationUnavailable
    from app.mcp.http import router as mcp_router
    from app.modules.guard.routers.mcp import router as legacy_router
    import app.tools.registrations.guard  # noqa: F401

    app = FastAPI()
    for routes in (router, authorization_router, mcp_router, legacy_router):
        app.include_router(routes)
    assert not app.dependency_overrides
    ws = fixture["workspace"]
    prefix = f"/workspaces/{ws}/federation"
    headers = fixture["headers"]
    config = dict(fixture["config"], status="active")
    principal_a, principal_b, binding_id, grant_a, grant_b = (str(uuid4()) for _ in range(5))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), kid="fixture")
    original_fetch = verifier.DEFAULT_CACHE.fetch
    verifier.DEFAULT_CACHE.fetch = lambda _: {"keys": [jwk]}

    def evidence(subject, **overrides):
        claims = dict(iss=config["issuer"], aud=config["audience"], sub=subject,
                      exp=int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()))
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "fixture", "typ": "at+jwt"})

    def caller_headers(subject="alice", **claims):
        return {**headers, "Conduct-Federation-Connection": fixture["connection"],
                "Conduct-Subject-Token": evidence(subject, **claims), "Mcp-Session-Id": "shared-transport"}

    def rpc(tool="guard_check_prompt"):
        return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": tool, "arguments": {"prompt": "Say hello", "model": "fixture"}}}

    def put(client, path, body, expected=200, auth=None):
        response = client.put(path, headers=auth or headers, json=body)
        assert response.status_code == expected, (path, response.status_code, response.text)
        return response.json()

    try:
        with TestClient(app) as client:
            # Existing service credential works before any federation binding.
            for endpoint in ("/mcp", "/guard/mcp"):
                response = client.post(endpoint, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
                assert response.status_code == 200, response.text
            put(client, fixture["path"], {"expected_revision": 2, "config": config})
            both = ["mcp.guard_check", "mcp.guard_check_prompt"]
            base = {"expected_revision": 0, "status": "active", "actions": both}
            binding = dict(base, caller_id=fixture["caller_id"], connection_id=fixture["connection"])
            put(client, prefix + "/bindings/" + binding_id, binding, 403, fixture["developer_headers"])
            put(client, prefix + "/bindings/" + binding_id, binding)
            principal = dict(base, issuer=config["issuer"], subject="alice", kind="human")
            put(client, prefix + "/principals/" + principal_a, principal)
            put(client, prefix + "/principals/" + principal_b,
                dict(principal, subject="bob", actions=["mcp.guard_check"]))
            grant = dict(base, binding_id=binding_id, principal_id=principal_a,
                         expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
            put(client, prefix + "/grants/" + grant_a, grant)
            put(client, prefix + "/grants/" + grant_b,
                dict(grant, principal_id=principal_b, actions=["mcp.guard_check"]))

            for endpoint in ("/mcp", "/guard/mcp"):
                def call(h, tool="guard_check_prompt"):
                    return client.post(endpoint, headers=h, json=rpc(tool))
                assert call(headers).status_code == 401
                assert call(caller_headers("unknown")).status_code == 403
                assert call(caller_headers("bob")).status_code == 403
                assert call(caller_headers(aud="other-audience")).status_code == 401
                assert call(caller_headers(exp=1)).status_code == 401
                assert call(caller_headers(), "conduct_run_workflow").status_code == 403
                assert call({**caller_headers(), "Conduct-Federation-Connection": str(uuid4())}).status_code == 403
                response = call(caller_headers())
                assert response.status_code == 200, response.text
                assert "result" in response.json() and not response.json()["result"].get("isError"), response.text
                assert "ok" in response.json()["result"]["content"][0]["text"], response.text
                duplicates = list(caller_headers().items()) + [("Conduct-Subject-Token", evidence("bob"))]
                assert call(duplicates).status_code == 401

            # Concurrent identities share a transport identifier, never authority.
            def concurrent_call(subject):
                with TestClient(app) as separate:
                    return separate.post("/mcp", headers=caller_headers(subject), json=rpc()).status_code
            with ThreadPoolExecutor(max_workers=4) as pool:
                statuses = list(pool.map(concurrent_call, ["alice", "bob", "alice", "bob"]))
            assert statuses == [200, 403, 200, 403], statuses
            from starlette.datastructures import Headers
            from app.modules.auth.federation.mcp_ingress import prepare
            from app.modules.auth.federation.resolver import FederationDenied, recheck
            context = prepare(SimpleNamespace(headers=Headers(caller_headers())), str(ws),
                              headers["Authorization"][7:], rpc())
            put(client, prefix + "/grants/" + grant_a, dict(grant, expected_revision=1, status="disabled"))
            assert client.post("/mcp", headers=caller_headers(), json=rpc()).status_code == 403
            with SessionLocal() as db:
                try:
                    recheck(db, context, "mcp.guard_check_prompt")
                except FederationDenied as error:
                    assert error.code == "federation_grant_invalid"
                else:
                    raise AssertionError("Previously verified context survived grant revocation")
            put(client, prefix + "/grants/" + grant_a, dict(grant, expected_revision=2))
            # Reconfigure trust to invalidate cached evidence/keys, then simulate outage.
            put(client, fixture["path"], {"expected_revision": 3, "config": config})
            def unavailable(_):
                raise VerificationUnavailable("fixture_outage")
            verifier.DEFAULT_CACHE.fetch = unavailable
            assert client.post("/mcp", headers=caller_headers(), json=rpc()).status_code == 503
            put(client, fixture["path"], {"expected_revision": 4, "config": dict(config, status="disabled")})
            assert client.post("/mcp", headers=caller_headers(), json=rpc()).status_code == 403
            assert client.post("/mcp", headers=headers, json=rpc()).status_code == 401
            put(client, prefix + "/bindings/" + binding_id, dict(binding, expected_revision=1, status="disabled"))
            assert client.post("/mcp", headers=headers, json=rpc()).status_code == 403

        with SessionLocal() as db:
            from app.core.workspace_context import set_workspace_rls
            set_workspace_rls(db, ws)
            decisions = db.query(AuditLog).filter(AuditLog.workspace_id == ws,
                                                AuditLog.action == "federation.guard.decision").all()
            assert len(decisions) == 4, len(decisions)
            assert {row.meta["principal_id"] for row in decisions} == {principal_a}
            for row in decisions:
                event = db.query(GuardAuditEvent).filter(GuardAuditEvent.id == row.resource_id).one()
                assert event.decision == "allowed" and event.workspace_id == ws
                assert "subject" not in row.meta and "token" not in json.dumps(row.meta)
            assert db.query(FederationGrant).filter(FederationGrant.workspace_id == ws).count() == 2
            if os.environ.get("FEDERATION_RESTRICTED_TEST") == "1":
                db.commit()
                set_workspace_rls(db, fixture["other"])
                assert db.query(FederationGrant).filter(FederationGrant.workspace_id == ws).count() == 0
        print("PASS: both MCP endpoints, two identities, concurrent isolation, missing evidence, expiry, revocation, outage and linked audit")
    finally:
        verifier.DEFAULT_CACHE.fetch = original_fetch


if __name__ == "__main__":
    main()
