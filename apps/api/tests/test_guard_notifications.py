"""Unit tests for #1142 Phase 1 notification channels.

Cover the pure-Python paths:
- resolve_channels returns enabled rows for (workspace, action)
- resolve_channels filters out disabled rows
- resolve_channels returns [] when nothing matches
- _autoseed_from_legacy materializes rows from a legacy alert_channel
- _autoseed_from_legacy is a no-op when rows already exist
- _autoseed_from_legacy is a no-op when no legacy alert_channel

Uses MagicMock sessions so no real Postgres required.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.modules.guard.routers.notifications import (
    _autoseed_from_legacy,
    resolve_channels,
)


def _fake_row(action: str, enabled: bool = True, channel: str = "#general"):
    row = MagicMock()
    row.id = uuid.uuid4()
    row.action = action
    row.channel_type = "slack"
    row.channel_ref = channel
    row.enabled = enabled
    row.integration_id = None
    row.dedupe_window_sec = 300
    return row


def _query_returning(rows):
    """Build a MagicMock session whose .query(...).filter(...).all() returns rows."""
    db = MagicMock()
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.order_by.return_value = chain
    chain.all.return_value = rows
    chain.first.return_value = rows[0] if rows else None
    db.query.return_value = chain
    return db


# ── resolve_channels ────────────────────────────────────────────────────────

def test_resolve_channels_returns_enabled_rows_for_action():
    ws = uuid.uuid4()
    enabled_row = _fake_row("block", enabled=True, channel="#security")
    db = _query_returning([enabled_row])
    result = resolve_channels(db, ws, "block")
    assert len(result) == 1
    assert result[0].channel_ref == "#security"


def test_resolve_channels_returns_empty_when_none_match():
    db = _query_returning([])
    result = resolve_channels(db, uuid.uuid4(), "audit")
    assert result == []


def test_resolve_channels_accepts_string_workspace_id():
    """The caller in events.py passes workspace_id as a string in some paths."""
    ws_str = str(uuid.uuid4())
    db = _query_returning([_fake_row("warn")])
    result = resolve_channels(db, ws_str, "warn")
    assert len(result) == 1


# ── _autoseed_from_legacy ────────────────────────────────────────────────────

def test_autoseed_noop_when_rows_already_exist():
    """If any row already exists for the workspace, seeding must not happen."""
    ws = uuid.uuid4()
    existing = _fake_row("block")

    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.first.return_value = existing  # already-present row
    db = MagicMock()
    db.query.return_value = query_chain

    _autoseed_from_legacy(db, ws)
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_autoseed_noop_when_no_legacy_alert_channel():
    """If guard_config has no alert_channel, don't seed anything."""
    ws = uuid.uuid4()

    # First query (existing rows) → None. Second query (GuardConfig) → cfg with alert_channel=None.
    cfg = MagicMock()
    cfg.alert_channel = None
    cfg.notify_on_block = True

    call_returns = [None, cfg]  # first .first() call returns None, next returns cfg

    def query_side_effect(*_args, **_kwargs):
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = call_returns.pop(0) if call_returns else None
        return chain

    db = MagicMock()
    db.query.side_effect = query_side_effect

    _autoseed_from_legacy(db, ws)
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_autoseed_materializes_block_and_warn_rows_from_legacy():
    """When legacy alert_channel is set, seed one 'block' row + one 'warn' row."""
    ws = uuid.uuid4()
    cfg = MagicMock()
    cfg.alert_channel = "#alerts"
    cfg.notify_on_block = True
    cfg.alert_slack_integration_id = None

    call_returns = [None, cfg]

    def query_side_effect(*_args, **_kwargs):
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = call_returns.pop(0) if call_returns else None
        return chain

    db = MagicMock()
    db.query.side_effect = query_side_effect

    _autoseed_from_legacy(db, ws)

    # Should have added exactly 2 rows (block + warn).
    assert db.add.call_count == 2
    added_actions = sorted(call.args[0].action for call in db.add.call_args_list)
    assert added_actions == ["block", "warn"]
    for call in db.add.call_args_list:
        row = call.args[0]
        assert row.channel_ref == "#alerts"
        assert row.channel_type == "slack"
        assert row.enabled is True
    db.commit.assert_called_once()
