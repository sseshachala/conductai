"""Gateway handler acceptance matrix with real LiteLLM and mock vendor HTTP.

No provider keys, inference charges, or external requests. The SDK still
executes its real request conversion, response parsing, and stream wrappers.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from app.modules.guard.gateway_config import GatewayProfileV2
from app.modules.guard.gateway_handler import _V2Plan, _execute_v2
from app.runtime.attempt_coordinator import AttemptCoordinator
from app.runtime.http_passthrough_transport import HTTPPassthroughTransport
from app.runtime.litellm_transport import LiteLLMTransport
from app.runtime.native_http_transport import NativeHTTPTransport
from app.runtime.accounting.normalizers.sse import parse_all

ENV = "11111111-1111-1111-1111-111111111111"
CHAT = {"id": "chatcmpl_fixture", "object": "chat.completion", "created": 1,
        "model": "gpt-4o", "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}
MESSAGE = {"id": "msg_fixture", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
           "content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn", "stop_sequence": None,
           "usage": {"input_tokens": 5, "output_tokens": 2}}
RESPONSE = {"id": "resp_fixture", "object": "response", "created_at": 1, "status": "completed",
            "model": "gpt-4o", "output": [{"id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed",
                                          "content": [{"type": "output_text", "text": "OK", "annotations": []}]}],
            "parallel_tool_calls": True, "tools": [], "tool_choice": "auto",
            "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}}


def wire(operation, stream):
    if operation == "anthropic_count_tokens":
        return json.dumps({"input_tokens": 5}).encode()
    data = MESSAGE if operation == "anthropic_messages" else RESPONSE if operation == "openai_responses" else CHAT
    if not stream:
        return json.dumps(data).encode()
    if operation == "anthropic_messages":
        events = [{"type": "message_start", "message": {**MESSAGE, "content": [], "usage": {"input_tokens": 5, "output_tokens": 0}}},
                  {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                  {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "OK"}},
                  {"type": "content_block_stop", "index": 0},
                  {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 2}},
                  {"type": "message_stop"}]
    elif operation == "openai_responses":
        events = [{"type": "response.created", "sequence_number": 0, "response": {**RESPONSE, "status": "in_progress", "output": []}},
                  {"type": "response.output_text.delta", "sequence_number": 1, "item_id": "msg_fixture", "output_index": 0, "content_index": 0, "delta": "OK"},
                  {"type": "response.completed", "sequence_number": 2, "response": RESPONSE}]
    else:
        events = [{"id": CHAT["id"], "object": "chat.completion.chunk", "created": 1, "model": CHAT["model"],
                   "choices": [{"index": 0, "delta": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]},
                  {"id": CHAT["id"], "object": "chat.completion.chunk", "created": 1, "model": CHAT["model"], "choices": [], "usage": CHAT["usage"]}]
    result = b"".join(((f"event: {e['type']}\n" if "type" in e else "") + "data: " + json.dumps(e) + "\n\n").encode() for e in events)
    return result if operation != "openai_chat_completions" else result + b"data: [DONE]\n\n"


class Chunked(httpx.AsyncByteStream):
    def __init__(self, data):
        self.data = data
        self.closed = False

    async def __aiter__(self):
        for i in range(0, len(self.data), 17):
            yield self.data[i:i + 17]

    async def aclose(self):
        self.closed = True


CASES = [(transport, provider, op) for transport in ("native_http", "litellm_sdk") for provider, ops in (
    ("anthropic", ("anthropic_messages", "anthropic_count_tokens")),
    ("openai", ("openai_chat_completions", "openai_responses")),
) for op in ops]
CASES += [("litellm_sdk", "anthropic", "openai_chat_completions"), ("litellm_sdk", "openai", "anthropic_messages")]
CASES += [("litellm_sdk", provider, "openai_chat_completions") for provider in ("perplexity", "together")]
CASES += [("http_passthrough", integration, operation) for integration, operation in (
    ("openrouter", "openai_chat_completions"), ("portkey", "openai_chat_completions"),
    ("helicone_openai", "openai_chat_completions"), ("helicone_anthropic", "anthropic_messages"),
    ("azure_openai", "openai_chat_completions"), ("custom", "openai_chat_completions"),
    ("custom", "openai_responses"), ("custom", "anthropic_messages"), ("custom", "anthropic_count_tokens"),
)]


@pytest.mark.asyncio
@pytest.mark.parametrize("transport,provider,operation", CASES)
@pytest.mark.parametrize("stream", [False, True])
async def test_handler_transport_matrix(monkeypatch, transport, provider, operation, stream):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setenv("OPENAI_API_BASE", "https://must-not-route.invalid/v1")
    if transport == "litellm_sdk":
        import litellm  # Deliberately no importorskip: CI must exercise the shipped SDK.
        litellm.turn_off_message_logging = True
    requests = []
    sources = []
    async def send(client, request, **kwargs):
        requests.append(request)
        # SDK cross-provider calls translate at the wire boundary.
        upstream_operation = "anthropic_messages" if request.url.path.endswith("/messages") else "anthropic_count_tokens" if request.url.path.endswith("/count_tokens") else "openai_responses" if request.url.path.endswith("/responses") else "openai_chat_completions"
        source = Chunked(wire(upstream_operation, stream))
        sources.append(source)
        response = httpx.Response(200, request=request, headers={"content-type": "text/event-stream" if stream else "application/json"}, stream=source)
        if not kwargs.get("stream"):
            await response.aread()
        return response
    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    target = {"id": "primary", "transport": transport, "model": "claude-sonnet-4-6" if provider == "anthropic" else "gpt-4o",
              "credential_ref": f"vault://{ENV}/fixture"}
    if transport == "http_passthrough":
        target["integration"] = provider
        target["provider_options"] = {"virtual_key": "fixture", "api_version": "2024-10-21", "protocol": "anthropic" if operation.startswith("anthropic") else "openai"}
        if provider in {"custom", "azure_openai"}:
            target["endpoint"] = "https://fixture.example/v1"
    else:
        target["provider"] = provider
    profile = GatewayProfileV2(name="fixture", model_alias="fixture", accepts=[operation], targets=[target])
    native = NativeHTTPTransport()
    passthrough = HTTPPassthroughTransport()
    sdk = LiteLLMTransport(native_transport=native)
    coordinator = AttemptCoordinator(native_http_transport=native, sdk_transport=sdk, http_passthrough_transport=passthrough)
    async def get_coordinator():
        return coordinator
    monkeypatch.setattr("app.runtime.gateway_transports.get_coordinator", get_coordinator)
    plan = _V2Plan(SimpleNamespace(profile=profile, revision_id=UUID(int=2)), operation,
                   lambda ref: "fixture-key", vendor_credential_resolver=lambda ref: "fixture-vendor-key")
    payload = {"model": "cond-fixture-alias", "stream": stream}
    payload.update({"input": "hello"} if operation == "openai_responses" else {"messages": [{"role": "user", "content": "hello"}]})
    if operation == "anthropic_messages":
        payload["max_tokens"] = 20
    try:
        if operation == "anthropic_count_tokens" and stream:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as error:
                await _execute_v2(plan=plan, body=payload, stream=stream)
            assert error.value.status_code == 400
            assert not requests
            return
        response = await _execute_v2(plan=plan, body=payload, stream=stream, client_headers={"anthropic-beta": "fixture-beta"} if operation.startswith("anthropic") else {"openai-organization": "fixture-org"})
        assert response.status_code == 200
        body = b"".join([chunk async for chunk in response.body_iterator]) if stream else response.body
        assert requests
        expected_operation = "anthropic_messages" if transport == "litellm_sdk" and provider == "anthropic" and operation == "openai_chat_completions" else "openai_responses" if transport == "litellm_sdk" and provider == "openai" and operation == "anthropic_messages" else operation
        suffix = {"anthropic_messages": "/messages", "anthropic_count_tokens": "/count_tokens", "openai_responses": "/responses", "openai_chat_completions": "/chat/completions"}[expected_operation]
        assert requests[-1].url.path.rstrip("/").endswith(suffix)
        if transport == "litellm_sdk":
            assert requests[-1].url.host == {"anthropic": "api.anthropic.com", "openai": "api.openai.com",
                                           "perplexity": "api.perplexity.ai", "together": "api.together.xyz"}[provider]
        assert all(json.loads(request.content)["model"] != "cond-fixture-alias" for request in requests)
        assert plan.last_meta["attempt_count"] == 1
        assert plan.last_meta["attempts"][0]["operation"] == operation
        if stream:
            assert parse_all(body)
            assert b"usage" in bytes(plan.upstream_body)
            assert all(source.closed for source in sources)
            if operation == "openai_responses":
                final = next(json.loads(event.data)["response"] for event in parse_all(body) if event.event == "response.completed")
                assert final["usage"]["input_tokens"] == 5
                assert final["usage"]["output_tokens"] == 2
        elif operation == "anthropic_count_tokens":
            assert json.loads(body) == {"input_tokens": 5}
        else:
            assert b"OK" in body
        if transport == "litellm_sdk":
            import asyncio
            await asyncio.sleep(0.05)  # Allow the SDK's post-stream logging tasks to drain.
    finally:
        for transport_instance in (native, passthrough):
            if transport_instance._client:
                await transport_instance._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["native_http", "litellm_sdk", "http_passthrough"])
@pytest.mark.parametrize("status", [400, 401, 429, 503])
@pytest.mark.parametrize("stream", [False, True])
async def test_handler_fallback_is_bounded_and_preserves_attempts(monkeypatch, transport, status, stream):
    from fastapi import HTTPException
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    requests = []
    sources = []

    async def send(client, request, **kwargs):
        requests.append(request)
        failed = json.loads(request.content)["model"] == "gpt-4o"
        code = status if failed else 200
        data = json.dumps({"error": {"message": "fixture refusal", "type": "fixture"}}).encode() if failed else wire("openai_chat_completions", stream)
        source = Chunked(data)
        sources.append(source)
        response = httpx.Response(code, request=request, headers={"content-type": "application/json" if failed or not stream else "text/event-stream"}, stream=source)
        if not kwargs.get("stream"):
            await response.aread()
        return response

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    common = {"transport": transport, "credential_ref": f"vault://{ENV}/fixture"}
    common.update({"integration": "openrouter"} if transport == "http_passthrough" else {"provider": "openai"})
    profile = GatewayProfileV2(name="fallback", model_alias="fallback", accepts=["openai_chat_completions"], max_attempts=2,
        targets=[{**common, "id": "primary", "model": "gpt-4o"}, {**common, "id": "fallback", "model": "gpt-4o-mini"}])
    native = NativeHTTPTransport()
    passthrough = HTTPPassthroughTransport()
    coordinator = AttemptCoordinator(native_http_transport=native, sdk_transport=LiteLLMTransport(native_transport=native), http_passthrough_transport=passthrough)

    async def get_coordinator():
        return coordinator

    monkeypatch.setattr("app.runtime.gateway_transports.get_coordinator", get_coordinator)
    plan = _V2Plan(SimpleNamespace(profile=profile, revision_id=UUID(int=2)), "openai_chat_completions", lambda ref: "fixture-key")
    try:
        payload = {"model": "cond-fallback", "messages": [{"role": "user", "content": "hello"}], "stream": stream}
        if status in {400, 401}:
            with pytest.raises(HTTPException):
                await _execute_v2(plan=plan, body=payload, stream=stream)
            assert len(requests) == 1
            assert plan.last_meta["attempt_count"] == 1
        else:
            response = await _execute_v2(plan=plan, body=payload, stream=stream)
            body = b"".join([chunk async for chunk in response.body_iterator]) if stream else response.body
            assert b"OK" in body
            assert len(requests) == 2
            assert plan.last_meta["winning_target_id"] == "fallback"
            assert [a["model"] for a in plan.last_meta["attempts"]] == ["gpt-4o", "gpt-4o-mini"]
            assert plan.last_meta["attempts"][0]["response_bytes_b64"]
        assert all(source.closed for source in sources)
        import asyncio
        await asyncio.sleep(0.05)
    finally:
        for instance in (native, passthrough):
            if instance._client:
                await instance._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("transport,provider", [("native_http", "openai"), ("litellm_sdk", "openai"), ("litellm_sdk", "anthropic"), ("http_passthrough", "openrouter")])
async def test_stream_disconnect_closes_vendor_response_without_fallback(monkeypatch, transport, provider):
    requests, sources = [], []

    async def send(client, request, **kwargs):
        requests.append(request)
        operation = "anthropic_messages" if provider == "anthropic" else "openai_chat_completions"
        source = Chunked(wire(operation, True))
        sources.append(source)
        return httpx.Response(200, request=request, headers={"content-type": "text/event-stream"}, stream=source)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    common = {"transport": transport, "credential_ref": f"vault://{ENV}/fixture",
              "integration" if transport == "http_passthrough" else "provider": provider,
              "model": "claude-sonnet-4-6" if provider == "anthropic" else "gpt-4o"}
    profile = GatewayProfileV2(name="disconnect", model_alias="disconnect", accepts=["openai_chat_completions"], max_attempts=2,
        targets=[{**common, "id": "primary"}, {**common, "id": "fallback"}])
    native, passthrough = NativeHTTPTransport(), HTTPPassthroughTransport()
    coordinator = AttemptCoordinator(native_http_transport=native, sdk_transport=LiteLLMTransport(native_transport=native), http_passthrough_transport=passthrough)

    async def get_coordinator():
        return coordinator

    monkeypatch.setattr("app.runtime.gateway_transports.get_coordinator", get_coordinator)
    plan = _V2Plan(SimpleNamespace(profile=profile, revision_id=UUID(int=2)), "openai_chat_completions", lambda ref: "fixture-key")
    try:
        response = await _execute_v2(plan=plan, body={"messages": [{"role": "user", "content": "hello"}]}, stream=True)
        assert await response.body_iterator.__anext__()
        await response.body_iterator.aclose()
        assert len(requests) == 1
        assert plan.last_meta["attempt_count"] == 1
        assert all(source.closed for source in sources)
    finally:
        for instance in (native, passthrough):
            if instance._client:
                await instance._client.aclose()
