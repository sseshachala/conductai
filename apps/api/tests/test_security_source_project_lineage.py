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
