"""Unit coverage for the profile-native ``/gateway/v1/completions`` endpoint (#2144, PR 1).

Covers the shim's own responsibilities:

- route registration
- strict input validation (canonical schema, profile format, streaming,
  tools/functions/vision, unknown fields, message shape) — every rejection
  path must fail BEFORE any delegation into the v2 executor, so a caller
  cannot smuggle a legacy-routed request through the canonical URL
- canonical → provider body rewrite (``profile`` → ``model``, whitelisted
  fields carried through)
- correct delegation call into the v2 executor (``provider``/``upstream_path``/auth args)

End-to-end parity with the SDK-shaped OpenAI route (same audit rows,
same policy decisions, same budget effects) requires DB fixtures and
lives in the integration-test follow-up commit before this PR merges.
This file stays a narrow contract test on the shim itself so it can run
in-memory in under a second and catch schema/regression bugs first.
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


# ---- fixtures ---------------------------------------------------------


class _CapturedCall:
    """Record what ``handle_gateway_request`` would have been called with.

    ``captured is None`` means the shim rejected the request before
    delegation, which is the invariant every rejection test asserts.
    """

    def __init__(self) -> None:
        self.captured: dict[str, Any] | None = None

    async def __call__(
        self,
        request: Request,
        background: BackgroundTasks,
        **kwargs: Any,
    ) -> JSONResponse:
        body_bytes = await request.body()
        self.captured = {
            "body": json.loads(body_bytes),
            "kwargs": kwargs,
            "auth_header": request.headers.get("authorization"),
        }
        return JSONResponse(
            status_code=200,
            content={"id": "chatcmpl-fake", "object": "chat.completion", "choices": []},
        )


@pytest.fixture
def captured_handler(monkeypatch: pytest.MonkeyPatch) -> _CapturedCall:
    fake = _CapturedCall()
    monkeypatch.setattr(completions_shim, "handle_gateway_request", fake)
    return fake


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(gateway_proxy.router)
    return TestClient(app)


def _valid_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "profile": "cond-abcd1234-gpt-4o",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    body.update(overrides)
    return body


# ---- registration ------------------------------------------------------


def test_completions_route_is_registered_under_gateway_v1() -> None:
    paths = {route.path for route in gateway_proxy.router.routes}
    assert "/gateway/v1/completions" in paths


# ---- happy path --------------------------------------------------------


def test_canonical_body_rewrites_profile_to_model_and_delegates_to_openai_operation(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=_valid_body(temperature=0.2, top_p=0.9, stop=["\n\n"]),
    )
    assert resp.status_code == 200
    assert captured_handler.captured is not None
    body = captured_handler.captured["body"]
    kwargs = captured_handler.captured["kwargs"]

    # profile → model swap; whitelisted fields carried through
    assert body["model"] == "cond-abcd1234-gpt-4o"
    assert "profile" not in body
    assert body["messages"] == [{"role": "user", "content": "ping"}]
    assert body["max_tokens"] == 5
    assert body["temperature"] == 0.2
    assert body["top_p"] == 0.9
    assert body["stop"] == ["\n\n"]
    assert body["stream"] is False

    # Delegates to the OpenAI Chat Completions v2 operation with the
    # same auth/args every SDK-shaped OpenAI route uses today.
    assert kwargs["provider"] == "openai"
    assert kwargs["upstream_path"] == "/v1/chat/completions"
    assert kwargs["auth_header_in"] == "authorization"
    assert kwargs["auth_header_out"] == "authorization"
    assert kwargs["bearer"] is True
    assert kwargs["canonical_profile"] is True

    # Auth header flows through unchanged.
    assert captured_handler.captured["auth_header"] == "Bearer cond_mt_test_token"


# ---- P1 fix: invalid profile MUST NOT fall through to legacy routing ---


@pytest.mark.parametrize(
    "bad_profile",
    [
        "gpt-4o",                    # v1-style bare model name — would silently v1-route
        "claude-sonnet-4-6",         # v1-style Anthropic model name
        "cond-invalid-test",         # code segment isn't 8 chars
        "cond-ABCDEFGH-x",           # uppercase code — parser is lowercase-only
        "cond-abcd1234",             # missing alias
        "cond-abcd1234-",            # empty alias
        "COND-abcd1234-gpt-4o",      # uppercase prefix
        "conda-abcd1234-gpt-4o",     # wrong prefix
        "",                          # empty
    ],
)
def test_invalid_profile_is_rejected_before_delegation(
    client: TestClient, captured_handler: _CapturedCall, bad_profile: str
) -> None:
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=_valid_body(profile=bad_profile),
    )
    assert resp.status_code == 400
    assert "cond-<8chars>-<alias>" in resp.text or "profile" in resp.text.lower()
    # The critical invariant: delegation MUST NOT happen. A bypass here
    # would let the caller reach v1 legacy routing through the canonical
    # URL, defeating the purpose of the shim.
    assert captured_handler.captured is None


def test_missing_profile_is_rejected(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    body = _valid_body()
    body.pop("profile")
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=body,
    )
    assert resp.status_code == 400
    assert captured_handler.captured is None


def test_client_supplied_model_is_rejected(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json={**_valid_body(), "model": "gpt-4o"},
    )
    assert resp.status_code == 400
    assert "`model` is not allowed" in resp.text
    assert captured_handler.captured is None


# ---- streaming: strict-bool enforcement + delegation shape ----------


@pytest.mark.parametrize("stream_value", [1, "true", "false", "no", "yes", 0.1, "1"])
def test_non_bool_stream_value_is_rejected(
    client: TestClient, captured_handler: _CapturedCall, stream_value: Any
) -> None:
    """Reviewer P2 fix from PR 1 stays intact via StrictBool. Only JSON
    ``true`` / ``false`` are accepted; truthy non-bools that the handler's
    ``bool(...)`` coercion would otherwise interpret as streaming are
    rejected at the shim boundary.
    """
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=_valid_body(stream=stream_value),
    )
    assert resp.status_code == 400, (
        f"non-bool stream={stream_value!r} should be rejected, got "
        f"{resp.status_code}"
    )
    assert captured_handler.captured is None


def test_stream_true_delegates_with_stream_flag_and_usage_option_set(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    """``stream: true`` is accepted and passed through to the v2 executor
    with ``stream_options.include_usage=true`` injected server-side.

    OpenAI omits the usage chunk on streaming responses unless the
    request explicitly asks for it. Without the injection, audit rows
    and budget settlement carry zero tokens for successful streams —
    reviewer P1 on the streaming PR.
    """
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=_valid_body(stream=True),
    )
    assert resp.status_code == 200
    assert captured_handler.captured is not None
    forwarded_body = captured_handler.captured["body"]
    assert forwarded_body["stream"] is True, (
        f"stream flag lost between shim and executor — forwarded body: "
        f"{forwarded_body}"
    )
    assert forwarded_body.get("stream_options") == {"include_usage": True}, (
        f"stream_options.include_usage=true must be injected server-side "
        f"when stream=true; forwarded body: {forwarded_body}"
    )


def test_stream_false_does_not_inject_stream_options(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    """The stream_options injection is scoped to stream=true. A non-
    streaming request MUST NOT carry stream_options — the field is
    meaningful only when streaming, and OpenAI rejects it otherwise
    with a 400.
    """
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=_valid_body(stream=False),
    )
    assert resp.status_code == 200
    assert captured_handler.captured is not None
    forwarded_body = captured_handler.captured["body"]
    assert "stream_options" not in forwarded_body, (
        f"stream_options must not be injected when stream=false; "
        f"forwarded body: {forwarded_body}"
    )


def test_stream_false_and_omitted_both_forward_stream_false(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    for payload in ({**_valid_body(), "stream": False}, _valid_body()):
        captured_handler.captured = None
        resp = client.post(
            "/gateway/v1/completions",
            headers={"Authorization": "Bearer cond_mt_test_token"},
            json=payload,
        )
        assert resp.status_code == 200
        assert captured_handler.captured is not None
        assert captured_handler.captured["body"]["stream"] is False


# ---- P2 fix: text-only contract enforced by schema --------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"tools": [{"type": "function", "function": {"name": "noop"}}]},
        {"functions": [{"name": "noop"}]},          # legacy OpenAI shape
        {"tool_choice": "auto"},
        {"response_format": {"type": "json_object"}},
        {"seed": 42},
        {"logprobs": True},
        {"n": 3},
        {"random_unknown_field": "hello"},
        # stream_options is deliberately forbidden: the shim injects it
        # server-side when stream=true so audit + budget always get token
        # counts. Letting the caller override would let them opt out of
        # accounting for their own request — that's Conduct's decision,
        # not the caller's.
        {"stream_options": {"include_usage": True}},
        {"stream_options": {"include_usage": False}},
    ],
)
def test_unknown_or_forbidden_top_level_fields_are_rejected(
    client: TestClient, captured_handler: _CapturedCall, extra: dict
) -> None:
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json={**_valid_body(), **extra},
    )
    assert resp.status_code == 400
    assert captured_handler.captured is None


@pytest.mark.parametrize(
    "bad_content",
    [
        # #2166 PR 2 — list content is now accepted (multimodal vision).
        # Deep validation of parts lives in vision_validator. Only truly
        # invalid shapes stay in this rejection parametrize.
        {"type": "text", "text": "hi"},    # single dict block (not wrapped in list)
        123,
        None,
    ],
)
def test_non_string_message_content_is_rejected(
    client: TestClient, captured_handler: _CapturedCall, bad_content: Any
) -> None:
    body = _valid_body()
    body["messages"] = [{"role": "user", "content": bad_content}]
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=body,
    )
    assert resp.status_code == 400
    assert captured_handler.captured is None


def test_empty_messages_array_is_rejected(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=_valid_body(messages=[]),
    )
    assert resp.status_code == 400
    assert captured_handler.captured is None


@pytest.mark.parametrize(
    "bad_role",
    ["tool", "function", "developer", "human", "assistants", ""],
)
def test_unknown_message_role_is_rejected(
    client: TestClient, captured_handler: _CapturedCall, bad_role: str
) -> None:
    body = _valid_body(messages=[{"role": bad_role, "content": "hi"}])
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=body,
    )
    assert resp.status_code == 400
    assert captured_handler.captured is None


def test_missing_max_tokens_is_rejected(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    body = _valid_body()
    body.pop("max_tokens")
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=body,
    )
    assert resp.status_code == 400
    assert captured_handler.captured is None


# ---- generic malformed body -------------------------------------------


def test_non_object_body_is_rejected(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": "Bearer cond_mt_test_token"},
        json=["not", "an", "object"],
    )
    assert resp.status_code == 400
    assert captured_handler.captured is None


def test_invalid_json_is_rejected(
    client: TestClient, captured_handler: _CapturedCall
) -> None:
    resp = client.post(
        "/gateway/v1/completions",
        headers={
            "Authorization": "Bearer cond_mt_test_token",
            "Content-Type": "application/json",
        },
        content=b"{not valid json",
    )
    assert resp.status_code == 400
    assert captured_handler.captured is None
