"""Flag-behavior tests for vision (image_url) support on /gateway/v1/completions (#2166 PR 1).

Mirrors the shape of ``test_completions_tools_flag.py``. Two cohorts:

- **Flag OFF** (default): any request carrying list-shaped
  ``message.content`` is refused at the shim with 400 before delegation.
- **Flag ON**: image_url parts pass through Conduct's contract
  validation and reach the downstream handler.

Regression coverage for the Codex review issue #1 (2026-09-21):
``validate_messages`` used to reject list content for user/system
messages BEFORE the vision block ran, making image-carrying requests
uniformly 400 even with the flag on.
"""
from __future__ import annotations

import base64
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
def vision_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        completions_shim.settings, "guard_gateway_vision_enabled", True,
    )


@pytest.fixture
def vision_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        completions_shim.settings, "guard_gateway_vision_enabled", False,
    )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(gateway_proxy.router)
    return TestClient(app)


_AUTH = {"Authorization": "Bearer cond_mt_test_token"}


def _vision_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "profile": "cond-abcd1234-gpt-4o",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "what's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/img.png"},
                },
            ],
        }],
        "max_tokens": 32,
    }
    body.update(overrides)
    return body


# ─── flag OFF (default) — multimodal refused ────────────────────────


class TestFlagOff:
    def test_list_content_rejected(
        self, client: TestClient, captured_handler: _CapturedCall,
        vision_disabled: None,
    ) -> None:
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=_vision_body())
        assert resp.status_code == 400
        assert "GUARD_GATEWAY_VISION_ENABLED" in resp.text
        assert captured_handler.captured is None

    def test_plain_string_content_still_ok(
        self, client: TestClient, captured_handler: _CapturedCall,
        vision_disabled: None,
    ) -> None:
        # Non-multimodal messages must keep working when vision is off.
        body = {
            "profile": "cond-abcd1234-gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 32,
        }
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 200
        assert captured_handler.captured is not None


# ─── flag ON — multimodal accepted end-to-end ───────────────────────


class TestFlagOn:
    def test_https_image_reaches_handler(
        self, client: TestClient, captured_handler: _CapturedCall,
        vision_enabled: None,
    ) -> None:
        # THE regression: this used to 400 because validate_messages
        # rejected list content before the vision block ran.
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=_vision_body())
        assert resp.status_code == 200, f"vision request rejected: {resp.text}"
        assert captured_handler.captured is not None
        forwarded = captured_handler.captured["body"]
        assert forwarded["messages"][0]["content"][1]["type"] == "image_url"

    def test_data_url_image_reaches_handler(
        self, client: TestClient, captured_handler: _CapturedCall,
        vision_enabled: None,
    ) -> None:
        payload = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"A" * 100).decode("ascii")
        data_url = f"data:image/png;base64,{payload}"
        body = _vision_body()
        body["messages"][0]["content"][1]["image_url"]["url"] = data_url
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 200, f"data URL vision rejected: {resp.text}"
        assert captured_handler.captured is not None

    def test_http_url_still_rejected_even_with_flag_on(
        self, client: TestClient, captured_handler: _CapturedCall,
        vision_enabled: None,
    ) -> None:
        # Security invariant: flag on ≠ allow http URLs. Scheme
        # allowlist runs inside vision_validator.
        body = _vision_body()
        body["messages"][0]["content"][1]["image_url"]["url"] = "http://example.com/img.png"
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 400
        assert "unsupported URL scheme" in resp.text
        assert captured_handler.captured is None

    def test_text_only_list_content_ok(
        self, client: TestClient, captured_handler: _CapturedCall,
        vision_enabled: None,
    ) -> None:
        # A list with only text parts (no images) must also pass.
        body = _vision_body()
        body["messages"][0]["content"] = [{"type": "text", "text": "just text"}]
        resp = client.post("/gateway/v1/completions", headers=_AUTH, json=body)
        assert resp.status_code == 200, resp.text
