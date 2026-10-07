"""Provider rejected the profile's credential → 424 naming the profile, not a blanket 502."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from app.modules.guard import gateway_handler
from app.modules.guard.gateway_config import GatewayProfileV2, LiteLLMSDKTarget
from app.modules.guard.gateway_runtime import ResolvedV2
from app.runtime import gateway_transports
from app.runtime.attempt_coordinator import AllAttemptsFailed, AttemptCoordinator, AttemptRecord

REV = UUID("22222222-2222-2222-2222-222222222222")


def _resolved() -> ResolvedV2:
    target = LiteLLMSDKTarget(
        id="primary", transport="litellm_sdk", provider="anthropic",
        model="claude-sonnet-4-6", credential_ref="vault://11111111-1111-1111-1111-111111111111/anthropic",
    )
    profile = GatewayProfileV2(
        name="claude-litellm", model_alias="claude-litellm", accepts=["anthropic_messages"],
        targets=[target],
    )
    return ResolvedV2(revision_id=REV, profile=profile)


def _attempt(status: int | None) -> AttemptRecord:
    return AttemptRecord(
        target_id="primary", transport="native_http", provider_or_integration="anthropic",
        started_at_monotonic=0.0, completed_at_monotonic=1.0, succeeded=False,
        error_class="HTTPStatusError", error_summary="upstream returned", upstream_status=status,
    )


# ── coordinator records the provider status ─────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_coordinator_records_upstream_status_from_httpx_error() -> None:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = httpx.HTTPStatusError("upstream returned 401", request=req, response=httpx.Response(401, request=req))
    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=err)
    with pytest.raises(AllAttemptsFailed) as excinfo:
        await AttemptCoordinator(sdk_transport=sdk).execute(
            resolved=_resolved(), operation="anthropic_messages",
            payload={"messages": [{"role": "user", "content": "hi"}]},
            credential_resolver=lambda ref: "sk-fake",
        )
    assert excinfo.value.attempts[-1].upstream_status == 401


# ── handler maps it to 424 ──────────────────────────────────────────────


async def _run(monkeypatch: pytest.MonkeyPatch, status: int | None) -> HTTPException:
    coord = MagicMock()
    coord.execute = AsyncMock(side_effect=AllAttemptsFailed([_attempt(status)]))
    monkeypatch.setattr(gateway_transports, "get_coordinator", AsyncMock(return_value=coord))
    plan = SimpleNamespace(
        resolved=_resolved(), operation="anthropic_messages", needs_anthropic_conversion=False,
        credential_resolver=None, vendor_credential_resolver=None, dispatched=False, last_meta=None,
    )
    with pytest.raises(HTTPException) as excinfo:
        await gateway_handler._execute_v2(plan=plan, body={"messages": []})
    return excinfo.value


@pytest.mark.anyio("asyncio")
@pytest.mark.parametrize("status", [401, 403])
async def test_credential_rejected_is_424_naming_profile(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    exc = await _run(monkeypatch, status)
    assert exc.status_code == 424
    assert "claude-litellm" in exc.detail and f"HTTP {status}" in exc.detail
    assert "rejected the credential" in exc.detail


@pytest.mark.anyio("asyncio")
@pytest.mark.parametrize("status", [500, None])
async def test_other_failures_stay_502(monkeypatch: pytest.MonkeyPatch, status: int | None) -> None:
    assert (await _run(monkeypatch, status)).status_code == 502
