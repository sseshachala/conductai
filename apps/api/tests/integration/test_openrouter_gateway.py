"""
End-to-end OpenRouter gateway test — hits real openrouter.ai with a real key.

**Skipped by default**. Opt-in via env vars — CI runs the unit suite;
this file only runs when an operator explicitly enables it.

Required env vars:
  CONDUCT_OPENROUTER_E2E    — set to "1" to enable
  OPENROUTER_API_KEY        — a real OpenRouter API key (sk-or-...)

Optional:
  OPENROUTER_TEST_MODELS    — comma-separated model ids (default: openai/gpt-4o-mini,
                              anthropic/claude-3-5-haiku, google/gemini-flash-1.5).
                              Each model runs as its own parametrized test case.
  OPENROUTER_TEST_MODEL     — single-model override (legacy; wins over MODELS if set).
  OPENROUTER_BASE_URL       — override endpoint (default: https://openrouter.ai/api/v1)

Verifies:
  1. Adapter routes openrouter.ai URLs to the openrouter adapter (pure).
  2. Model is provider-prefixed correctly for both "model" and "provider/model" inputs.
  3. A live chat/completions call with Bearer auth + prefixed model returns 200 with content.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

from app.runtime.adapters.gateway import gateway_adapt


pytestmark = pytest.mark.skipif(
    os.environ.get("CONDUCT_OPENROUTER_E2E") != "1",
    reason="OpenRouter E2E disabled — set CONDUCT_OPENROUTER_E2E=1 and OPENROUTER_API_KEY to run",
)


def _env(key: str) -> str:
    v = os.environ.get(key)
    if not v:
        pytest.skip(f"Missing required env var: {key}")
    return v


def test_adapter_routes_openrouter_url():
    gw = gateway_adapt("https://openrouter.ai/api/v1", "sk-or-fake", "anthropic", "claude-3-5-haiku")
    assert gw.headers == {}, "openrouter uses caller-supplied Bearer auth, not gateway headers"
    assert gw.model == "anthropic/claude-3-5-haiku"


def test_adapter_preserves_already_prefixed_model():
    gw = gateway_adapt("https://openrouter.ai/api/v1", "sk-or-fake", "openai", "openai/gpt-4o-mini")
    assert gw.model == "openai/gpt-4o-mini", "should not double-prefix"


_DEFAULT_MODELS = (
    "openai/gpt-4o-mini,"
    "anthropic/claude-3-5-haiku,"
    "google/gemini-flash-1.5"
)


def _models() -> list[str]:
    single = os.environ.get("OPENROUTER_TEST_MODEL")
    if single:
        return [single]
    raw = os.environ.get("OPENROUTER_TEST_MODELS", _DEFAULT_MODELS)
    return [m.strip() for m in raw.split(",") if m.strip()]


@pytest.mark.parametrize("model", _models())
def test_live_chat_completion(model: str):
    key = _env("OPENROUTER_API_KEY")
    base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # Prove the adapter would produce the same model id we send.
    provider, _, tail = model.partition("/")
    gw = gateway_adapt(base, key, provider, tail or model)
    assert gw.model == model

    body = json.dumps({
        "model": gw.model,
        "messages": [{"role": "user", "content": "Say ok"}],
        "max_tokens": 5,
    }).encode()

    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        # 402/404: account can't reach this model — skip, don't fail the run.
        if e.code in (402, 404):
            pytest.skip(f"model {model} unavailable on this account (HTTP {e.code}): {detail}")
        pytest.fail(f"OpenRouter returned HTTP {e.code} for {model}: {detail}")

    assert payload.get("choices"), f"no choices in response: {payload}"
    msg = payload["choices"][0].get("message", {}).get("content", "")
    assert msg, f"empty content in response: {payload}"
