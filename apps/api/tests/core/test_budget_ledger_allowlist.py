"""Workspace-allowlist gate for the budget ledger canary.

Semantics guarded here (see budget_ledger.enabled_for):

    global flag OFF                                    -> no workspace enforces
    global flag ON + allowlist unset/empty             -> all workspaces enforce
    global flag ON + allowlist = '*'                   -> all workspaces enforce
    global flag ON + allowlist = 'ws1,ws2'             -> only ws1, ws2 enforce
    global flag ON + allowlist set + workspace_id=None -> fail-closed

The allowlist is read from ``BUDGET_LEDGER_ALLOWLIST`` on every call
so ops can rotate workspaces via a config change without a restart.
Match is case-insensitive to guard against a mixed-case UUID
comparison bug.
"""
from __future__ import annotations

import os
from unittest.mock import patch


def _clear_env(monkeypatch):
    monkeypatch.delenv("BUDGET_LEDGER_ENABLED", raising=False)
    monkeypatch.delenv("BUDGET_LEDGER_ALLOWLIST", raising=False)


def test_global_flag_off_never_enforces(monkeypatch):
    _clear_env(monkeypatch)
    from app.core.budget_ledger import enabled_for

    monkeypatch.setenv("BUDGET_LEDGER_ALLOWLIST", "ws1,ws2")  # ignored while flag off
    assert enabled_for("ws1") is False
    assert enabled_for("ws2") is False
    assert enabled_for(None) is False


def test_global_flag_on_no_allowlist_enforces_everywhere(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    from app.core.budget_ledger import enabled_for

    assert enabled_for("any-workspace") is True
    assert enabled_for("another-one") is True
    assert enabled_for(None) is True  # backward compat — no restriction


def test_global_flag_on_empty_allowlist_enforces_everywhere(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    monkeypatch.setenv("BUDGET_LEDGER_ALLOWLIST", "")
    from app.core.budget_ledger import enabled_for

    assert enabled_for("any-workspace") is True


def test_wildcard_allowlist_enforces_everywhere(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    monkeypatch.setenv("BUDGET_LEDGER_ALLOWLIST", "*")
    from app.core.budget_ledger import enabled_for

    assert enabled_for("workspace-a") is True
    assert enabled_for("workspace-b") is True


def test_explicit_allowlist_only_matches_listed_workspaces(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    monkeypatch.setenv("BUDGET_LEDGER_ALLOWLIST", "canary-a,canary-b")
    from app.core.budget_ledger import enabled_for

    assert enabled_for("canary-a") is True
    assert enabled_for("canary-b") is True
    assert enabled_for("outside") is False


def test_allowlist_match_is_case_insensitive(monkeypatch):
    """UUID strings vary in case across serialization boundaries. Match
    lower-case both sides so ``ws-ABC`` and ``WS-abc`` never diverge."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    monkeypatch.setenv("BUDGET_LEDGER_ALLOWLIST", "ws-ABC")
    from app.core.budget_ledger import enabled_for

    assert enabled_for("ws-abc") is True
    assert enabled_for("WS-ABC") is True
    assert enabled_for("Ws-Abc") is True


def test_workspace_none_with_allowlist_fails_closed(monkeypatch):
    """A code path with no workspace context cannot pass the allowlist.
    Return False so accidental enforcement never leaks across the gate."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    monkeypatch.setenv("BUDGET_LEDGER_ALLOWLIST", "canary-a")
    from app.core.budget_ledger import enabled_for

    assert enabled_for(None) is False


def test_reserve_helper_uses_enabled_for(monkeypatch):
    """Grep-guard: reserve_budgets_for_request must call enabled_for so
    the allowlist actually gates the gateway path."""
    import inspect

    from app.modules.guard import gateway_lifecycle

    src = inspect.getsource(gateway_lifecycle.reserve_budgets_for_request)
    assert "_ledger_enabled_for(workspace_id)" in src, (
        "reserve_budgets_for_request must call enabled_for(workspace_id) "
        "so the canary allowlist gates gateway enforcement. See the "
        "workspace-allowlist gate."
    )


def test_reserve_helper_emits_enforcement_metric(monkeypatch):
    """The reserve helper increments GUARD_BUDGET_ENFORCEMENT_ACTIVE
    for each admitted workspace so ops can observe canary traffic."""
    import inspect

    from app.modules.guard import gateway_lifecycle

    src = inspect.getsource(gateway_lifecycle.reserve_budgets_for_request)
    assert "GUARD_BUDGET_ENFORCEMENT_ACTIVE" in src, (
        "enforcement metric missing — ops has no signal for which "
        "workspaces are actively on the ledger."
    )


def test_allowlist_helper_parses_csv_and_normalizes(monkeypatch):
    """The parser must strip whitespace and lowercase entries so
    typos in the env value don't silently drop a workspace."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("BUDGET_LEDGER_ALLOWLIST", "  Ws-A ,  ws-B  ,,")
    from app.core.budget_ledger import _allowlisted_workspaces

    allow = _allowlisted_workspaces()
    assert allow == {"ws-a", "ws-b"}
