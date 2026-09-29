"""Real LiteLLM proxy -> Conduct HTTP/MCP -> PostgreSQL, no Gateway routing."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import FastAPI, Request

from http_fixture import Fixture, free_port, serve


def main():
    fixture = Fixture()
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardPolicyCache, GuardAuditEvent
    from app.models.audit_log import AuditLog
    with SessionLocal() as db:
        db.add(GuardPolicyCache(workspace_id=fixture.base["workspace"], persona="proxy",
                               version_hash="fixture-rule-v1", payload=[{
                                   "id": "fixture-block", "action": "block", "gates": ["prompt"],
                                   "match_prompt": "fixture-prohibited", "match_pattern": "fixture-prohibited",
                                   "message": "Fixture prompt denied", "match_tool": "*",
                               }]))
        db.commit()
    provider = FastAPI()
    received = []
    @provider.post("/v1/chat/completions")
    async def completion(request: Request):
        body = await request.json()
        assert not any("conduct-subject" in key.lower() for key in request.headers)
        assert "at+jwt" not in json.dumps(body)
        received.append(body)
        return {"id": "fixture-completion", "object": "chat.completion", "created": 1, "model": "fixture",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"},
                             "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}
    proxy = None
    try:
        with serve(fixture.app) as conduct, serve(provider) as upstream, tempfile.TemporaryDirectory() as directory:
            root = Path(__file__).resolve().parents[2]
            env = {k: v for k, v in os.environ.items() if not any(x in k for x in ("API_KEY", "BASE_URL", "TOKEN"))}
            env.update(CONDUCT_API_URL=conduct, CONDUCT_AGENT_TOKEN=fixture.base["headers"]["Authorization"][7:],
                       CONDUCT_FEDERATION_CONNECTION=fixture.base["connection"], FIXTURE_JWK=json.dumps(fixture.jwk),
                       FIXTURE_ISSUER=fixture.config["issuer"], FIXTURE_AUDIENCE=fixture.config["audience"],
                       PYTHONPATH=str(root / "packages/conduct-litellm-guard/src") + os.pathsep + str(Path(__file__).parent),
                       LITELLM_LOCAL_MODEL_COST_MAP="True")
            config = {
                "model_list": [{"model_name": "fixture", "litellm_params": {
                    "model": "openai/fixture", "api_key": "synthetic-provider", "api_base": upstream + "/v1"}}],
                "general_settings": {"custom_auth": "pilot_proxy.authenticate", "disable_error_logs": True},
                "guardrails": [{"guardrail_name": "conduct", "litellm_params": {
                    "guardrail": "pilot_proxy.PilotGuard", "mode": "pre_call", "default_on": True,
                    "unreachable_fallback": "fail_open"}}],
            }
            path = Path(directory) / "config.yaml"
            path.write_text(json.dumps(config))
            port = free_port()
            executable = os.environ.get("FEDERATION_LITELLM", "litellm")
            # Log only on fixture failures; all credentials are disposable/synthetic.
            with (Path(directory) / "proxy.log").open("w+") as logfile:
                proxy = subprocess.Popen([executable, "--config", str(path), "--host", "127.0.0.1", "--port", str(port)],
                                         env=env, stdout=logfile, stderr=logfile)
                url = f"http://127.0.0.1:{port}"
                for _ in range(120):
                    try:
                        if httpx.get(url + "/health/liveliness", timeout=1).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if proxy.poll() is not None:
                        raise AssertionError("LiteLLM exited before readiness")
                    time.sleep(.5)
                else:
                    raise AssertionError("LiteLLM readiness timeout")
                def call(subject, prompt):
                    return httpx.post(url + "/v1/chat/completions", timeout=30,
                                      headers={"Authorization": "Bearer " + fixture.token(subject)},
                                      json={"model": "fixture", "messages": [{"role": "user", "content": prompt}]})
                with ThreadPoolExecutor(max_workers=2) as pool:
                    allowed = pool.submit(call, "alice", "Hello")
                    blocked = pool.submit(call, "bob", "fixture-prohibited")
                    a, b = allowed.result(), blocked.result()
                assert a.status_code == 200, (a.status_code, a.text)
                assert b.status_code in (400, 403), (b.status_code, b.text)
                assert len(received) == 1
                denied = call("unknown", "Hello")
                assert denied.status_code in (400, 403) and len(received) == 1, denied.text
                # Missing evidence at Conduct must not bypass even with fail_open.
                with SessionLocal() as db:
                    from app.modules.auth.federation.delegation_models import FederationGrant
                    grant = db.get(FederationGrant, fixture.grants["alice"])
                    grant.status = "disabled"
                    db.commit()
                assert call("alice", "Hello").status_code in (400, 403)
                assert len(received) == 1
            with SessionLocal() as db:
                rows = db.query(AuditLog).filter(AuditLog.workspace_id == fixture.base["workspace"],
                                                AuditLog.action == "federation.guard.decision").all()
                decisions = {}
                for row in rows:
                    event = db.get(GuardAuditEvent, row.resource_id)
                    decisions[row.meta["principal_id"]] = event.decision
                    assert "subject" not in row.meta and "token" not in json.dumps(row.meta)
                assert decisions == {fixture.principals["alice"]: "allowed", fixture.principals["bob"]: "blocked"}, decisions
            print("PASS: real LiteLLM HTTP proxy, concurrent users, policy allow/block, revocation, attribution, no denied inference")
    finally:
        if proxy:
            proxy.terminate()
            try:
                proxy.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proxy.kill()
                proxy.wait()
        fixture.close()


if __name__ == "__main__":
    main()
