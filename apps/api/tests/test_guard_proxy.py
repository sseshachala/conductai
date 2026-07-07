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


# ── canonical workspace resolution ───────────────────────────────────────────

from unittest.mock import MagicMock, patch
import uuid as _uuid
from app.modules.guard.routers.proxy import _resolve_canonical_workspace


def _ws(id_str: str, owner_id: str | None = None, created_at=None):
    from datetime import datetime
    w = MagicMock()
    w.id = _uuid.UUID(id_str)
    w.owner_id = owner_id
    w.created_at = created_at or datetime(2024, 1, 1)
    return w


WS_A = "00000000-0000-0000-0000-000000000001"
WS_B = "00000000-0000-0000-0000-000000000002"
OWNER = "owner-x"


def test_single_workspace_resolves_to_itself():
    """Owner with one workspace → same workspace returned."""
    ws = _ws(WS_A, owner_id=OWNER)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = ws
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = ws
    assert _resolve_canonical_workspace(db, WS_A) == WS_A


def test_multi_workspace_resolves_to_oldest():
    """Owner with two workspaces → oldest (WS_A) returned when called with WS_B."""
    from datetime import datetime
    ws_a = _ws(WS_A, owner_id=OWNER, created_at=datetime(2024, 1, 1))
    ws_b = _ws(WS_B, owner_id=OWNER, created_at=datetime(2024, 6, 1))

    db = MagicMock()
    # First call: lookup WS_B by id
    db.query.return_value.filter.return_value.first.return_value = ws_b
    # Second call: canonical query returns WS_A (oldest)
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = ws_a

    assert _resolve_canonical_workspace(db, WS_B) == WS_A


def test_no_owner_id_resolves_to_self():
    """Workspace with no owner_id → falls back to itself."""
    ws = _ws(WS_A, owner_id=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = ws
    assert _resolve_canonical_workspace(db, WS_A) == WS_A


def test_workspace_not_found_resolves_to_self():
    """DB returns None → falls back to original workspace_id."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert _resolve_canonical_workspace(db, WS_A) == WS_A


def test_canonical_workspace_id_is_cached(monkeypatch):
    """_canonical_workspace_id returns same result without hitting DB twice."""
    from app.modules.guard.routers.proxy import _canonical_workspace_id, _resolve_canonical_workspace
    calls = []

    def fake_resolve(db, ws_id):
        calls.append(ws_id)
        return ws_id

    # Clear lru_cache between tests
    _canonical_workspace_id.cache_clear()
    monkeypatch.setattr(
        "app.modules.guard.routers.proxy._resolve_canonical_workspace", fake_resolve
    )
    monkeypatch.setattr(
        "app.modules.guard.routers.proxy.SessionLocal", lambda: MagicMock()
    )

    _canonical_workspace_id.cache_clear()
    result1 = _canonical_workspace_id(WS_A)
    result2 = _canonical_workspace_id(WS_A)

    assert result1 == result2
    assert len(calls) == 1  # DB hit only once
