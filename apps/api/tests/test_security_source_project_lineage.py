"""#1005 step 5 — SecurityFinding.source_project_id lineage resolver.

_resolve_source_project_id walks Run → WorkflowVersion → Workflow.project_id
so Guard Activity can render Source · Owner · Target without new JOINs later.
Best-effort — returns None whenever the chain has any gap.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.routers.security import _resolve_source_project_id


def _mk_db(row):
    """Mock db.execute(...).first() → row (a 1-tuple or None)."""
    db = MagicMock()
    db.execute.return_value.first.return_value = row
    return db


def test_returns_none_when_source_run_id_is_none():
    """Manual finding (no source run) → no lineage. Zero DB calls."""
    db = MagicMock()

    result = _resolve_source_project_id(db, None)

    assert result is None
    db.execute.assert_not_called()


def test_returns_none_when_source_run_id_is_empty_string():
    """Empty string is falsy → no lookup, no lineage."""
    db = MagicMock()

    result = _resolve_source_project_id(db, "")

    assert result is None
    db.execute.assert_not_called()


def test_returns_project_id_when_chain_resolves():
    """Run → WorkflowVersion → Workflow.project_id → return as string."""
    db = _mk_db(("proj-abc-123",))

    result = _resolve_source_project_id(db, "run-uuid")

    assert result == "proj-abc-123"
    db.execute.assert_called_once()


def test_returns_none_when_run_not_found():
    """SQL returns no rows → None."""
    db = _mk_db(None)

    result = _resolve_source_project_id(db, "run-uuid")

    assert result is None


def test_returns_none_when_workflow_has_no_project_id():
    """Workflow row exists but project_id is NULL → None (not the string 'None')."""
    db = _mk_db((None,))

    result = _resolve_source_project_id(db, "run-uuid")

    assert result is None


def test_swallows_db_errors_and_returns_none():
    """Invalid UUID → psycopg2 raises → best-effort returns None, never crashes ingest."""
    db = MagicMock()
    db.execute.side_effect = Exception("invalid input syntax for type uuid")

    result = _resolve_source_project_id(db, "not-a-uuid")

    assert result is None


# ── _load_owner_project_name (#1008 lineage — Owner) ─────────────────────────

from app.routers.security import (
    _attach_source_project_name,
    _load_owner_project_name,
)


def test_owner_returns_project_name_when_pointer_set():
    """workspace pointer → JOIN returns project name."""
    db = MagicMock()
    db.execute.return_value.first.return_value = ("Security Automation · abc123",)
    assert _load_owner_project_name(db, "ws-1") == "Security Automation · abc123"


def test_owner_returns_none_when_no_workspace_row():
    """No such workspace → None. Defensive."""
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    assert _load_owner_project_name(db, "ws-missing") is None


def test_owner_returns_none_when_pointer_null():
    """Workspace exists but pointer null → LEFT JOIN returns (None,)."""
    db = MagicMock()
    db.execute.return_value.first.return_value = (None,)
    assert _load_owner_project_name(db, "ws-1") is None


# ── _attach_source_project_name (#1008 lineage — Source) ──────────────────────

def test_attach_populates_name_from_batch_select():
    """Batched SELECT keyed by source_project_id populates .source_project_name."""
    f1 = MagicMock(source_project_id="proj-a")
    f2 = MagicMock(source_project_id="proj-b")
    f3 = MagicMock(source_project_id=None)
    db = MagicMock()
    db.execute.return_value.__iter__ = lambda self: iter([
        ("proj-a", "Scanner A"),
        ("proj-b", "Scanner B"),
    ])
    _attach_source_project_name(db, [f1, f2, f3])
    assert f1.source_project_name == "Scanner A"
    assert f2.source_project_name == "Scanner B"
    assert f3.source_project_name is None


def test_attach_skips_db_when_no_findings_have_source_project():
    """Zero rows have source_project_id → no SELECT issued; every finding gets None."""
    f1 = MagicMock(source_project_id=None)
    f2 = MagicMock(source_project_id=None)
    db = MagicMock()
    _attach_source_project_name(db, [f1, f2])
    assert f1.source_project_name is None
    assert f2.source_project_name is None
    db.execute.assert_not_called()


def test_attach_swallows_db_errors_and_defaults_to_none():
    """DB error during batch SELECT → every finding gets None, ingest keeps going."""
    f1 = MagicMock(source_project_id="proj-a")
    db = MagicMock()
    db.execute.side_effect = Exception("boom")
    _attach_source_project_name(db, [f1])
    assert f1.source_project_name is None
