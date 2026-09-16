"""Contract tests for AttemptCoordinator (#2001 review fix, wiring).

Locks the runtime invariants a v2 admin relies on:

- Order is priority (first target wins if healthy).
- max_attempts caps the loop.
- timeout_seconds is a total budget across all attempts.
- Each attempt records its outcome in an AttemptRecord.
- Streaming responses are handed back unwrapped so the caller can
  enforce the "no retries after first byte" invariant at the ASGI
  layer.
- HTTP passthrough targets raise UnsupportedTransport rather than
  silently degrading — the launch set is LiteLLM SDK only.
- Requesting an operation the profile does not accept fails at
  entry, not partway through the loop.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.modules.guard.gateway_config import (
    GatewayProfileV2,
    HTTPPassthroughTarget,
    LiteLLMSDKTarget,
)
from app.modules.guard.gateway_runtime import ResolvedV2
from app.runtime.attempt_coordinator import (
    AllAttemptsFailed,
    AttemptCoordinator,
    CoordinatorResult,
    UnsupportedTransport,
)


ENV = "11111111-1111-1111-1111-111111111111"
REV = UUID("22222222-2222-2222-2222-222222222222")


def _sdk_target(id: str, provider: str = "anthropic", model: str = "claude-sonnet-4-6") -> LiteLLMSDKTarget:
    return LiteLLMSDKTarget(
        id=id,
        transport="litellm_sdk",
        provider=provider,
        model=model,
        credential_ref=f"vault://{ENV}/{provider}",
    )


def _profile(*, targets, timeout_seconds: int = 30, max_attempts: int = 3) -> GatewayProfileV2:
    return GatewayProfileV2(
        name="prod",
        model_alias="coding",
        accepts=["anthropic_messages"],
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        targets=targets,
    )


def _resolved(profile: GatewayProfileV2) -> ResolvedV2:
    return ResolvedV2(revision_id=REV, profile=profile)


@pytest.mark.anyio("asyncio")
async def test_primary_target_serves_when_healthy():
    """List order = priority. Primary target's response is returned
    without touching fallback."""
    sdk = MagicMock()
    sdk.execute = AsyncMock(return_value={"content": "ok"})

    coord = AttemptCoordinator(sdk_transport=sdk)
    result = await coord.execute(
        resolved=_resolved(_profile(targets=[_sdk_target("primary"), _sdk_target("fallback")])),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-fake",
    )
    assert isinstance(result, CoordinatorResult)
    assert result.winning_target_id == "primary"
    assert result.revision_id == REV
    assert len(result.attempts) == 1
    assert result.attempts[0].succeeded is True
    assert sdk.execute.await_count == 1


@pytest.mark.anyio("asyncio")
async def test_falls_through_to_next_target_on_failure():
    """Primary fails, fallback succeeds. Both attempts recorded; the
    fallback's response is returned."""
    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=[
        TimeoutError("upstream timeout"),  # transient → fallback fires
        {"content": "ok"},
    ])

    coord = AttemptCoordinator(sdk_transport=sdk)
    result = await coord.execute(
        resolved=_resolved(_profile(targets=[_sdk_target("primary"), _sdk_target("fallback")])),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-fake",
    )
    assert result.winning_target_id == "fallback"
    assert [a.target_id for a in result.attempts] == ["primary", "fallback"]
    assert result.attempts[0].succeeded is False
    assert result.attempts[0].error_class == "TimeoutError"
    assert result.attempts[1].succeeded is True


@pytest.mark.anyio("asyncio")
async def test_max_attempts_caps_the_loop():
    """Three targets in the list, max_attempts=2. Only the first two
    are ever tried, even if both fail."""
    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=TimeoutError("everything timing out"))

    coord = AttemptCoordinator(sdk_transport=sdk)
    with pytest.raises(AllAttemptsFailed) as excinfo:
        await coord.execute(
            resolved=_resolved(_profile(
                targets=[_sdk_target("a"), _sdk_target("b"), _sdk_target("c")],
                max_attempts=2,
            )),
            operation="anthropic_messages",
            payload={"messages": [{"role": "user", "content": "hi"}]},
            credential_resolver=lambda ref: "sk-fake",
        )
    assert [a.target_id for a in excinfo.value.attempts] == ["a", "b"]
    assert sdk.execute.await_count == 2


@pytest.mark.anyio("asyncio")
async def test_timeout_budget_is_total_across_attempts():
    """A single attempt that eats the whole budget prevents further
    attempts from starting — matches the ``timeout_seconds is a total
    deadline, not per-attempt`` contract."""
    async def _slow(**kw):
        await asyncio.sleep(1.0)
        return {"content": "ok"}

    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=_slow)

    coord = AttemptCoordinator(sdk_transport=sdk)
    with pytest.raises(AllAttemptsFailed) as excinfo:
        await coord.execute(
            resolved=_resolved(_profile(
                targets=[_sdk_target("a"), _sdk_target("b")],
                timeout_seconds=1,   # matches the sleep
                max_attempts=5,
            )),
            operation="anthropic_messages",
            payload={"messages": [{"role": "user", "content": "hi"}]},
            credential_resolver=lambda ref: "sk-fake",
        )
    # First attempt exhausted the deadline; second was recorded as
    # a deadline-exceeded record, not a real attempt.
    reasons = {a.error_class for a in excinfo.value.attempts}
    assert reasons & {"TimeoutError", "DeadlineExceeded"}


@pytest.mark.anyio("asyncio")
async def test_unsupported_operation_rejected_before_loop():
    """Publishing an accepts list that doesn't include the requested
    operation is a publish-time bug, but if it slips through, refuse
    at the coordinator's entry rather than hitting each target."""
    sdk = MagicMock()
    sdk.execute = AsyncMock()

    coord = AttemptCoordinator(sdk_transport=sdk)
    with pytest.raises(ValueError, match=r"does not accept operation"):
        await coord.execute(
            resolved=_resolved(_profile(targets=[_sdk_target("a")])),
            operation="openai_responses",
            payload={"input": "hi"},
            credential_resolver=lambda ref: "sk-fake",
        )
    sdk.execute.assert_not_awaited()


@pytest.mark.anyio("asyncio")
async def test_http_passthrough_target_raises_unsupported_transport():
    """Launch set is LiteLLM SDK only. If a passthrough target is
    published and then hit at request time, fail loudly with
    ``UnsupportedTransport`` — not a fall-through to the legacy proxy
    path, which would silently downgrade the guarantees the admin
    published against."""
    passthrough = HTTPPassthroughTarget(
        id="via-portkey",
        transport="http_passthrough",
        integration="portkey",
        model="claude-sonnet-4-6",
        credential_ref=f"vault://{ENV}/portkey",
    )
    sdk = MagicMock()
    sdk.execute = AsyncMock()

    coord = AttemptCoordinator(sdk_transport=sdk)
    with pytest.raises(UnsupportedTransport):
        await coord.execute(
            resolved=_resolved(_profile(targets=[passthrough])),
            operation="anthropic_messages",
            payload={"messages": [{"role": "user", "content": "hi"}]},
            credential_resolver=lambda ref: "sk-fake",
        )


@pytest.mark.anyio("asyncio")
async def test_credential_resolver_and_target_forwarded_to_sdk_per_attempt():
    """The coordinator passes the caller's ``credential_resolver`` and
    the specific ``target`` through to the SDK transport on each
    attempt. LiteLLMTransport is what actually invokes the resolver
    (locked separately in test_litellm_transport). Here we just verify
    the coordinator delegates cleanly per attempt."""
    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=[
        TimeoutError("primary transient timeout"),
        {"content": "served"},
    ])

    def _resolver(ref: str) -> str:
        return f"resolved-for-{ref}"

    coord = AttemptCoordinator(sdk_transport=sdk)
    await coord.execute(
        resolved=_resolved(_profile(targets=[
            _sdk_target("primary", provider="anthropic"),
            _sdk_target("fallback", provider="anthropic"),
        ])),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=_resolver,
    )
    # Two delegated calls, one per attempted target.
    assert sdk.execute.await_count == 2
    first, second = sdk.execute.await_args_list
    assert first.kwargs["target"].id == "primary"
    assert first.kwargs["credential_resolver"] is _resolver
    assert second.kwargs["target"].id == "fallback"
    assert second.kwargs["credential_resolver"] is _resolver


@pytest.mark.anyio("asyncio")
async def test_permanent_error_stops_after_first_target():
    """Non-transient exceptions (auth failure, config error, our own
    ValueError) must not fall through. Trying the next target would
    burn the profile's budget on a request that cannot succeed."""
    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=ValueError("credential missing scope"))

    coord = AttemptCoordinator(sdk_transport=sdk)
    with pytest.raises(AllAttemptsFailed) as excinfo:
        await coord.execute(
            resolved=_resolved(_profile(targets=[
                _sdk_target("primary"), _sdk_target("fallback"),
            ])),
            operation="anthropic_messages",
            payload={"messages": [{"role": "user", "content": "hi"}]},
            credential_resolver=lambda ref: "sk-fake",
        )
    # Only one attempt recorded; fallback never fired.
    assert [a.target_id for a in excinfo.value.attempts] == ["primary"]
    assert excinfo.value.attempts[0].error_class == "ValueError"
    assert sdk.execute.await_count == 1


@pytest.mark.anyio("asyncio")
async def test_authentication_error_is_permanent_even_though_it_extends_api_error():
    """Round-3 review fix (#2001): the OpenAI SDK inheritance chain is
    ``AuthenticationError`` → ``APIStatusError`` → ``APIError``. A naive
    MRO walk over the transient set would match ``APIError`` and burn
    the fallback budget re-hitting the second target with the same bad
    credential. Permanent classes must be excluded FIRST."""
    class APIError(Exception):
        """LiteLLM/OpenAI SDK's ``APIError`` for test purposes."""
    class APIStatusError(APIError):
        pass
    class AuthenticationError(APIStatusError):
        status_code = 401

    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=AuthenticationError("bad key"))
    coord = AttemptCoordinator(sdk_transport=sdk)
    with pytest.raises(AllAttemptsFailed) as excinfo:
        await coord.execute(
            resolved=_resolved(_profile(targets=[
                _sdk_target("primary"), _sdk_target("fallback"),
            ])),
            operation="anthropic_messages",
            payload={"messages": [{"role": "user", "content": "hi"}]},
            credential_resolver=lambda ref: "sk-fake",
        )
    assert [a.target_id for a in excinfo.value.attempts] == ["primary"]
    assert sdk.execute.await_count == 1


@pytest.mark.anyio("asyncio")
async def test_http_400_status_code_is_permanent_via_status_attribute():
    """Some SDKs surface a numeric ``status_code`` on the exception
    without a subclass matching our permanent-name list. Reject those
    at the HTTP-status check so a 400 isn't retried."""
    class HTTPError(Exception):
        def __init__(self, msg, status_code):
            super().__init__(msg)
            self.status_code = status_code

    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=HTTPError("bad body", 400))
    coord = AttemptCoordinator(sdk_transport=sdk)
    with pytest.raises(AllAttemptsFailed) as excinfo:
        await coord.execute(
            resolved=_resolved(_profile(targets=[
                _sdk_target("primary"), _sdk_target("fallback"),
            ])),
            operation="anthropic_messages",
            payload={"messages": [{"role": "user", "content": "hi"}]},
            credential_resolver=lambda ref: "sk-fake",
        )
    assert [a.target_id for a in excinfo.value.attempts] == ["primary"]


@pytest.mark.anyio("asyncio")
async def test_http_500_status_code_still_retries():
    """5xx (and 408/429) remain transient — the whole point of retry
    classification is those specific cases."""
    class HTTPError(Exception):
        def __init__(self, msg, status_code):
            super().__init__(msg)
            self.status_code = status_code

    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=[
        HTTPError("upstream down", 503),
        {"content": "ok"},
    ])
    coord = AttemptCoordinator(sdk_transport=sdk)
    result = await coord.execute(
        resolved=_resolved(_profile(targets=[
            _sdk_target("primary"), _sdk_target("fallback"),
        ])),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-fake",
    )
    assert result.winning_target_id == "fallback"


@pytest.mark.anyio("asyncio")
async def test_transient_error_by_class_name_does_retry():
    """LiteLLM's ``RateLimitError`` (or any exception subclassing a
    known transient class name) counts as retryable even though we
    don't import litellm here — the classifier compares class names
    across the MRO. Simulates via a synthetic ``RateLimitError`` class."""
    class RateLimitError(Exception):
        """LiteLLM's ``RateLimitError`` for test purposes."""
    sdk = MagicMock()
    sdk.execute = AsyncMock(side_effect=[
        RateLimitError("rate limited"),
        {"content": "ok"},
    ])
    coord = AttemptCoordinator(sdk_transport=sdk)
    result = await coord.execute(
        resolved=_resolved(_profile(targets=[
            _sdk_target("primary"), _sdk_target("fallback"),
        ])),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-fake",
    )
    assert result.winning_target_id == "fallback"
