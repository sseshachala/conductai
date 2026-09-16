"""X7 — vendor-specific headers reach v2 upstreams (with allowlist).

Before the fix, ``anthropic-beta``, ``openai-organization``,
``openai-project`` etc. that the client sent were collected into
``extra_headers`` in the handler but never threaded into
``_execute_v2``. v2 traffic hitting features that require these
headers (e.g. Anthropic's prompt caching, org-scoped OpenAI billing)
silently degraded.

Fix scope:

- Handler filters ``extra_headers`` to an allowlist of vendor
  headers (``_V2_HEADER_ALLOWLIST``) and passes them to
  ``_execute_v2``.
- Coordinator threads ``client_headers`` into ``_dispatch``.
- ``NativeHTTPTransport`` + ``HTTPPassthroughTransport`` merge them
  into the outgoing request AFTER their own auth + static headers,
  but content-type + auth-header are re-pinned last so a
  malicious/misconfigured client can't override them.
- ``LiteLLMTransport`` is unchanged for this PR (LiteLLM's
  extra-headers API is provider-specific; deferred).

Tests below lock the allowlist filter + transport merge + auth
override protection.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.guard.gateway_config import HTTPPassthroughTarget, NativeHTTPTarget


ENV = "11111111-1111-1111-1111-111111111111"


def _native() -> NativeHTTPTarget:
    return NativeHTTPTarget(
        id="primary",
        transport="native_http",
        provider="anthropic",
        model="claude-sonnet-4-6",
        credential_ref=f"vault://{ENV}/anthropic",
    )


def _openrouter() -> HTTPPassthroughTarget:
    return HTTPPassthroughTarget(
        id="or-primary",
        transport="http_passthrough",
        integration="openrouter",
        model="anthropic/claude-sonnet",
        credential_ref=f"vault://{ENV}/openrouter",
    )


# ─── Allowlist filter ─────────────────────────────────────────────────


def test_allowlist_keeps_vendor_headers_and_drops_everything_else():
    """Client-facing headers a caller might legitimately send land in
    the outgoing dict; unrelated / potentially dangerous headers get
    silently dropped (matches v1's ``_skip`` semantics but stricter)."""
    from app.modules.guard.gateway_handler import _v2_allowlisted_headers

    filtered = _v2_allowlisted_headers({
        "anthropic-beta": "prompt-caching-2024-07-31",
        "openai-organization": "org-abc",
        "openai-project": "proj-xyz",
        # Not in the allowlist — dropped.
        "x-arbitrary-header": "leak",
        "authorization": "Bearer stolen-key",   # never forwardable
        "cookie": "session=stealme",
    })
    assert filtered == {
        "anthropic-beta": "prompt-caching-2024-07-31",
        "openai-organization": "org-abc",
        "openai-project": "proj-xyz",
    }


def test_allowlist_handles_empty_and_none_input():
    from app.modules.guard.gateway_handler import _v2_allowlisted_headers
    assert _v2_allowlisted_headers(None) == {}
    assert _v2_allowlisted_headers({}) == {}


# ─── Transport merge — vendor headers reach the wire ─────────────────


@pytest.mark.anyio("asyncio")
async def test_native_transport_forwards_client_headers(monkeypatch):
    """NativeHTTPTransport must send allowlisted client headers to the
    vendor — that's the whole point of the fix. Auth + content-type
    stay under transport control regardless of what the client passed."""
    from app.runtime.native_http_transport import NativeHTTPTransport

    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured["headers"] = headers
        class _R:
            status_code = 200
            def json(self): return {"content": "ok"}
            def raise_for_status(self): pass
        return _R()

    transport = NativeHTTPTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_native(),
        operation="anthropic_messages",
        payload={"messages": []},
        credential_resolver=lambda ref: "sk-ant-live",
        client_headers={
            "anthropic-beta": "prompt-caching-2024-07-31",
            "anthropic-version": "2024-10-22",
        },
    )
    # Vendor headers reached the wire.
    assert captured["headers"]["anthropic-beta"] == "prompt-caching-2024-07-31"
    assert captured["headers"]["anthropic-version"] == "2024-10-22"
    # Content-type + auth stay under transport control.
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["headers"]["x-api-key"] == "sk-ant-live"


@pytest.mark.anyio("asyncio")
async def test_native_transport_client_cannot_override_auth_header(monkeypatch):
    """Even if a caller sneaks a client header that clashes with the
    transport's auth or content-type field, transport wins. Guards
    against a compromised client trying to route through a different
    key or content type."""
    from app.runtime.native_http_transport import NativeHTTPTransport

    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured["headers"] = headers
        class _R:
            status_code = 200
            def json(self): return {"content": "ok"}
            def raise_for_status(self): pass
        return _R()

    transport = NativeHTTPTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_native(),
        operation="anthropic_messages",
        payload={"messages": []},
        credential_resolver=lambda ref: "sk-ant-live",
        # Hostile client input — not in the allowlist in practice,
        # but the transport still must not honour it if it somehow
        # arrives.
        client_headers={
            "x-api-key": "sk-attacker",
            "content-type": "text/plain",
        },
    )
    assert captured["headers"]["x-api-key"] == "sk-ant-live"
    assert captured["headers"]["content-type"] == "application/json"


@pytest.mark.anyio("asyncio")
async def test_http_passthrough_forwards_client_headers(monkeypatch):
    """Symmetric assertion for the passthrough transport."""
    from app.runtime.http_passthrough_transport import HTTPPassthroughTransport

    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured["headers"] = headers
        class _R:
            status_code = 200
            def json(self): return {"id": "x"}
            def raise_for_status(self): pass
        return _R()

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_openrouter(),
        operation="openai_chat_completions",
        payload={"messages": []},
        credential_resolver=lambda ref: "sk-or-live",
        client_headers={"openai-organization": "org-abc"},
    )
    assert captured["headers"]["openai-organization"] == "org-abc"
    # OpenRouter's Bearer auth pinned; content-type pinned.
    assert captured["headers"]["authorization"] == "Bearer sk-or-live"
    assert captured["headers"]["content-type"] == "application/json"
