"""Wiring tests for ``maybe_handle_v2`` (#2001 review fix).

Locks the invariants the flag-based rollout depends on:

- Flag off → return None (v1 keeps serving).
- Flag on but no environment header → None.
- Flag on, no ``model`` in body → None.
- Flag on, streaming request → None (streaming wiring is a follow-up).
- Flag on, unwired operation → None.
- Flag on, no v2 binding → 400 with a specific ``unknown_model`` error
  (not fall-through — v2-enabled workspace explicitly published
  something, unknown alias is a client bug).
- Flag on, binding exists, coordinator succeeds → 200 with response +
  routing_meta captures revision_id + winning target.
- Flag on, binding exists, coordinator fails all attempts → 502 with
  attempt summary + routing_meta populated for audit.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.modules.guard.gateway_config import GatewayProfileV2, LiteLLMSDKTarget
from app.modules.guard.gateway_runtime import ResolvedV2
from app.runtime.attempt_coordinator import (
    AllAttemptsFailed,
    AttemptRecord,
    CoordinatorResult,
)
from app.runtime.v2_request_handler import maybe_handle_v2


ENV = "11111111-1111-1111-1111-111111111111"
REV = UUID("22222222-2222-2222-2222-222222222222")
WS = "33333333-3333-3333-3333-333333333333"


def _profile() -> GatewayProfileV2:
    return GatewayProfileV2(
        name="prod",
        model_alias="coding",
        accepts=["anthropic_messages"],
        timeout_seconds=30,
        max_attempts=2,
        targets=[
            LiteLLMSDKTarget(
                id="primary",
                transport="litellm_sdk",
                provider="anthropic",
                model="claude-sonnet-4-6",
                credential_ref=f"vault://{ENV}/anthropic",
            ),
        ],
    )


def _fake_request() -> Any:
    r = MagicMock()
    r.headers = {}
    return r


@pytest.fixture
def flag_on(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "guard_gateway_profile_v2", True)


@pytest.mark.anyio("asyncio")
async def test_flag_off_returns_none():
    """v1 stays authoritative when the flag is off — matches the
    'rollback via env-var flip' contract."""
    from app.core.config import settings
    assert settings.guard_gateway_profile_v2 is False  # default
    result = await maybe_handle_v2(
        request=_fake_request(),
        db=MagicMock(),
        workspace_id=WS,
        environment_id=ENV,
        body={"model": "coding", "messages": []},
        provider="anthropic",
        upstream_path="/v1/messages",
        routing_meta_sink={},
    )
    assert result is None


@pytest.mark.anyio("asyncio")
async def test_missing_environment_header_returns_none(flag_on):
    """v2 keys on env; if the request didn't pin one, fall through."""
    result = await maybe_handle_v2(
        request=_fake_request(),
        db=MagicMock(),
        workspace_id=WS,
        environment_id=None,
        body={"model": "coding", "messages": []},
        provider="anthropic",
        upstream_path="/v1/messages",
        routing_meta_sink={},
    )
    assert result is None


@pytest.mark.anyio("asyncio")
async def test_missing_model_field_returns_none(flag_on):
    result = await maybe_handle_v2(
        request=_fake_request(),
        db=MagicMock(),
        workspace_id=WS,
        environment_id=ENV,
        body={"messages": []},
        provider="anthropic",
        upstream_path="/v1/messages",
        routing_meta_sink={},
    )
    assert result is None


@pytest.mark.anyio("asyncio")
async def test_streaming_request_returns_none(flag_on):
    """Streaming path lands in a follow-up commit because the
    'no attempt N+1 after first byte' invariant lives in
    ``_stream_chunks``. Until that path is wired, fall through."""
    result = await maybe_handle_v2(
        request=_fake_request(),
        db=MagicMock(),
        workspace_id=WS,
        environment_id=ENV,
        body={"model": "coding", "messages": [], "stream": True},
        provider="anthropic",
        upstream_path="/v1/messages",
        routing_meta_sink={},
    )
    assert result is None


@pytest.mark.anyio("asyncio")
async def test_unwired_operation_returns_none(flag_on):
    """Any URL the operation-map doesn't yet cover → fall through so
    behavior for that endpoint is unchanged."""
    result = await maybe_handle_v2(
        request=_fake_request(),
        db=MagicMock(),
        workspace_id=WS,
        environment_id=ENV,
        body={"model": "coding"},
        provider="anthropic",
        upstream_path="/v1/some-unwired-path",
        routing_meta_sink={},
    )
    assert result is None


@pytest.mark.anyio("asyncio")
async def test_no_binding_returns_400_unknown_model(flag_on):
    """A workspace on the v2 flag has explicitly opted in. Unknown
    alias is a client bug, not a fall-through case."""
    with patch(
        "app.runtime.v2_request_handler.resolve_v2",
        return_value=None,
    ):
        result = await maybe_handle_v2(
            request=_fake_request(),
            db=MagicMock(),
            workspace_id=WS,
            environment_id=ENV,
            body={"model": "does-not-exist", "messages": []},
            provider="anthropic",
            upstream_path="/v1/messages",
            routing_meta_sink={},
        )
    assert result is not None
    assert result.status_code == 400
    assert b"unknown_model" in result.body
    assert b"does-not-exist" in result.body


@pytest.mark.anyio("asyncio")
async def test_operation_not_accepted_returns_400(flag_on):
    """Profile is published but for a different operation. Client asked
    for chat_completions on an anthropic_messages-only profile → 400
    surfacing the mismatch."""
    resolved = ResolvedV2(revision_id=REV, profile=_profile())
    with patch(
        "app.runtime.v2_request_handler.resolve_v2",
        return_value=resolved,
    ):
        result = await maybe_handle_v2(
            request=_fake_request(),
            db=MagicMock(),
            workspace_id=WS,
            environment_id=ENV,
            body={"model": "coding", "messages": []},
            provider="openai",
            upstream_path="/v1/chat/completions",
            routing_meta_sink={},
        )
    assert result is not None
    assert result.status_code == 400
    assert b"operation_not_accepted" in result.body


@pytest.mark.anyio("asyncio")
async def test_happy_path_returns_200_and_pins_routing_meta(flag_on):
    """Coordinator succeeds → 200 JSON response + routing_meta populated
    with revision id + winning target so the audit row can attribute
    the request to a specific published revision."""
    resolved = ResolvedV2(revision_id=REV, profile=_profile())

    fake_response = SimpleNamespace(
        model_dump=lambda: {"content": [{"type": "text", "text": "pong"}]}
    )
    coord_result = CoordinatorResult(
        response=fake_response,
        revision_id=REV,
        attempts=[AttemptRecord(
            target_id="primary", transport="litellm_sdk",
            provider_or_integration="anthropic",
            started_at_monotonic=0.0, completed_at_monotonic=0.5,
            succeeded=True, error_class=None, error_summary=None,
        )],
        winning_target_id="primary",
    )
    sink: dict = {}
    with patch(
        "app.runtime.v2_request_handler.resolve_v2",
        return_value=resolved,
    ), patch(
        "app.runtime.v2_request_handler._make_credential_resolver",
        return_value=lambda ref: "sk-fake",
    ), patch(
        "app.runtime.v2_request_handler._COORDINATOR.execute",
        AsyncMock(return_value=coord_result),
    ):
        result = await maybe_handle_v2(
            request=_fake_request(),
            db=MagicMock(),
            workspace_id=WS,
            environment_id=ENV,
            body={"model": "coding", "messages": [{"role": "user", "content": "hi"}]},
            provider="anthropic",
            upstream_path="/v1/messages",
            routing_meta_sink=sink,
        )
    assert result is not None
    assert result.status_code == 200
    # routing_meta captures the pinned revision + winning target for audit.
    assert sink["v2"]["revision_id"] == str(REV)
    assert sink["v2"]["winning_target_id"] == "primary"
    assert len(sink["v2"]["attempts"]) == 1
    assert sink["v2"]["attempts"][0]["succeeded"] is True


@pytest.mark.anyio("asyncio")
async def test_all_attempts_failed_returns_502_with_attempt_summary(flag_on):
    """Every target failed. Fail-closed 502 with attempt list pinned in
    routing_meta so the audit row shows which targets were tried."""
    resolved = ResolvedV2(revision_id=REV, profile=_profile())

    failing_attempts = [AttemptRecord(
        target_id="primary", transport="litellm_sdk",
        provider_or_integration="anthropic",
        started_at_monotonic=0.0, completed_at_monotonic=1.0,
        succeeded=False, error_class="RuntimeError", error_summary="upstream 503",
    )]
    sink: dict = {}
    with patch(
        "app.runtime.v2_request_handler.resolve_v2",
        return_value=resolved,
    ), patch(
        "app.runtime.v2_request_handler._make_credential_resolver",
        return_value=lambda ref: "sk-fake",
    ), patch(
        "app.runtime.v2_request_handler._COORDINATOR.execute",
        AsyncMock(side_effect=AllAttemptsFailed(failing_attempts)),
    ):
        result = await maybe_handle_v2(
            request=_fake_request(),
            db=MagicMock(),
            workspace_id=WS,
            environment_id=ENV,
            body={"model": "coding", "messages": []},
            provider="anthropic",
            upstream_path="/v1/messages",
            routing_meta_sink=sink,
        )
    assert result is not None
    assert result.status_code == 502
    assert b"upstream_unavailable" in result.body
    # Attempt summary is pinned even on failure so the audit row shows
    # which targets we tried and why each failed.
    assert sink["v2"]["revision_id"] == str(REV)
    assert sink["v2"]["winning_target_id"] is None
    assert sink["v2"]["attempts"][0]["error_class"] == "RuntimeError"
