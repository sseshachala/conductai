"""Per-workspace canary self-checks (#2209 Session 6).

Validates the ``accounting_shadow_enabled_for(workspace_id)`` decision
matrix + verifies the shadow writer respects it.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.runtime.accounting.shadow_writer import shadow_write


@pytest.fixture
def _captured_row(monkeypatch):
    captured: dict = {}
    session = MagicMock()
    session.add.side_effect = lambda row: captured.setdefault("row", row)
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=session),
    )
    return captured


def _flip(monkeypatch, *, enabled: bool, allowlist: str = ""):
    monkeypatch.setattr(settings, "guard_accounting_shadow_enabled", enabled)
    monkeypatch.setattr(
        settings, "guard_accounting_shadow_workspace_allowlist", allowlist
    )


def _write(workspace_id: uuid.UUID):
    return shadow_write(
        workspace_id=workspace_id,
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
    )


# ─── decision matrix ────────────────────────────────────────────────────────


def test_global_off_blocks_every_workspace(monkeypatch):
    _flip(monkeypatch, enabled=False, allowlist="ws-A")
    assert settings.accounting_shadow_enabled_for("ws-A") is False
    assert settings.accounting_shadow_enabled_for("any-other") is False


def test_empty_allowlist_lets_every_workspace_through(monkeypatch):
    _flip(monkeypatch, enabled=True, allowlist="")
    assert settings.accounting_shadow_enabled_for("ws-A") is True
    assert settings.accounting_shadow_enabled_for("ws-B") is True


def test_wildcard_allowlist_lets_every_workspace_through(monkeypatch):
    _flip(monkeypatch, enabled=True, allowlist="*")
    assert settings.accounting_shadow_enabled_for("ws-A") is True


def test_explicit_allowlist_restricts_to_listed_workspaces(monkeypatch):
    _flip(monkeypatch, enabled=True, allowlist="ws-A,ws-B")
    assert settings.accounting_shadow_enabled_for("ws-A") is True
    assert settings.accounting_shadow_enabled_for("ws-B") is True
    assert settings.accounting_shadow_enabled_for("ws-C") is False


def test_allowlist_ignores_whitespace_and_empty_tokens(monkeypatch):
    _flip(monkeypatch, enabled=True, allowlist=" ws-A , , ws-B ")
    assert settings.accounting_shadow_enabled_for("ws-A") is True
    assert settings.accounting_shadow_enabled_for("ws-B") is True
    assert settings.accounting_shadow_enabled_for(" ") is False


# ─── shadow_write respects the canary ───────────────────────────────────────


def test_shadow_writer_skips_workspace_not_on_allowlist(monkeypatch, _captured_row):
    _flip(monkeypatch, enabled=True, allowlist="only-this-one")
    result = _write(workspace_id=uuid.uuid4())  # different ID
    assert result is None
    assert "row" not in _captured_row


def test_shadow_writer_writes_when_workspace_on_allowlist(monkeypatch, _captured_row):
    ws = uuid.uuid4()
    _flip(monkeypatch, enabled=True, allowlist=str(ws))
    result = _write(workspace_id=ws)
    assert result is not None
    assert _captured_row["row"].workspace_id == ws


def test_shadow_writer_writes_under_wildcard(monkeypatch, _captured_row):
    _flip(monkeypatch, enabled=True, allowlist="*")
    result = _write(workspace_id=uuid.uuid4())
    assert result is not None
    assert "row" in _captured_row


def test_canary_decision_swallows_exceptions_in_settings(monkeypatch, _captured_row):
    """A broken decision function must never fail the request path."""

    class _BrokenSettings:
        guard_accounting_shadow_enabled = True

        def accounting_shadow_enabled_for(self, _ws_id):
            raise RuntimeError("broken settings")

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.settings",
        _BrokenSettings(),
    )
    result = _write(workspace_id=uuid.uuid4())
    assert result is None
    assert "row" not in _captured_row
