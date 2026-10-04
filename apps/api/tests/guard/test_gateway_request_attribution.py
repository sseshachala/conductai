import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from app.core.config import settings
from app.guard.policy_types import PolicyAction, PolicyDecision
from app.modules.guard import gateway_handler, gateway_helpers
from app.modules.guard.gateway_profile_rate_limit import ProfileRateDecision


@pytest.mark.anyio
@pytest.mark.parametrize("action,status", [("ALLOW", 429), ("BLOCK", 403), ("APPROVAL", 428)])
async def test_request_attribution_uses_resolved_token_identity_and_profile_even_when_refused(monkeypatch, action, status):
    workspace, profile, revision, identity, forged = [str(uuid4()) for _ in range(5)]
    model = "cond-abcdefgh-coding"
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": "fixture"}]}).encode()
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}
    request = Request({
        "type": "http", "method": "POST", "path": "/gateway/v1/openai/v1/responses",
        "scheme": "https", "server": ("fixture", 443),
        "headers": [(b"authorization", b"Bearer cond_agt_fixture"), (b"x-conduct-agent-id", forged.encode())],
        "query_string": b"",
    }, receive)
    monkeypatch.setattr(type(settings), "gateway_profile_v2_enabled_for", lambda self, ws: True)
    monkeypatch.setattr("app.core.auth_cache.get_auth_cache", lambda: None)
    monkeypatch.setattr(gateway_helpers, "_resolve_gateway_auth", lambda *a, **kw: SimpleNamespace(
        workspace_id=workspace, clerk_user_id="fixture-member", is_internal=False,
        agent_identity_id=identity, agent_risk_tier=None,
    ))
    monkeypatch.setattr("app.modules.auth.federation.gateway.prepare_gateway", lambda *a: None)
    monkeypatch.setattr("app.core.admission._acquire", AsyncMock(return_value=None))
    monkeypatch.setattr(gateway_helpers, "_apply_tier_resolution_owned", lambda *a: (model, None))
    monkeypatch.setattr(gateway_handler, "_build_v2_plan_owned", lambda **kw: SimpleNamespace(
        resolved=SimpleNamespace(profile_id=profile, revision_id=revision), operation="openai_responses",
    ))
    monkeypatch.setattr(gateway_helpers, "_lookup_user_email", lambda *a: "fixture@example.test")
    monkeypatch.setattr(gateway_helpers, "_lookup_workspace_trial", lambda *a: (None, None))
    monkeypatch.setattr("app.core.database.SessionLocal", MagicMock)
    monkeypatch.setattr("app.modules.guard.routers._proxy_helpers.SessionLocal", MagicMock)
    monkeypatch.setattr("app.modules.guard.approval.pending_marker", lambda req: "fixture pending")
    monkeypatch.setattr("app.core.workspace_context.set_workspace_rls", lambda *a: None)
    monkeypatch.setattr("app.guard.policy.evaluate_composed", lambda ctx: PolicyDecision(
        action=PolicyAction[action], source="rule", rule_id="fixture-rule", reason="fixture refusal",
    ))
    quota = MagicMock(return_value=ProfileRateDecision(
        limited=True, reason="Agent requests-per-minute reached.", metric="rpm", limit=2,
        current=2, scope="agent", retry_after=15,
    ))
    monkeypatch.setattr("app.modules.guard.gateway_profile_rate_limit.check_profile_rate_limit", quota)
    background = BackgroundTasks()
    response = await gateway_handler.handle_gateway_request(request, background, provider="openai",
        upstream_path="/v1/responses", auth_header_in="authorization", auth_header_out="authorization",
        bearer=True, canonical_profile=True)
    assert response.status_code == status
    audit = background.tasks[0].kwargs
    assert audit["agent_identity_id"] == identity and audit["agent_identity_id"] != forged
    assert audit["routing_meta"]["gateway_profile_id"] == profile
    assert audit["routing_meta"]["gateway_profile"] == model
    assert audit["routing_meta"]["revision_id"] == revision
    if action == "ALLOW":
        assert quota.call_args.kwargs["agent_identity_id"] == identity
        assert quota.call_args.kwargs["profile_id"] == profile
        assert response.headers["Retry-After"] == "15"
    else:
        quota.assert_not_called()
