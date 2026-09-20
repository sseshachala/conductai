"""Wire-in tests for the Anthropic-target route on canonical completions.

Proves that when a v2 profile targets Anthropic but the caller sends
the canonical (OpenAI Chat Completions) shape, the executor:

  1. Detects the shape mismatch in _build_v2_plan and sets
     needs_anthropic_conversion=True (rather than 400).
  2. Converts body → Anthropic Messages before coordinator dispatch.
  3. Normalizes coordinator response → canonical OpenAI shape before
     the response gate sees it.
  4. Rejects streaming+Anthropic with 501 (deferred to follow-up).

Uses stubbed resolve_v2 + coordinator so the tests stay pure.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

from app.modules.guard.gateway_handler import (
    _V2Plan,
    _build_v2_plan,
    _execute_v2,
)


def _resolved(*, accepts, targets, revision_id="rev-anth"):
    return SimpleNamespace(
        revision_id=revision_id,
        profile=SimpleNamespace(accepts=accepts, targets=targets),
    )


def _target(*, transport, provider, model="claude-3-5-sonnet"):
    return SimpleNamespace(transport=transport, provider=provider, model=model)


class TestBuildV2PlanConversionDetection:
    def test_anthropic_only_profile_flags_conversion(self, monkeypatch) -> None:
        resolved = _resolved(
            accepts=["anthropic_messages"],
            targets=[_target(transport="native_http", provider="anthropic")],
        )
        monkeypatch.setattr(
            "app.modules.guard.gateway_runtime.resolve_v2",
            lambda db, *, workspace_id, cond_code: resolved,
        )
        # Fake credential resolver — never actually invoked in this test.
        monkeypatch.setattr(
            "app.runtime.gateway_v2_bridge.build_credential_resolver",
            lambda db, *, workspace_id, environment_id, provider, profile: (
                lambda ref: "sk-fake"
            ),
        )
        plan = _build_v2_plan(
            db=None, workspace_id="ws", cond_code="abcd1234",
            provider="openai", upstream_path="/v1/chat/completions",
            body={"model": "cond-abcd1234-claude", "messages": [{"role": "user", "content": "x"}]},
        )
        assert plan.needs_anthropic_conversion is True
        # Operation switched to anthropic_messages so transport
        # dispatch resolves to the right upstream URL.
        assert plan.operation == "anthropic_messages"

    def test_openai_only_profile_no_conversion(self, monkeypatch) -> None:
        resolved = _resolved(
            accepts=["openai_chat_completions"],
            targets=[_target(transport="native_http", provider="openai", model="gpt-4o")],
        )
        monkeypatch.setattr(
            "app.modules.guard.gateway_runtime.resolve_v2",
            lambda db, *, workspace_id, cond_code: resolved,
        )
        monkeypatch.setattr(
            "app.runtime.gateway_v2_bridge.build_credential_resolver",
            lambda db, *, workspace_id, environment_id, provider, profile: (
                lambda ref: "sk-fake"
            ),
        )
        plan = _build_v2_plan(
            db=None, workspace_id="ws", cond_code="abcd1234",
            provider="openai", upstream_path="/v1/chat/completions",
            body={"model": "cond-abcd1234-gpt-4o", "messages": [{"role": "user", "content": "x"}]},
        )
        assert plan.needs_anthropic_conversion is False
        assert plan.operation == "openai_chat_completions"

    def test_mixed_provider_profile_rejected(self, monkeypatch) -> None:
        # A profile with both Anthropic AND OpenAI targets is intentionally
        # out of scope for the wire-in — per-target dispatch is a follow-up.
        # Falls through to the original "does not accept operation" 400.
        resolved = _resolved(
            accepts=["anthropic_messages"],
            targets=[
                _target(transport="native_http", provider="anthropic"),
                _target(transport="native_http", provider="openai", model="gpt-4o"),
            ],
        )
        monkeypatch.setattr(
            "app.modules.guard.gateway_runtime.resolve_v2",
            lambda db, *, workspace_id, cond_code: resolved,
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as e:
            _build_v2_plan(
                db=None, workspace_id="ws", cond_code="abcd1234",
                provider="openai", upstream_path="/v1/chat/completions",
                body={"model": "cond-abcd1234-x", "messages": [{"role": "user", "content": "x"}]},
            )
        assert e.value.status_code == 400
        assert "does not accept" in str(e.value.detail)


@pytest.mark.anyio("asyncio")
class TestExecuteV2AnthropicConversion:
    async def test_body_converted_before_coordinator(self, monkeypatch) -> None:
        """_execute_v2 passes an Anthropic-shape body to the coordinator when
        needs_anthropic_conversion is True."""
        captured: dict = {}

        class _FakeCoordinator:
            async def execute(self, *, resolved, operation, payload, credential_resolver, stream, **_kw):
                captured["operation"] = operation
                captured["payload"] = payload
                # Return an Anthropic-shape non-streaming response.
                from app.runtime.attempt_coordinator import (
                    AttemptRecord, CoordinatorResult,
                )
                return CoordinatorResult(
                    response={
                        "id": "msg_1", "model": "claude-3-5-sonnet",
                        "role": "assistant", "type": "message",
                        "content": [{"type": "text", "text": "pong"}],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 5, "output_tokens": 2},
                    },
                    revision_id=resolved.revision_id if resolved is not None else None,
                    attempts=[AttemptRecord(
                        target_id="anth", transport="native_http",
                        provider_or_integration="anthropic",
                        started_at_monotonic=0.0, completed_at_monotonic=0.1,
                        succeeded=True, error_class=None, error_summary=None,
                    )],
                    winning_target_id="anth",
                )

        async def _fake_get_coordinator():
            return _FakeCoordinator()
        monkeypatch.setattr(
            "app.runtime.gateway_transports.get_coordinator",
            _fake_get_coordinator,
        )

        plan = _V2Plan(
            resolved=SimpleNamespace(
                revision_id="rev-1",
                profile=SimpleNamespace(
                    accepts=["anthropic_messages"],
                    targets=[_target(transport="native_http", provider="anthropic")],
                ),
            ),
            operation="anthropic_messages",
            credential_resolver=lambda ref: "sk-fake",
            needs_anthropic_conversion=True,
        )

        canonical_body = {
            "model": "cond-x-claude", "max_tokens": 5,
            "messages": [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": "ping"},
            ],
        }
        response = await _execute_v2(plan=plan, body=canonical_body, stream=False)

        # Coordinator saw Anthropic-shape body.
        assert captured["operation"] == "anthropic_messages"
        assert captured["payload"]["system"] == "be brief"
        # system extracted from messages list
        assert all(m["role"] != "system" for m in captured["payload"]["messages"])

        # Response normalised back to OpenAI shape before returning.
        assert isinstance(response, JSONResponse)
        body = json.loads(response.body)
        assert body["object"] == "chat.completion"
        assert body["choices"][0]["message"] == {"role": "assistant", "content": "pong"}
        assert body["choices"][0]["finish_reason"] == "stop"
        assert body["usage"]["prompt_tokens"] == 5

    async def test_streaming_rejected_when_conversion_needed(self, monkeypatch) -> None:
        """SSE-to-SSE Anthropic-to-OpenAI translation is deferred; the wire-in
        rejects the combination up front."""
        from fastapi import HTTPException

        # Coordinator should never be reached.
        async def _fake_get_coordinator():
            raise AssertionError("coordinator must not run when streaming+Anthropic rejected")
        monkeypatch.setattr(
            "app.runtime.gateway_transports.get_coordinator",
            _fake_get_coordinator,
        )

        plan = _V2Plan(
            resolved=SimpleNamespace(
                revision_id="rev-1",
                profile=SimpleNamespace(
                    accepts=["anthropic_messages"],
                    targets=[_target(transport="native_http", provider="anthropic")],
                ),
            ),
            operation="anthropic_messages",
            credential_resolver=lambda ref: "sk-fake",
            needs_anthropic_conversion=True,
        )

        with pytest.raises(HTTPException) as e:
            await _execute_v2(
                plan=plan,
                body={"model": "cond-x-claude", "messages": [{"role": "user", "content": "x"}]},
                stream=True,
            )
        assert e.value.status_code == 501
        assert "SSE-to-SSE" in str(e.value.detail)
