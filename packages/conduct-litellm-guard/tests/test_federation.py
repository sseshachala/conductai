import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from conduct_litellm_guard import ConductGuard
from conduct_litellm_guard._client import GuardCheckClient, IdentityRequiredError


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [
    (401, {}), (403, {}), (401, []), (403, "invalid credentials"),
    (503, {"error": {"data": {"identity_required": True}}}),
    (200, {"result": {"isError": True, "structuredContent": {"identity_required": True}}}),
])
async def test_identity_errors_never_fail_open(status, body):
    guard = ConductGuard(agent_token="cond_api_fixture", unreachable_fallback="fail_open")
    guard._client._client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json=body)))
    try:
        assert (await guard.check(data={}, call_type="completion")).verdict == "block"
    finally:
        await guard.close()


@pytest.mark.asyncio
async def test_metadata_cannot_supply_identity():
    pytest.importorskip("litellm")
    guard = ConductGuard(agent_token="cond_api_fixture", federation_connection=str(uuid4()),
                         unreachable_fallback="fail_open")
    guard._client.guard_check = AsyncMock(return_value="ok")
    data = {"metadata": {"conduct_subject": "spoofed"}, "user": "alice"}
    try:
        decision = await guard.check(data=data, call_type="completion",
                                     auth=SimpleNamespace(metadata=data["metadata"]))
        assert decision.verdict == "block"
        guard._client.guard_check.assert_not_called()
    finally:
        await guard.close()


@pytest.mark.asyncio
async def test_private_auth_handoff_is_request_local_and_not_serialized():
    pytest.importorskip("litellm")
    from litellm.proxy._types import UserAPIKeyAuth
    from conduct_litellm_guard.auth import with_subject_token, subject_token
    auth = with_subject_token(UserAPIKeyAuth(user_id="alice"), "synthetic-evidence")
    assert UserAPIKeyAuth.model_validate(auth) is auth
    assert "synthetic-evidence" not in auth.model_dump_json()
    assert "synthetic-evidence" not in repr(auth)
    assert subject_token(UserAPIKeyAuth(user_id="alice")) is None
    guard = ConductGuard(agent_token="cond_api_fixture", federation_connection=str(uuid4()),
                         unreachable_fallback="fail_open")
    guard._client.guard_check = AsyncMock(side_effect=TimeoutError("secret-must-not-escape"))
    try:
        decision = await guard.check(data={}, call_type="completion", auth=auth)
        assert decision.verdict == "block"
        assert "secret" not in decision.raw
        assert guard._client.guard_check.call_args.kwargs["subject_token"] == "synthetic-evidence"
    finally:
        await guard.close()


@pytest.mark.asyncio
async def test_evidence_in_headers_only():
    client = GuardCheckClient(api_url="https://conduct.invalid", agent_token="cond_api_fixture")
    def check(request):
        assert request.headers["Conduct-Subject-Token"] == "synthetic-evidence"
        assert request.headers["Authorization"] == "Bearer cond_api_fixture"
        assert "synthetic-evidence" not in request.content.decode()
        return httpx.Response(200, json={"result": {"content": [{"type": "text", "text": "ok"}]}})
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(check))
    try:
        assert await client.guard_check(prompt="hello", subject_token="synthetic-evidence",
                                        federation_connection=str(uuid4())) == "ok"
    finally:
        await client.aclose()
