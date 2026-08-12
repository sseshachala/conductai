"""
Guard MCP endpoint auth — Authorization header only (query-param path was
retired in issue #800).

These tests verify the contract of `_extract_token` directly, without
spinning up FastAPI or touching the DB. Token validation against
guard_member_config and the surrounding route is covered by test_guard.py
and integration tests.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

if "structlog" not in sys.modules:
    _structlog = types.ModuleType("structlog")
    _structlog.get_logger = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    _structlog.contextvars = MagicMock()
    sys.modules["structlog"] = _structlog


class _HeaderDict(dict):
    """dict where .get() returns the actual value, not MagicMock."""
    pass


def _req(*, authorization: str | None = None) -> object:
    req = MagicMock()
    h = _HeaderDict()
    if authorization is not None:
        h["Authorization"] = authorization
    req.headers = h
    return req


def test_header_bearer_returns_token():
    from app.modules.guard.routers.mcp import _extract_token
    assert _extract_token(_req(authorization="Bearer secret-from-header")) == "secret-from-header"


def test_no_header_returns_none():
    from app.modules.guard.routers.mcp import _extract_token
    assert _extract_token(_req(authorization=None)) is None


def test_bearer_with_only_whitespace_returns_none():
    from app.modules.guard.routers.mcp import _extract_token
    # "Bearer    ".strip() → empty → None (matches prod behaviour).
    assert _extract_token(_req(authorization="Bearer    ")) is None


def test_non_bearer_auth_scheme_returns_raw_header():
    """Smithery compatibility — bare token (no Bearer prefix) is returned as-is."""
    from app.modules.guard.routers.mcp import _extract_token
    assert _extract_token(_req(authorization="Basic some-basic-auth")) == "Basic some-basic-auth"


def test_bearer_prefix_extraction_no_extra_whitespace():
    from app.modules.guard.routers.mcp import _extract_token
    result = _extract_token(_req(authorization="Bearer abc123"))
    assert result == "abc123"
    assert not result.startswith(" "), "leading whitespace not stripped"
