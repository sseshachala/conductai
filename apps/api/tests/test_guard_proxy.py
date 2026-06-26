"""Smoke tests for the Guard proxy — pure-function paths only.

End-to-end forwarding is exercised by a separate dev-machine smoke test
(`scripts/proxy_smoke.sh`) once a real Anthropic key is configured.
"""
from __future__ import annotations

from app.modules.guard.routers.proxy import (
    MEMBER_TOKEN_PREFIX,
    VENDOR_DEFAULTS,
    _extract_member_token,
    _extract_token_counts,
    _safe_json,
)


def test_extract_member_token_anthropic_x_api_key():
    assert _extract_member_token("guard-mt-abc123", bearer=False) == "guard-mt-abc123"


def test_extract_member_token_openai_bearer():
    assert _extract_member_token("Bearer guard-mt-xyz", bearer=True) == "guard-mt-xyz"


def test_extract_member_token_rejects_missing_prefix():
    assert _extract_member_token("sk-ant-real-key", bearer=False) is None


def test_extract_member_token_rejects_wrong_scheme():
    assert _extract_member_token("Basic guard-mt-abc", bearer=True) is None


def test_extract_member_token_rejects_empty():
    assert _extract_member_token("", bearer=False) is None
    assert _extract_member_token("", bearer=True) is None


def test_safe_json_handles_garbage():
    assert _safe_json(b"not json", fallback={"ok": False}) == {"ok": False}


def test_safe_json_parses_clean_json():
    assert _safe_json(b'{"a": 1}', fallback={}) == {"a": 1}


def test_extract_token_counts_from_anthropic_non_stream():
    body = b'{"usage": {"input_tokens": 100, "output_tokens": 250}}'
    assert _extract_token_counts({}, body) == (100, 250)


def test_extract_token_counts_from_anthropic_sse():
    sse = (
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":42}}}\n'
        b'data: {"type":"content_block_delta","delta":{"text":"hi"}}\n'
        b'data: {"type":"message_delta","usage":{"output_tokens":17}}\n'
    )
    assert _extract_token_counts({}, sse) == (42, 17)


def test_extract_token_counts_returns_none_on_garbage():
    assert _extract_token_counts({}, b"completely not parseable") == (None, None)


def test_vendor_defaults_cover_v1_providers():
    assert set(VENDOR_DEFAULTS) == {"anthropic", "openai", "perplexity"}
    assert MEMBER_TOKEN_PREFIX == "guard-mt-"
