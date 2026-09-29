"""Real Gateway HTTP, persisted run propagation and worker expiry/revocation checks."""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request

from http_fixture import Fixture, serve


def main():
    fixture = Fixture(actions=("mcp.guard_check_prompt", "gateway.inference", "workflows.run"))
    from app.core.crypto import encrypt
    from app.core.database import SessionLocal
    from app.models.environment import Environment
    from app.models.integration import Integration
    from app.models.run import Run, RunEvent
    from app.models.workflow import Workflow, WorkflowVersion
    from app.modules.agent_identity.models import AgentIdentity
    from app.modules.agent_identity.run_token_model import AgentRunToken
    from app.modules.auth.federation.delegation_models import FederationGrant
    from app.modules.auth.federation.workflow import load_run_context, EVENT_KIND
    from app.modules.guard.models import GuardAuditEvent
    from app.modules.guard.routers.gateway_proxy import router as gateway
    from app.routers.runs import router as runs
    from app.runtime.executor import execute_run
    from app.modules.auth.federation.attribution import attribution
    fixture.app.include_router(gateway)
    fixture.app.include_router(runs)
    ws = fixture.base["workspace"]
    env_id, workflow_id, version_id = uuid4(), uuid4(), uuid4()
    unbound_token = "cond_api_" + secrets.token_hex(32)
    with SessionLocal() as db:
        db.add(Environment(id=env_id, workspace_id=ws, name="Fixture"))
        db.add(AgentIdentity(id=str(uuid4()), workspace_id=ws, name="Unbound fixture",
                            token_prefix=unbound_token[:13], token_encrypted=encrypt({"token": unbound_token}),
                            token_type="api", created_at=datetime.now(timezone.utc)))
        db.add(Workflow(id=workflow_id, workspace_id=ws, name="Federation fixture",
                        environment_id=env_id, guard_enabled=False, agent_identity_required=False))
        db.flush()
        db.add(WorkflowVersion(id=version_id, workflow_id=workflow_id, graph={
            "nodes": [{"id": "start", "data": {"type": "trigger", "label": "Start", "config": {}}}],
            "edges": [],
        }))
        db.flush()
        db.get(Workflow, workflow_id).current_version_id = version_id
        db.commit()
    provider, received = FastAPI(), []
    @provider.post("/v1/chat/completions")
    async def completion(request: Request):
        body = await request.json()
        assert "conduct-subject-token" not in request.headers
        assert "conduct-federation-connection" not in request.headers
        assert not request.headers.get("authorization", "").startswith("Bearer cond_")
        received.append(body)
        return {"id": "fixture", "object": "chat.completion", "created": 1, "model": "fixture",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}
    try:
        with serve(provider) as upstream, serve(fixture.app) as api:
            with SessionLocal() as db:
                db.add(Integration(workspace_id=ws, environment_id=env_id, service="proxy_config",
                                   handle="proxy_config", auth_method="api_key",
                                   encrypted_credentials=encrypt({"LLM_UPSTREAM": upstream,
                                                                  "LLM_UPSTREAM_API_KEY": "synthetic-provider"})))
                db.commit()
            path = api + "/gateway/v1/openai/v1/chat/completions"
            def infer(headers):
                return httpx.post(path, timeout=30, headers={**headers, "x-conductai-environment-id": str(env_id)},
                                  json={"model": "fixture", "messages": [{"role": "user", "content": "Hello"}]})
            unbound = {"Authorization": "Bearer " + unbound_token, "X-Workspace-Id": str(ws)}
            assert infer(fixture.base["headers"]).status_code == 401
            assert infer(fixture.headers("unknown")).status_code == 403
            assert infer(fixture.headers(exp=1)).status_code == 401
            assert infer(fixture.headers(aud="untrusted-audience")).status_code == 401
            assert infer({**fixture.headers(), "Conduct-Federation-Connection": str(uuid4())}).status_code == 403
            assert not received
            for headers in (unbound, fixture.headers("alice"), fixture.headers("bob")):
                response = infer(headers)
                assert response.status_code == 200, (response.status_code, response.text)
            assert len(received) == 3
            import time
            for _ in range(100):
                with SessionLocal() as db:
                    count = db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id == ws,
                                                            GuardAuditEvent.source == "gateway").count()
                if count >= 3:
                    break
                time.sleep(.05)
            with SessionLocal() as db:
                events = db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id == ws,
                                                         GuardAuditEvent.source == "gateway").all()
                contexts = [attribution(row.routing_meta) for row in events]
                assert {c["principal_id"] for c in contexts if c} == set(fixture.principals.values()), contexts
                assert any(c is None for c in contexts)
            run_url = api + f"/workflows/{workflow_id}/runs"
            assert httpx.post(run_url, headers=fixture.base["headers"], json={}).status_code == 401
            def create(headers):
                result = httpx.post(run_url, headers=headers,
                                    json={"initial_state": {"__manual": True, "federation": "spoofed"}}, timeout=20)
                assert result.status_code == 201, (result.status_code, result.text)
                return UUID(result.json()["id"])
            normal_run = create(unbound)
            allowed_run = create(fixture.headers("alice"))
            expired_run = create(fixture.headers("alice", exp=int((datetime.now(timezone.utc) + timedelta(seconds=3)).timestamp())))
            revoked_run = create(fixture.headers("bob"))
            # A real server-issued run token resolves only its own persisted identity.
            run_token = "cond_run_" + secrets.token_hex(16)
            with SessionLocal() as db:
                context = load_run_context(db, ws, allowed_run)
                assert str(context.principal.principal_id) == fixture.principals["alice"]
                assert load_run_context(db, fixture.base["other"], allowed_run) is None
                db.add(AgentRunToken(id=str(uuid4()), workspace_id=ws, run_id=str(allowed_run),
                    token_hash=hashlib.sha256(run_token.encode()).hexdigest(), created_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
                db.commit()
            internal = {"x-conductai-internal": run_token, "x-conductai-workspace-id": str(ws),
                        "x-conductai-run-id": str(allowed_run)}
            response = infer(internal)
            assert response.status_code == 200, (response.status_code, response.text)
            assert infer({**internal, "x-conductai-run-id": str(revoked_run)}).status_code == 403
            assert len(received) == 4
            with SessionLocal() as db:
                grant = db.get(FederationGrant, fixture.grants["bob"])
                grant.status = "disabled"
                db.commit()
            assert infer(fixture.headers("bob")).status_code == 403
            import time
            time.sleep(4)  # Expiry is real clock time, not a mocked verifier.
            for run_id in (normal_run, allowed_run, expired_run, revoked_run):
                execute_run(str(run_id))
            with SessionLocal() as db:
                for run_id in (normal_run, allowed_run):
                    run = db.get(Run, run_id)
                    assert run.status in ("succeeded", "completed"), (run.id, run.status, run.state)
                for run_id in (expired_run, revoked_run):
                    assert db.get(Run, run_id).status == "failed"
                    assert db.query(RunEvent).filter(RunEvent.run_id == run_id,
                                                     RunEvent.kind == "block_completed").count() == 0
                recorded = db.query(RunEvent).filter(RunEvent.run_id == allowed_run, RunEvent.kind == EVENT_KIND).one()
                assert recorded.payload["principal_id"] == fixture.principals["alice"]
                assert "subject" not in recorded.payload and "token" not in json.dumps(recorded.payload)
                # Approver/run-state edits cannot extend the immutable initiating evidence.
                expired = db.get(Run, expired_run)
                expired.status = "paused"
                expired.state = {"approved_by": "different-approver", "federation": "replacement"}
                db.commit()
            execute_run(str(expired_run))
            with SessionLocal() as db:
                assert db.get(Run, expired_run).status == "failed"
            # Disabling a connection blocks its bound callers, not unrelated service calls.
            from app.modules.auth.federation.models import FederationConnection
            with SessionLocal() as db:
                connection = db.get(FederationConnection, fixture.base["connection"])
                connection.config = {**connection.config, "status": "disabled"}
                connection.revision += 1
                db.commit()
            assert infer(fixture.headers("alice")).status_code == 403
            assert infer(unbound).status_code == 200
            print("PASS: Gateway configured/unconfigured, both users, no evidence forwarding, run-token binding, worker execution, expiry and revocation")
    finally:
        fixture.close()


if __name__ == "__main__":
    main()
