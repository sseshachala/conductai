"""#1005 Day 2 — auto-provision + pointer-driven workflow lookup.

Two helpers are new in ``app/routers/security.py``:

- ``_ensure_security_automation_project`` — race-safe get-or-create of the
  workspace's Security Automation project + sets the workspace pointer.
- ``_find_security_workflow`` — pointer-first lookup, legacy ``.first()``
  fallback until backfill lands.

Both dispatchers (``_trigger_security_loop``, ``trigger_fix``) now call
``_find_security_workflow`` instead of doing ``.first()`` themselves.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.routers.security import (
    _ensure_security_automation_project,
    _find_security_workflow,
)


# ── _ensure_security_automation_project ──────────────────────────────────────

def test_ensure_creates_project_and_sets_pointer_on_new_workspace():
    """INSERT succeeded → use returned id + call UPDATE workspaces once."""
    db = MagicMock()
    # First execute() is INSERT ... RETURNING id
    db.execute.return_value.first.return_value = ("proj-uuid-new",)
    # scalar() not called because RETURNING succeeded
    result = _ensure_security_automation_project(db, "ws-1")

    assert result == "proj-uuid-new"
    # Two execute calls: INSERT ... RETURNING, then UPDATE workspaces
    assert db.execute.call_count == 2


def test_ensure_returns_existing_when_insert_conflicts():
    """INSERT ON CONFLICT → RETURNING empty → look up existing row via scalar()."""
    db = MagicMock()
    # INSERT ... RETURNING returns None (ON CONFLICT DO NOTHING)
    db.execute.return_value.first.return_value = None
    # SELECT existing row via scalar()
    db.execute.return_value.scalar.return_value = "proj-uuid-existing"

    result = _ensure_security_automation_project(db, "ws-1")

    assert result == "proj-uuid-existing"
    # Three execute calls: INSERT, SELECT, UPDATE
    assert db.execute.call_count == 3


# ── _find_security_workflow ──────────────────────────────────────────────────

def _mk_workspace(pointer_project_id=None):
    ws = MagicMock()
    ws.security_automation_project_id = pointer_project_id
    return ws


def _mk_workflow():
    wf = MagicMock()
    wf.current_version_id = "wfv-1"
    return wf


def _mk_db(first_returns: list):
    """Build a db mock where .query().filter().first() returns each item in order."""
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.first.side_effect = first_returns
    return db


def test_pointer_path_used_when_workspace_has_pointer_and_workflow_matches():
    """Pointer set + workflow under project → return via pointer path (2 .first() calls)."""
    ws = _mk_workspace(pointer_project_id="proj-1")
    wf = _mk_workflow()
    db = _mk_db([ws, wf])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is wf
    # 2 first() calls: workspace + workflow. Legacy fallback NOT invoked.
    assert db.query.return_value.first.call_count == 2


def test_falls_back_when_workspace_pointer_is_null():
    """No pointer → skip pointer branch entirely, use legacy .first() (2 calls)."""
    ws = _mk_workspace(pointer_project_id=None)
    wf = _mk_workflow()
    db = _mk_db([ws, wf])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is wf
    # 2 first() calls: workspace lookup + legacy workflow lookup (pointer branch skipped).
    assert db.query.return_value.first.call_count == 2


def test_falls_back_when_pointer_set_but_workflow_not_under_project():
    """Pointer set but workflow not moved under the project → fallback returns it."""
    ws = _mk_workspace(pointer_project_id="proj-1")
    legacy_wf = _mk_workflow()
    # Order: workspace lookup, pointer-path workflow (None), legacy fallback
    db = _mk_db([ws, None, legacy_wf])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is legacy_wf
    assert db.query.return_value.first.call_count == 3


def test_returns_none_when_no_workflow_anywhere():
    """No pointer, no legacy workflow → None (uninstalled)."""
    ws = _mk_workspace(pointer_project_id=None)
    db = _mk_db([ws, None])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is None


def test_returns_none_when_workspace_missing():
    """Non-existent workspace + no legacy workflow → None (defensive)."""
    db = _mk_db([None, None])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is None
