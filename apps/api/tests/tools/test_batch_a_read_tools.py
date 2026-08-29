"""Batch A read tools (#1413, #1416, #1418, #1419) — free-function ToolDefs.

Verifies each tool registers, respects lens/read_only annotations, and
produces the expected envelope shape. DB reads are mocked; the goal is
wiring parity, not query correctness.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # side-effect: populate registry
from app.tools.registry import default_registry


_CTX = MCPContext(workspace_id="00000000-0000-0000-0000-000000000000", surface="lens")


def test_batch_a_tools_registered():
    for name in (
        "list_playbooks", "get_playbook",
        "list_machines_sync_state",
        "get_llm_primitives",
        "get_rate_limits",
    ):
        tool = default_registry.get(name)
        assert tool is not None, f"{name} missing"
        assert "lens" in tool.tags
        assert tool.annotations.read_only, f"{name} must be read_only"


# ── #1413 Playbooks ───────────────────────────────────────────────────────────

def test_list_playbooks_returns_builtins_when_no_user_templates():
    class _Q:
        def filter(self, *_a, **_k): return self
        def all(self): return []

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import list_playbooks
        out = list_playbooks(_CTX)

    assert out["count"] > 0, "expected at least one builtin playbook"
    assert all(p["source"] == "builtin" for p in out["playbooks"])
    assert all("slug" in p and "name" in p for p in out["playbooks"])


def test_get_playbook_unknown_slug_returns_error():
    from app.tools.registrations.lens import get_playbook
    out = get_playbook(_CTX, slug="does_not_exist_anywhere")
    assert "error" in out
    assert out["slug"] == "does_not_exist_anywhere"


# ── #1416 Sync state ──────────────────────────────────────────────────────────

def test_list_machines_sync_state_in_sync_computation():
    class _Row:
        user_email = "dev@example.com"
        detected_tools = ["claude-code", "cursor"]
        mcp_registered = ["claude-code"]
        hook_registered = ["cursor"]
        reported_at = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)

    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def all(self): return [_Row()]

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import list_machines_sync_state
        out = list_machines_sync_state(_CTX)

    assert out["count"] == 1
    row = out["machines"][0]
    assert row["user_email"] == "dev@example.com"
    assert row["in_sync"] is True


def test_list_machines_sync_state_filter_out_of_sync_hides_synced():
    class _RowSynced:
        user_email = "synced@example.com"
        detected_tools = ["claude-code"]
        mcp_registered = ["claude-code"]
        hook_registered = []
        reported_at = None

    class _RowUnsynced:
        user_email = "unsynced@example.com"
        detected_tools = ["claude-code", "cursor"]
        mcp_registered = ["claude-code"]
        hook_registered = []
        reported_at = None

    class _Q:
        def filter(self, *_a, **_k): return self
        def order_by(self, *_a, **_k): return self
        def all(self): return [_RowSynced(), _RowUnsynced()]

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import list_machines_sync_state
        out = list_machines_sync_state(_CTX, filter="out_of_sync")

    assert out["count"] == 1
    assert out["machines"][0]["user_email"] == "unsynced@example.com"
    assert out["machines"][0]["in_sync"] is False


# ── #1418 LLM primitives ─────────────────────────────────────────────────────

def test_get_llm_primitives_unconfigured():
    class _Q:
        def filter(self, *_a, **_k): return self
        def first(self): return None

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_llm_primitives
        out = get_llm_primitives(_CTX)

    assert out["configured"] is False
    assert out["preferred_provider"] == "anthropic"
    assert out["tier_map"] == {}


def test_get_llm_primitives_configured():
    class _Row:
        preferred_provider = "openai"
        tier_map = {"cheap": "gpt-4o-mini", "balanced": "gpt-4o", "smart": "o1"}
        updated_at = datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc)

    class _Q:
        def filter(self, *_a, **_k): return self
        def first(self): return _Row()

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_llm_primitives
        out = get_llm_primitives(_CTX)

    assert out["configured"] is True
    assert out["preferred_provider"] == "openai"
    assert out["tier_map"]["balanced"] == "gpt-4o"
    assert out["updated_at"] == "2026-08-20T10:30:00+00:00"


# ── #1418 (part 2) Secret suppression — critical ─────────────────────────────

def test_get_llm_primitives_never_returns_api_key_field():
    """Vault-adjacent tool — must never surface anything key-shaped."""
    class _Row:
        preferred_provider = "anthropic"
        tier_map = {"smart": "claude-opus-4-7"}
        updated_at = None

    class _Q:
        def filter(self, *_a, **_k): return self
        def first(self): return _Row()

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_llm_primitives
        out = get_llm_primitives(_CTX)

    forbidden = ("api_key", "apikey", "secret", "token", "credential")
    for k in out.keys():
        assert not any(f in k.lower() for f in forbidden), f"unexpected key-shaped field: {k}"


# ── #1419 Rate limits ────────────────────────────────────────────────────────

def test_get_rate_limits_no_rows_returns_empty_defaults():
    class _Q:
        def filter(self, *_a, **_k): return self
        def all(self): return []

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_rate_limits
        out = get_rate_limits(_CTX)

    assert out["default"]["rpm"] is None
    assert out["default"]["tpm"] is None
    assert out["overrides"] == []
    assert out["override_count"] == 0


def test_get_rate_limits_default_plus_overrides():
    class _Default:
        agent_identity_id = None
        rpm = 60
        tpm = 100000
        updated_at = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)

    class _Override:
        agent_identity_id = "cond_agt_abc"
        rpm = 2
        tpm = 500
        updated_at = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)

    class _Q:
        def filter(self, *_a, **_k): return self
        def all(self): return [_Default(), _Override()]

    class _DB:
        def query(self, *_a, **_k): return _Q()
        def close(self): pass

    with patch("app.core.database.SessionLocal", return_value=_DB()):
        from app.tools.registrations.lens import get_rate_limits
        out = get_rate_limits(_CTX)

    assert out["default"]["rpm"] == 60
    assert out["default"]["tpm"] == 100000
    assert out["override_count"] == 1
    assert out["overrides"][0]["agent_identity_id"] == "cond_agt_abc"
