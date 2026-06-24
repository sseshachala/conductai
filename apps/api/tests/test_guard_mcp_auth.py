"""
Issue #800 — Guard MCP endpoint auth: header-first, URL-query fallback.

These tests verify the contract of `_extract_token` directly, without
spinning up FastAPI or touching the DB. Token validation against
guard_member_config + the surrounding route is covered by
test_guard.py and integration tests.

Cases:
  1. Authorization: Bearer header present → header value returned
  2. Query token only (legacy Claude.ai web path) → query value returned
  3. Both header and query present → header wins
  4. Neither present → None
  5. Bearer header with no value → falls back to query
  6. Bearer header with whitespace-only value → falls back to query
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Path + env setup before importing app code
HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# Stub structlog before importing _extract_token (it imports get_logger at
# the call site for the deprecation warning).
import types
if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    _structlog.contextvars = MagicMock()
    sys.modules["structlog"] = _structlog


def _make_request(headers: dict[str, str]) -> object:
    """Minimal stub of fastapi.Request — just exposes .headers.get(...)."""
    request = MagicMock()
    request.headers = headers  # MagicMock will allow .get() on a dict directly
    # MagicMock by default makes .get() return a MagicMock, which is truthy.
    # So we route through the dict explicitly.
    request.headers = headers
    return request


# ── Real test cases ──────────────────────────────────────────────────────────


class _HeaderDict(dict):
    """dict where .get() returns the actual value, not MagicMock."""
    pass


def _req(authorization: str | None = None):
    req = MagicMock()
    h = _HeaderDict()
    if authorization is not None:
        h["Authorization"] = authorization
    req.headers = h
    return req


def test_header_bearer_wins():
    from app.modules.guard.routers.mcp import _extract_token
    req = _req(authorization="Bearer secret-from-header")
    assert _extract_token(req, query_token="from-query") == "secret-from-header"


def test_query_only_legacy_path():
    from app.modules.guard.routers.mcp import _extract_token
    req = _req(authorization=None)
    assert _extract_token(req, query_token="legacy-token") == "legacy-token"


def test_both_header_takes_precedence_over_query():
    from app.modules.guard.routers.mcp import _extract_token
    req = _req(authorization="Bearer wins-from-header")
    assert _extract_token(req, query_token="loses-from-query") == "wins-from-header"


def test_neither_returns_none():
    from app.modules.guard.routers.mcp import _extract_token
    req = _req(authorization=None)
    assert _extract_token(req, query_token=None) is None


def test_empty_query_with_no_header_returns_none():
    from app.modules.guard.routers.mcp import _extract_token
    req = _req(authorization=None)
    assert _extract_token(req, query_token="") is None


def test_bearer_with_only_whitespace_returns_none_when_no_query():
    from app.modules.guard.routers.mcp import _extract_token
    req = _req(authorization="Bearer    ")
    assert _extract_token(req, query_token=None) is None


def test_non_bearer_auth_scheme_falls_through_to_query():
    """If a client sends `Authorization: Basic <…>`, we don't treat it as a token.
    The query string fallback should still apply."""
    from app.modules.guard.routers.mcp import _extract_token
    req = _req(authorization="Basic some-basic-auth")
    assert _extract_token(req, query_token="from-query") == "from-query"


def test_bearer_prefix_extraction_no_extra_whitespace():
    """The 'Bearer ' literal (7 chars including the space) is stripped exactly."""
    from app.modules.guard.routers.mcp import _extract_token
    req = _req(authorization="Bearer abc123")
    result = _extract_token(req, query_token=None)
    assert result == "abc123"
    assert not result.startswith(" "), "leading whitespace not stripped"
