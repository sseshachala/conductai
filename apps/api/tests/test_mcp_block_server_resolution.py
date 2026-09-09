"""MCP block server-resolution regression coverage.

Two bugs fixed in one PR:

1. ``mcp_block._execute_mcp`` read the UUID from ``config.provider`` but the
   canvas MCP block editor writes it to ``config.server_id``. Field-name
   mismatch meant UUID resolution was silently broken for every
   canvas-authored MCP block since the field was renamed. Verified live
   2026-09-08 during the NeMo guardrails demo — a workflow with a valid
   server_id in its config still fell through to name lookup, and failed
   with "MCP server 'X' not registered" when the workspace row had a
   different display name.

2. ``resolve_mcp_server`` had ``if server_id: ... elif server_name: ...`` —
   a wrong or stale UUID short-circuited without trying the name lookup.
   Now falls through to name if UUID misses.

Both regressions land in one test file so they can't slip apart later.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.runtime.blocks.mcp_block import _execute_mcp
from app.runtime.mcp_credentials import resolve_mcp_server


# ── resolve_mcp_server: id → name fallback ────────────────────────────────────


def _fake_db_with_rows(rows_by_query: dict) -> MagicMock:
    """Build a fake db that returns different rows based on the SQL text.

    ``rows_by_query`` keys are substrings of the SQL; the first key that
    substring-matches wins. Values are the row object (or None).
    """
    db = MagicMock()

    def _execute(query, params=None):
        result = MagicMock()
        sql = str(query)
        row = None
        for needle, r in rows_by_query.items():
            if needle in sql:
                # Also honour param matching so we can differentiate id vs name
                # calls that both target mcp_servers.
                if params and "id" in params and "id = :id" in sql:
                    row = r if r and r.id == params["id"] else None
                elif params and "name" in params and "name = :name" in sql:
                    row = r if r and r.name == params["name"] else None
                else:
                    row = r
                break
        result.fetchone.return_value = row
        return result

    db.execute.side_effect = _execute
    return db


def _mock_row(row_id: str, name: str, url: str = "https://example.com/mcp") -> MagicMock:
    r = MagicMock()
    r.id = row_id
    r.name = name
    r.url = url
    r.transport = "http"
    r.encrypted_auth = None
    r.environment_id = None
    return r


def test_resolve_prefers_server_id_when_it_matches():
    row = _mock_row("uuid-A", "Conduct AI")
    db = _fake_db_with_rows({"WHERE id = :id": row})
    out = resolve_mcp_server(server_id="uuid-A", server_name="ignored", workspace_id="ws-1", db=db)
    assert out is not None
    assert out[0] == "https://example.com/mcp"


def test_resolve_falls_through_to_name_when_id_misses():
    """The bug — stale/wrong UUID must not short-circuit the name lookup."""
    row = _mock_row("uuid-A", "Conduct AI Guard")
    db = _fake_db_with_rows({
        "WHERE id = :id": None,          # UUID doesn't match anything
        "WHERE name = :name": row,        # but the name does
    })
    out = resolve_mcp_server(server_id="stale-uuid", server_name="Conduct AI Guard", workspace_id="ws-1", db=db)
    assert out is not None, "should have fallen through to name lookup"
    assert out[0] == "https://example.com/mcp"


def test_resolve_returns_none_when_neither_matches():
    db = _fake_db_with_rows({
        "WHERE id = :id": None,
        "WHERE name = :name": None,
    })
    out = resolve_mcp_server(server_id="stale", server_name="nope", workspace_id="ws-1", db=db)
    assert out is None


# ── mcp_block: reads server_id from the RIGHT config key ──────────────────────


def _run_mcp_block(config: dict) -> dict:
    """Execute _execute_mcp with the given config, mocking DB + call_tool."""
    block = {"data": {"config": {**config, "tool_name": "some_tool"}}}
    state = {}

    with patch("app.runtime.blocks.mcp_block.call_tool") as mock_call, \
         patch("app.core.database.get_db") as mock_get_db, \
         patch("app.runtime.mcp_credentials.resolve_mcp_server") as mock_resolve:
        mock_get_db.return_value = iter([MagicMock()])
        mock_resolve.return_value = ("https://example.com/mcp", "http", "tok-xxx")
        mock_call.return_value = {"verdict": "allowed"}
        result = _execute_mcp(block, state, cred_store=None, workspace_id="ws-1")
        return {"result": result, "resolve_call": mock_resolve.call_args}


def test_mcp_block_reads_server_id_from_config_server_id():
    """Canvas writes config.server_id — runtime must read from that key."""
    out = _run_mcp_block({"server_id": "canvas-uuid", "server_name": "Whatever"})
    _, kwargs = out["resolve_call"]
    assert kwargs["server_id"] == "canvas-uuid", (
        "runtime should have picked up the UUID from config.server_id — the "
        "field the canvas MCP block editor actually writes"
    )


def test_mcp_block_falls_back_to_provider_key_for_legacy_configs():
    """Older configs used 'provider' as the UUID key. Keep it working."""
    out = _run_mcp_block({"provider": "legacy-uuid", "server_name": "Whatever"})
    _, kwargs = out["resolve_call"]
    assert kwargs["server_id"] == "legacy-uuid"


def test_mcp_block_prefers_server_id_over_provider_if_both_set():
    """If both keys exist, server_id (new) wins over provider (legacy)."""
    out = _run_mcp_block({
        "server_id": "new-uuid",
        "provider":  "old-uuid",
        "server_name": "Whatever",
    })
    _, kwargs = out["resolve_call"]
    assert kwargs["server_id"] == "new-uuid"
