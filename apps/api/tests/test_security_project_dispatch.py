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

import pytest
from fastapi import HTTPException

from app.routers.security import (
    _ensure_security_automation_project,
    _find_security_workflow,
    apply_security_install_guard,
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


def test_returns_workflow_when_pointer_set_and_workflow_under_project():
    """Pointer set + workflow under that project → return it."""
    ws = _mk_workspace(pointer_project_id="proj-1")
    wf = _mk_workflow()
    db = _mk_db([ws, wf])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is wf
    # 2 first() calls: workspace + workflow. No legacy path.
    assert db.query.return_value.first.call_count == 2


def test_returns_none_when_workspace_pointer_is_null():
    """No pointer (never installed a security playbook) → None. Only 1 first() call."""
    ws = _mk_workspace(pointer_project_id=None)
    db = _mk_db([ws])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is None
    assert db.query.return_value.first.call_count == 1


def test_returns_none_when_workflow_not_under_project():
    """Pointer set but no matching workflow → None (unlike the legacy behavior)."""
    ws = _mk_workspace(pointer_project_id="proj-1")
    db = _mk_db([ws, None])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is None
    assert db.query.return_value.first.call_count == 2


def test_returns_none_when_workspace_missing():
    """Non-existent workspace → None (defensive). One first() call."""
    db = _mk_db([None])

    result = _find_security_workflow(db, "ws-1", "security_loop")

    assert result is None
    assert db.query.return_value.first.call_count == 1


# ── apply_security_install_guard (#1005 step 4) ──────────────────────────────

def _mk_provision_db(project_id):
    """Mock db.execute that mimics _ensure_security_automation_project succeeding."""
    db = MagicMock()
    # First execute: INSERT ... RETURNING (project_id,)
    db.execute.return_value.first.return_value = (project_id,)
    return db


def test_install_guard_passthrough_for_non_security_templates():
    """Non-security template → return None so caller passes body.project_id through."""
    db = MagicMock()
    assert apply_security_install_guard(db, "ws-1", "autopilot", "some-proj") is None
    assert apply_security_install_guard(db, "ws-1", None, None) is None
    db.execute.assert_not_called()  # short-circuit, no DB touched


def test_install_guard_auto_provisions_for_security_loop_when_no_project_supplied():
    """security_loop install without project_id → return the auto-provisioned id."""
    db = _mk_provision_db("proj-sec-1")

    result = apply_security_install_guard(db, "ws-1", "security_loop", None)

    assert result == "proj-sec-1"


def test_install_guard_auto_provisions_for_security_autopilot_fix():
    """security_autopilot_fix install → same auto-provision path."""
    db = _mk_provision_db("proj-sec-1")

    result = apply_security_install_guard(db, "ws-1", "security_autopilot_fix", None)

    assert result == "proj-sec-1"


def test_install_guard_accepts_correct_project_id():
    """If caller supplies the same project_id we would auto-provision → accept."""
    db = _mk_provision_db("proj-sec-1")

    result = apply_security_install_guard(db, "ws-1", "security_loop", "proj-sec-1")

    assert result == "proj-sec-1"


def test_install_guard_rejects_wrong_project_id():
    """security_loop install into a non-security project → 400."""
    db = _mk_provision_db("proj-sec-1")

    with pytest.raises(HTTPException) as exc:
        apply_security_install_guard(db, "ws-1", "security_loop", "proj-user")

    assert exc.value.status_code == 400
    assert "security_loop" in exc.value.detail
    assert "Security Automation project" in exc.value.detail
