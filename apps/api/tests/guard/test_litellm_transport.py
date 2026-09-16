"""Contract tests for LiteLLMTransport (#2001 commit 4).

Locks the runtime invariants a v2 admin cares about but can't inspect
from the profile shape alone:

- Operation dispatch maps each ``Operation`` to LiteLLM's own
  operation-specific API (not ``completion()`` for everything).
- ``num_retries=0`` is unconditionally passed so LiteLLM's retry ladder
  never stacks on top of Conduct's ``max_attempts``.
- Credential is resolved through the caller-supplied resolver — never
  read from a database or a global cache — and passed only for the
  duration of the LiteLLM call.
- ``provider_options`` merge cleanly; explicit kwargs win.
- Unknown operations raise loudly rather than silently degrading to
  ``completion()``.
- Empty credential from the resolver raises before any LiteLLM call
  fires, so callback plumbing can never see an empty ``api_key``.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.guard.gateway_config import LiteLLMSDKTarget
from app.runtime.litellm_transport import LiteLLMTransport


ENV = "11111111-1111-1111-1111-111111111111"


def _target(**overrides):
    """Build a target with minimal defaults suitable for each operation."""
    defaults = dict(
        id="primary",
        transport="litellm_sdk",
        provider="anthropic",
        model="claude-sonnet-4-6",
        credential_ref=f"vault://{ENV}/anthropic",
        provider_options={},
    )
    defaults.update(overrides)
    return LiteLLMSDKTarget(**defaults)


@pytest.fixture
def fake_litellm(monkeypatch):
    """Install a fake ``litellm`` module so tests never call the real
    SDK. Every operation-specific function returns a sentinel that
    tests can identify."""
    module = SimpleNamespace(
        anthropic_messages=AsyncMock(return_value={"sentinel": "anthropic_messages"}),
        acompletion=AsyncMock(return_value={"sentinel": "acompletion"}),
        aresponses=AsyncMock(return_value={"sentinel": "aresponses"}),
        token_counter=MagicMock(return_value=42),
        # Deliberately NOT included: ``completion`` — no fallback path,
        # if the transport ever reaches for it a test explodes.
    )
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


# ─── Operation dispatch ───────────────────────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_dispatches_openai_chat_completions_to_acompletion(fake_litellm):
    result = await LiteLLMTransport().execute(
        target=_target(provider="openai", model="gpt-4o"),
        operation="openai_chat_completions",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-fake",
    )
    assert result == {"sentinel": "acompletion"}
    fake_litellm.acompletion.assert_awaited_once()
    fake_litellm.anthropic_messages.assert_not_awaited()


@pytest.mark.anyio("asyncio")
async def test_dispatches_openai_responses_to_aresponses(fake_litellm):
    result = await LiteLLMTransport().execute(
        target=_target(provider="openai", model="gpt-4o"),
        operation="openai_responses",
        payload={"input": "hello world"},
        credential_resolver=lambda ref: "sk-fake",
    )
    assert result == {"sentinel": "aresponses"}
    fake_litellm.aresponses.assert_awaited_once()
    kwargs = fake_litellm.aresponses.await_args.kwargs
    assert kwargs["input"] == "hello world"


@pytest.mark.anyio("asyncio")
async def test_dispatches_anthropic_messages_to_anthropic_messages(fake_litellm):
    result = await LiteLLMTransport().execute(
        target=_target(),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 100},
        credential_resolver=lambda ref: "sk-ant-fake",
    )
    assert result == {"sentinel": "anthropic_messages"}
    fake_litellm.anthropic_messages.assert_awaited_once()
    kwargs = fake_litellm.anthropic_messages.await_args.kwargs
    assert kwargs["max_tokens"] == 100
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]


@pytest.mark.anyio("asyncio")
async def test_dispatches_anthropic_count_tokens_to_token_counter(fake_litellm):
    result = await LiteLLMTransport().execute(
        target=_target(),
        operation="anthropic_count_tokens",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-ant-fake",
    )
    assert result == 42
    # token_counter is a sync call — NOT awaited
    fake_litellm.token_counter.assert_called_once()
    # And it deliberately does NOT receive api_key or stream — those
    # kwargs are only meaningful for inference calls.
    call_kwargs = fake_litellm.token_counter.call_args.kwargs
    assert "api_key" not in call_kwargs
    assert "stream" not in call_kwargs


# ─── Retry policy ─────────────────────────────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_num_retries_is_always_zero(fake_litellm):
    """Conduct owns retries. LiteLLM's own retry ladder MUST NOT stack
    on top of ``max_attempts`` from the v2 profile — the admin's
    intended attempt cap becomes 2× or 3× otherwise."""
    await LiteLLMTransport().execute(
        target=_target(provider="openai", model="gpt-4o"),
        operation="openai_chat_completions",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-fake",
    )
    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert kwargs["num_retries"] == 0


# ─── Credential resolution ────────────────────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_credential_resolver_is_called_with_target_credential_ref(fake_litellm):
    """Resolver receives the target's ``vault://`` ref verbatim and its
    return value ends up as ``api_key`` — the transport never reads
    the ref from anywhere else and never caches the plaintext."""
    seen: list[str] = []

    def _resolver(ref: str) -> str:
        seen.append(ref)
        return "sk-resolved-per-attempt"

    ref = f"vault://{ENV}/anthropic"
    await LiteLLMTransport().execute(
        target=_target(credential_ref=ref),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=_resolver,
    )
    assert seen == [ref]
    kwargs = fake_litellm.anthropic_messages.await_args.kwargs
    assert kwargs["api_key"] == "sk-resolved-per-attempt"


@pytest.mark.anyio("asyncio")
async def test_empty_credential_raises_before_reaching_litellm(fake_litellm):
    """A resolver that returns empty MUST raise before LiteLLM sees the
    call. An empty ``api_key`` in a LiteLLM call could reach callbacks
    with an ambiguous/empty auth state — surface it as our failure,
    not theirs."""
    with pytest.raises(ValueError, match=r"credential_resolver returned empty"):
        await LiteLLMTransport().execute(
            target=_target(),
            operation="anthropic_messages",
            payload={"messages": [{"role": "user", "content": "hi"}]},
            credential_resolver=lambda ref: "",
        )
    fake_litellm.anthropic_messages.assert_not_awaited()


# ─── provider_options merging ─────────────────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_provider_options_merge_but_explicit_kwargs_win(fake_litellm):
    """``provider_options`` supply region/api_version/etc. If someone
    stuffs ``api_key`` or ``num_retries`` in there, our explicit
    values must still win — the retry-owner and credential-scope
    contracts can't be silently overridden by a profile setting."""
    await LiteLLMTransport().execute(
        target=_target(
            provider="bedrock",
            provider_options={
                "region": "us-east-1",
                "api_key": "leaked-attempt",
                "num_retries": 3,
                "custom_llm_provider": "not-bedrock",
            },
        ),
        operation="openai_chat_completions",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-real",
    )
    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert kwargs["region"] == "us-east-1"
    assert kwargs["api_key"] == "sk-real"
    assert kwargs["num_retries"] == 0
    assert kwargs["custom_llm_provider"] == "bedrock"


# ─── Safety rails ─────────────────────────────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_unknown_operation_raises_without_calling_litellm(fake_litellm):
    with pytest.raises(ValueError, match=r"does not support operation"):
        await LiteLLMTransport().execute(
            target=_target(),
            operation="anthropic_hallucinated_operation",  # type: ignore[arg-type]
            payload={},
            credential_resolver=lambda ref: "sk-fake",
        )
    fake_litellm.acompletion.assert_not_awaited()
    fake_litellm.anthropic_messages.assert_not_awaited()


@pytest.mark.anyio("asyncio")
async def test_target_provider_is_passed_as_custom_llm_provider(fake_litellm):
    """LiteLLM disambiguates provider routing through ``custom_llm_provider``.
    Whatever the target says its provider is (bedrock, gemini, mistral,
    …) must land in that kwarg so LiteLLM's dispatch matches."""
    await LiteLLMTransport().execute(
        target=_target(provider="bedrock", model="anthropic.claude-3-sonnet"),
        operation="openai_chat_completions",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "aws-cred",
    )
    assert fake_litellm.acompletion.await_args.kwargs["custom_llm_provider"] == "bedrock"


@pytest.mark.anyio("asyncio")
async def test_transport_registers_iff_flag_is_on(monkeypatch):
    """The register hook must be off by default and no-op with a flag
    check. Off = legacy RawHTTPTransport still services ``provider=
    litellm``; on = LiteLLMTransport is available."""
    from app.core.config import settings
    from app.runtime.litellm_transport import register_litellm_transport_if_enabled

    _prev = settings.guard_litellm_in_process
    try:
        settings.guard_litellm_in_process = False
        # Should be a no-op — no exception, no side effects.
        register_litellm_transport_if_enabled()
        settings.guard_litellm_in_process = True
        register_litellm_transport_if_enabled()  # idempotent
    finally:
        settings.guard_litellm_in_process = _prev


# ─── Payload whitelisting (review fix #4) ─────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_client_supplied_api_base_raises(fake_litellm):
    """Review fix (#2001 round 3): client injecting ``api_base`` or
    ``base_url`` must produce a clear validation error, not silently
    disappear from the request. Silent drop hid the "you can't override
    endpoints from a client payload" contract from the caller."""
    from app.runtime.litellm_transport import UnsupportedPayloadFields
    with pytest.raises(UnsupportedPayloadFields, match=r"transport-controlled"):
        await LiteLLMTransport().execute(
            target=_target(provider="openai", model="gpt-4o"),
            operation="openai_chat_completions",
            payload={
                "messages": [{"role": "user", "content": "hi"}],
                "api_base": "https://attacker.example.com/v1",
            },
            credential_resolver=lambda ref: "sk-fake",
        )
    fake_litellm.acompletion.assert_not_awaited()


@pytest.mark.anyio("asyncio")
async def test_client_supplied_callbacks_raises(fake_litellm):
    """LiteLLM's ``callbacks``/``success_callback``/``failure_callback``
    would let a client register plugins server-side. Reject loudly."""
    from app.runtime.litellm_transport import UnsupportedPayloadFields
    with pytest.raises(UnsupportedPayloadFields, match=r"transport-controlled"):
        await LiteLLMTransport().execute(
            target=_target(provider="openai", model="gpt-4o"),
            operation="openai_chat_completions",
            payload={
                "messages": [{"role": "user", "content": "hi"}],
                "callbacks": ["custom_plugin"],
            },
            credential_resolver=lambda ref: "sk-fake",
        )
    fake_litellm.acompletion.assert_not_awaited()


@pytest.mark.anyio("asyncio")
async def test_unknown_operation_body_field_raises(fake_litellm):
    """Review fix (#2001 round 3): an unknown operation body field
    (e.g. a legit LiteLLM parameter we haven't added to the allowlist
    yet) must surface as a clear error to the caller rather than being
    silently ignored. Bug pattern the reviewer flagged: sending
    ``max_completion_tokens=10`` for OpenAI o1 and seeing it disappear.
    """
    from app.runtime.litellm_transport import UnsupportedPayloadFields
    with pytest.raises(UnsupportedPayloadFields, match=r"unsupported fields"):
        await LiteLLMTransport().execute(
            target=_target(provider="openai", model="gpt-4o"),
            operation="openai_chat_completions",
            payload={
                "messages": [{"role": "user", "content": "hi"}],
                "totally_made_up_field": True,
            },
            credential_resolver=lambda ref: "sk-fake",
        )
    fake_litellm.acompletion.assert_not_awaited()


@pytest.mark.anyio("asyncio")
async def test_max_completion_tokens_is_forwarded_now(fake_litellm):
    """Regression lock for the review-flagged field. ``max_completion_tokens``
    (OpenAI o1/o3 series) is now on the allowlist and must forward."""
    await LiteLLMTransport().execute(
        target=_target(provider="openai", model="o1-mini"),
        operation="openai_chat_completions",
        payload={
            "messages": [{"role": "user", "content": "hi"}],
            "max_completion_tokens": 512,
            "store": False,
        },
        credential_resolver=lambda ref: "sk-fake",
    )
    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert kwargs["max_completion_tokens"] == 512
    assert kwargs["store"] is False


@pytest.mark.anyio("asyncio")
async def test_bad_payload_does_not_trigger_credential_resolve(fake_litellm):
    """Payload validation runs BEFORE credential resolution so a
    malformed request never causes a Vault decrypt."""
    from app.runtime.litellm_transport import UnsupportedPayloadFields
    resolved: list[str] = []
    with pytest.raises(UnsupportedPayloadFields):
        await LiteLLMTransport().execute(
            target=_target(provider="openai", model="gpt-4o"),
            operation="openai_chat_completions",
            payload={"messages": [], "api_base": "https://x"},
            credential_resolver=lambda ref: (resolved.append(ref) or "sk-fake"),
        )
    assert resolved == []


@pytest.mark.anyio("asyncio")
async def test_operation_body_fields_still_forwarded(fake_litellm):
    """Whitelist keeps operation-body fields (tools, tool_choice,
    system, response_format, etc.) so the whitelist tightening didn't
    regress the fields customers legitimately send."""
    tools_payload = [{"type": "function", "function": {"name": "x"}}]
    await LiteLLMTransport().execute(
        target=_target(provider="openai", model="gpt-4o"),
        operation="openai_chat_completions",
        payload={
            "messages": [{"role": "user", "content": "hi"}],
            "tools": tools_payload,
            "tool_choice": "auto",
            "temperature": 0.5,
            "response_format": {"type": "json_object"},
        },
        credential_resolver=lambda ref: "sk-fake",
    )
    kwargs = fake_litellm.acompletion.await_args.kwargs
    assert kwargs["tools"] == tools_payload
    assert kwargs["tool_choice"] == "auto"
    assert kwargs["temperature"] == 0.5
    assert kwargs["response_format"] == {"type": "json_object"}
