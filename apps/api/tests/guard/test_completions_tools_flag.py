"""Flag-behavior tests for tools support on /gateway/v1/completions (#2159 PR 1).

PR 1 lands the shim wire-in behind ``settings.guard_gateway_tools_enabled``.
When OFF (default), the pre-tools contract is preserved: any request
carrying ``tools`` / ``tool_choice`` / ``role: "tool"`` / assistant
``tool_calls`` is refused at the shim with 400 before delegation.

When ON, the shim widens the schema, runs Conduct's own contract
validation via ``tools_validator``, redacts request-path tool payloads,
and forwards. Response-gate + audit fields land in PR 2; until then,
the "on" path is exercised via the flag but ops keeps it OFF in prod.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.modules.guard import completions_shim
from app.modules.guard.routers import gateway_proxy


class _CapturedCall:
    def __init__(self) -> None:
        self.captured: dict[str, Any] | None = None

    async def __call__(
        self,
        request: Request,
        background: BackgroundTasks,
        **kwargs: Any,
    ) -> JSONResponse:
        body_bytes = await request.body()
        self.captured = {"body": json.loads(body_bytes), "kwargs": kwargs}
        return JSONResponse(
            status_code=200,
            content={"id": "x", "object": "chat.completion", "choices": []},
        )


@pytest.fixture
def captured_handler(monkeypatch: pytest.MonkeyPatch) -> _CapturedCall:
    fake = _CapturedCall()
    monkeypatch.setattr(completions_shim, "handle_gateway_request", fake)
    return fake


@pytest.fixture
def tools_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # Flip the flag on for tests that exercise tools acceptance.
    monkeypatch.setattr(completions_shim.settings, "guard_gateway_tools_enabled", True)


@pytest.fixture
def tools_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicit off — belt-and-suspenders for the default-behavior tests.
    monkeypatch.setattr(completions_shim.settings, "guard_gateway_tools_enabled", False)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(gateway_proxy.router)
    return TestClient(app)


_AUTH = {"Authorization": "Bearer cond_mt_test_token"}


def _tools_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "profile": "cond-abcd1234-gpt-4o",
        "messages": [{"role": "user", "content": "what's the weather?"}],
        "max_tokens": 32,
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Look up the current weather in a city.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }],
    }
    body.update(overrides)
    return body


# ─── flag OFF (default) — pre-tools contract preserved ───────────────


class TestFlagOff:
    def test_tools_field_rejected(
        self, client: TestClient, captured_handler: _CapturedCall, tools_disabled: None,
    ) -> None:
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=_tools_body())
        assert resp.status_code == 400
        assert captured_handler.captured is None
        assert "GUARD_GATEWAY_TOOLS_ENABLED" in resp.text

    def test_tool_choice_alone_rejected(
        self, client: TestClient, captured_handler: _CapturedCall, tools_disabled: None,
    ) -> None:
        body = {
            "profile": "cond-abcd1234-gpt-4o",
            "messages": [{"role": "user", "content": "x"}],
            "max_tokens": 5,
            "tool_choice": "auto",
        }
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert captured_handler.captured is None

    def test_tool_role_message_rejected(
        self, client: TestClient, captured_handler: _CapturedCall, tools_disabled: None,
    ) -> None:
        body = {
            "profile": "cond-abcd1234-gpt-4o",
            "messages": [
                {"role": "user", "content": "x"},
                {"role": "tool", "content": "72F", "tool_call_id": "call_1"},
            ],
            "max_tokens": 5,
        }
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert captured_handler.captured is None

    def test_assistant_tool_calls_rejected(
        self, client: TestClient, captured_handler: _CapturedCall, tools_disabled: None,
    ) -> None:
        body = {
            "profile": "cond-abcd1234-gpt-4o",
            "messages": [
                {"role": "user", "content": "x"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "get_weather", "arguments": "{}"},
                    }],
                },
            ],
            "max_tokens": 5,
        }
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert captured_handler.captured is None


# ─── flag ON — tools accepted, validated, redacted, forwarded ────────


class TestFlagOn:
    def test_valid_tools_forwarded(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=_tools_body())
        assert resp.status_code == 200, resp.text
        assert captured_handler.captured is not None
        body = captured_handler.captured["body"]
        assert body["model"] == "cond-abcd1234-gpt-4o"
        assert len(body["tools"]) == 1
        assert body["tools"][0]["function"]["name"] == "get_weather"

    def test_tool_choice_named_matches_declared(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        body = _tools_body(tool_choice={
            "type": "function", "function": {"name": "get_weather"},
        })
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 200, resp.text

    def test_tool_choice_named_unmatched_400(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        body = _tools_body(tool_choice={
            "type": "function", "function": {"name": "send_email"},
        })
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert "does not appear" in resp.text

    def test_duplicate_tool_names_400(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        body = _tools_body(tools=[
            {"type": "function", "function": {"name": "search"}},
            {"type": "function", "function": {"name": "search"}},
        ])
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert "duplicate" in resp.text

    def test_stream_true_with_tools_400(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        body = _tools_body(stream=True)
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert captured_handler.captured is None
        assert "2155" in resp.text

    def test_tool_role_requires_tool_call_id(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        body = _tools_body(messages=[
            {"role": "user", "content": "x"},
            # Missing tool_call_id — must fail validation.
            {"role": "tool", "content": "72F"},
        ])
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert "tool_call_id" in resp.text

    def test_assistant_null_content_needs_tool_calls(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        body = _tools_body(messages=[
            {"role": "user", "content": "x"},
            # Assistant with null content but no tool_calls — malformed.
            {"role": "assistant", "content": None},
        ])
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400

    def test_valid_multi_turn_with_tool_result(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        body = _tools_body(messages=[
            {"role": "user", "content": "weather in SF?"},
            {
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"city": "San Francisco"}),
                    },
                }],
            },
            {"role": "tool", "content": "72F, sunny", "tool_call_id": "call_1"},
        ])
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 200, resp.text
        assert captured_handler.captured is not None
        forwarded = captured_handler.captured["body"]
        # All three messages made it through with the correct shape.
        roles = [m["role"] for m in forwarded["messages"]]
        assert roles == ["user", "assistant", "tool"]
        # Assistant's content: null was preserved OR omitted (exclude_none).
        assert "content" not in forwarded["messages"][1] or forwarded["messages"][1]["content"] is None
        # Tool's tool_call_id round-trips.
        assert forwarded["messages"][2]["tool_call_id"] == "call_1"

    def test_malformed_arguments_json_400(
        self, client: TestClient, captured_handler: _CapturedCall, tools_enabled: None,
    ) -> None:
        # Reviewer's "escaped secret" concern: broken JSON must NOT
        # silently pass through. Redactor raises → 400 tool_arguments_validation_failed.
        body = _tools_body(messages=[
            {"role": "user", "content": "x"},
            {
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"broken'},
                }],
            },
        ])
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert "tool_arguments_validation_failed" in resp.text
        assert captured_handler.captured is None


# ─── estimator regression — audit._estimate_input_tokens ─────────────


class TestEstimatorTools:
    def test_body_without_tools_unchanged(self) -> None:
        from app.guard.audit import _estimate_input_tokens
        base = {"messages": [{"role": "user", "content": "hello world"}]}
        assert _estimate_input_tokens(base) >= 1

    def test_body_with_tools_bigger_than_without(self) -> None:
        # Reservation must NOT under-bill by omitting tool schemas.
        from app.guard.audit import _estimate_input_tokens
        base = {"messages": [{"role": "user", "content": "hello world"}]}
        with_tools = {
            **base,
            "tools": [{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Look up today's weather in a city.",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }],
        }
        assert _estimate_input_tokens(with_tools) > _estimate_input_tokens(base)

    def test_empty_tools_list_no_bonus(self) -> None:
        # An empty tools list contributes zero (validator catches this
        # earlier, but the estimator must be robust).
        from app.guard.audit import _estimate_input_tokens
        base = {"messages": [{"role": "user", "content": "hi"}]}
        with_empty = {**base, "tools": []}
        assert _estimate_input_tokens(with_empty) == _estimate_input_tokens(base)
