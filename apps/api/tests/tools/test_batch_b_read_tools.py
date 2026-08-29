"""Batch B read tools (#1414, #1415, #1417, #1296) — join-heavy free-function
ToolDefs. Verifies each tool registers, produces the expected envelope
shape, and (critically for #1417) never returns raw secret material.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # side-effect: populate registry
from app.tools.registry import default_registry


_CTX = MCPContext(workspace_id="00000000-0000-0000-0000-000000000000", surface="lens")


def test_batch_b_tools_registered():
    for name in (
        "get_workspace_kpis",
        "list_discovered_agents",
        "list_credentials",
        "get_autopilot_activity",
    ):
        tool = default_registry.get(name)
        assert tool is not None, f"{name} missing"
        assert "lens" in tool.tags
        assert tool.annotations.read_only, f"{name} must be read_only"


# ── #1414 Workspace KPIs ─────────────────────────────────────────────────────

def test_get_workspace_kpis_returns_expected_shape():
    class _Q:
        def __init__(self, count_val=0, all_val=None):
            self._count = count_val
            self._all = all_val or []
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def distinct(self): return self
        def count(self): return self._count
        def all(self): return self._all

    class _DB:
        def query(self, *_a, **_k):
            # First call returns the block-count query, subsequent calls
            # return empty queries. Order matters only for readability
            # here — the function does 4 queries. We overload query() to
            # simulate every one returning "no data".
            return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_workspace_kpis
        out = get_workspace_kpis(_CTX, time_window="last_24h")

    assert out["time_window"] == "last_24h"
    assert out["blocked_calls"] == 0
    assert out["spend"] == {"amount_usd": 0.0, "currency": "USD"}
    assert out["runs"]["total"] == 0
    assert out["runs"]["succeeded"] == 0
    assert out["runs"]["failed"] == 0
    assert out["active_agents"] == 0
    assert "since" in out


def test_get_workspace_kpis_window_last_7d():
    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def distinct(self): return self
        def count(self): return 0
        def all(self): return []

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_workspace_kpis
        out = get_workspace_kpis(_CTX, time_window="last_7d")

    assert out["time_window"] == "last_7d"


# ── #1415 Discovery ──────────────────────────────────────────────────────────

def test_list_discovered_agents_empty():
    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def all(self): return []

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import list_discovered_agents
        out = list_discovered_agents(_CTX)

    assert out["count"] == 0
    assert out["agents"] == []


def test_list_discovered_agents_returns_shape():
    class _Agent:
        name = "langchain-agent-1"
        framework = "langchain"
        source = "process"
        location = "/home/user/agent.py"
        risk_score = 72
        under_guard = False
        proxy_routed = False
        first_seen_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
        last_seen_at = datetime(2026, 8, 29, tzinfo=timezone.utc)

    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def all(self): return [_Agent()]

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import list_discovered_agents
        out = list_discovered_agents(_CTX, framework="langchain")

    assert out["count"] == 1
    a = out["agents"][0]
    assert a["framework"] == "langchain"
    assert a["under_guard"] is False
    assert a["last_seen_at"] == "2026-08-29T00:00:00+00:00"


# ── #1417 Vault — SECURITY-CRITICAL secret suppression ────────────────────────

def test_list_credentials_never_returns_encrypted_credentials():
    """Absolute: metadata-only tool must never surface the raw blob."""
    class _Integ:
        id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        service = "github"
        handle = "acme"
        auth_method = "oauth"
        scopes = ["repo", "workflow"]
        environment_id = None
        encrypted_credentials = "SECRET-BLOB-THAT-MUST-NOT-LEAK"
        last_used_at = datetime(2026, 8, 29, tzinfo=timezone.utc)
        created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)

    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def all(self): return [_Integ()]

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import list_credentials
        out = list_credentials(_CTX)

    assert out["count"] == 1
    cred = out["credentials"][0]
    forbidden = ("encrypted_credentials", "encrypted", "secret", "raw", "blob", "credentials_value", "credential")
    for k in cred.keys():
        assert not any(f in k.lower() for f in forbidden), f"leaked key: {k}"
    # Recursive scan of every string value — the blob must not appear anywhere.
    def _walk(obj):
        if isinstance(obj, str):
            assert "SECRET-BLOB-THAT-MUST-NOT-LEAK" not in obj, "raw secret leaked in output"
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
    _walk(out)


def test_list_credentials_returns_metadata():
    class _Integ:
        id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        service = "slack"
        handle = "acme-workspace"
        auth_method = "api_key"
        scopes = ["chat:write"]
        environment_id = None
        last_used_at = datetime(2026, 8, 29, tzinfo=timezone.utc)
        created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)

    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def all(self): return [_Integ()]

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import list_credentials
        out = list_credentials(_CTX)

    cred = out["credentials"][0]
    assert cred["service"] == "slack"
    assert cred["handle"] == "acme-workspace"
    assert cred["auth_method"] == "api_key"
    assert cred["scopes"] == ["chat:write"]


# ── #1296 Autopilot activity ─────────────────────────────────────────────────

def test_get_autopilot_activity_empty():
    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def limit(self, _n): return self
        def all(self): return []

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_autopilot_activity
        out = get_autopilot_activity(_CTX)

    assert out["count"] == 0
    assert out["findings"] == []


def test_get_autopilot_activity_limit_clamped():
    """limit above 500 clamps to 500; below 1 clamps to 1."""
    captured = {}

    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def limit(self, n):
            captured["limit"] = n
            return self
        def all(self): return []

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_autopilot_activity
        get_autopilot_activity(_CTX, limit=9999)
    assert captured["limit"] == 500


def test_get_autopilot_activity_shape():
    class _F:
        id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        tool = "claude-code"
        severity = "high"
        type = "injection"
        file = "app/routes/user.py"
        line = 42
        description = "SQL string concatenation with user input"
        status = "open"
        repo_full_name = "acme/webapp"
        run_id = "run_abc"
        github_issue_url = "https://github.com/acme/webapp/issues/1"
        created_at = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)
        updated_at = datetime(2026, 8, 29, 11, 0, tzinfo=timezone.utc)

    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def limit(self, _n): return self
        def all(self): return [_F()]

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_autopilot_activity
        out = get_autopilot_activity(_CTX, status="open")

    assert out["count"] == 1
    f = out["findings"][0]
    assert f["tool"] == "claude-code"
    assert f["severity"] == "high"
    assert f["status"] == "open"
