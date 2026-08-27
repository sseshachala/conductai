"""Direct DB tests for the three run/workflow-detail tools on GLens Executor (#1253).

Exercises:
- `_tool_get_workflow_details` — by workflow_id, by name, with/without latest run
- `_tool_list_runs` — status + workflow_id filter, joins to Workflow
- `_tool_get_run` — one run, org-scoped
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.regression.conftest import requires_db


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def ws_and_executor():
    from app.core.database import SessionLocal
    from app.models.workspace import Workspace
    from app.modules.glens.executor import Executor

    ws_id = uuid.uuid4()
    tag = ws_id.hex[:8]
    with SessionLocal() as db:
        db.add(Workspace(
            id=ws_id, name="glens-runs-" + tag, owner_id="user_test_runs_" + tag,
            plan="free", is_approved=True, created_at=_now(), updated_at=_now(),
        ))
        db.commit()

    db = SessionLocal()
    try:
        yield db, str(ws_id), Executor(db, str(ws_id))
    finally:
        db.close()
        # Raw SQL cleanup — avoids re-importing app.models.run / workflow at
        # teardown time. test_token_paths.py leaks a MagicMock into
        # sys.modules["app.models.run"], and re-importing here would pick it
        # up and fail on `db2.query(Run)` coercion.
        from sqlalchemy import text as sa_text
        with SessionLocal() as db2:
            db2.execute(sa_text("DELETE FROM runs WHERE workspace_id = :ws"), {"ws": ws_id})
            db2.execute(sa_text(
                "DELETE FROM workflow_versions "
                "WHERE workflow_id IN (SELECT id FROM workflows WHERE workspace_id = :ws)"
            ), {"ws": ws_id})
            db2.execute(sa_text("DELETE FROM workflows WHERE workspace_id = :ws"), {"ws": ws_id})
            db2.execute(sa_text("DELETE FROM workspaces WHERE id = :ws"), {"ws": ws_id})
            db2.commit()


def _seed_workflow_with_version(db, workspace_id: str, name: str):
    """Raw INSERT — see _seed_run comment. test_token_paths.py leaks
    MagicMocks into sys.modules for app.models.workflow / app.models.run,
    so fresh imports here would fail on ORM coercion."""
    from sqlalchemy import text as sa_text
    wf_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    now_ts = _now()
    db.execute(
        sa_text(
            "INSERT INTO workflows "
            "(id, workspace_id, name, default_mode, guard_enabled, "
            " agent_identity_required, created_at, updated_at, is_template) "
            "VALUES (:id, :ws, :nm, 'dag', TRUE, TRUE, :now, :now, FALSE)"
        ),
        {"id": wf_id, "ws": uuid.UUID(workspace_id), "nm": name, "now": now_ts},
    )
    db.execute(
        sa_text(
            "INSERT INTO workflow_versions "
            "(id, workflow_id, graph, created_at) "
            "VALUES (:id, :wid, CAST(:graph AS jsonb), :now)"
        ),
        {"id": ver_id, "wid": wf_id, "graph": '{"nodes": [], "edges": []}', "now": now_ts},
    )
    db.commit()

    class _WF:
        pass
    class _V:
        pass
    wf = _WF()
    wf.id = wf_id
    wf.name = name
    ver = _V()
    ver.id = ver_id
    return wf, ver


def _seed_run(db, workspace_id: str, ver_id, status="succeeded", when=None):
    """Raw INSERT — avoids ORM state pitfalls with Run's cascade
    relationships. Same pattern as `_seed_event` in test_workflow_tools.py.
    Returns a lightweight object with `.id` so callers can pass it to
    `_tool_get_run`, etc."""
    from sqlalchemy import text as sa_text
    run_id = uuid.uuid4()
    now_ts = _now()
    completed = now_ts if status in ("succeeded", "failed", "cancelled") else None
    db.execute(
        sa_text(
            "INSERT INTO runs "
            "(id, workflow_version_id, workspace_id, triggered_by, status, "
            " started_at, completed_at, actual_turns, state, created_at, attempt_count) "
            "VALUES (:id, :vid, :wid, :tby, :st, :sa, :ca, :at, "
            "        CAST(:state AS jsonb), :now, 0)"
        ),
        {
            "id": run_id, "vid": ver_id, "wid": uuid.UUID(workspace_id),
            "tby": "test", "st": status,
            "sa": when or now_ts, "ca": completed,
            "at": 3, "state": "{}", "now": now_ts,
        },
    )
    db.commit()

    class _R:
        pass
    r = _R()
    r.id = run_id
    return r


# ─────────────────────────────────────────────────────────────────────────────
# get_workflow_details
# ─────────────────────────────────────────────────────────────────────────────

@requires_db
def test_get_workflow_details_by_id(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    wf, ver = _seed_workflow_with_version(db, ws_id, "alpha")
    _seed_run(db, ws_id, ver.id, status="succeeded")

    out = ex._tool_get_workflow_details(workflow_id=str(wf.id))
    assert out["name"] == "alpha"
    assert out["workflow_id"] == str(wf.id)
    assert out["latest_run"] is not None
    assert out["latest_run"]["status"] == "succeeded"


@requires_db
def test_get_workflow_details_by_name(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _seed_workflow_with_version(db, ws_id, "beta")

    out = ex._tool_get_workflow_details(name="beta")
    assert out["name"] == "beta"
    assert out["latest_run"] is None


@requires_db
def test_get_workflow_details_missing_returns_error(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    out = ex._tool_get_workflow_details(name="nonexistent")
    assert "error" in out


# ─────────────────────────────────────────────────────────────────────────────
# list_runs
# ─────────────────────────────────────────────────────────────────────────────

@requires_db
def test_list_runs_returns_recent(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _, ver = _seed_workflow_with_version(db, ws_id, "wf-1")
    _seed_run(db, ws_id, ver.id, status="succeeded")
    _seed_run(db, ws_id, ver.id, status="failed")

    rows = ex._tool_list_runs()
    assert len(rows) == 2
    assert {r["status"] for r in rows} == {"succeeded", "failed"}


@requires_db
def test_list_runs_filter_by_status(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _, ver = _seed_workflow_with_version(db, ws_id, "wf-1")
    _seed_run(db, ws_id, ver.id, status="succeeded")
    _seed_run(db, ws_id, ver.id, status="failed")

    only_failed = ex._tool_list_runs(status="failed")
    assert len(only_failed) == 1 and only_failed[0]["status"] == "failed"


@requires_db
def test_list_runs_filter_by_workflow(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    wf1, ver1 = _seed_workflow_with_version(db, ws_id, "wf-1")
    _, ver2 = _seed_workflow_with_version(db, ws_id, "wf-2")
    _seed_run(db, ws_id, ver1.id, status="succeeded")
    _seed_run(db, ws_id, ver2.id, status="succeeded")

    rows = ex._tool_list_runs(workflow_id=str(wf1.id))
    assert len(rows) == 1 and rows[0]["workflow_name"] == "wf-1"


# ─────────────────────────────────────────────────────────────────────────────
# get_run
# ─────────────────────────────────────────────────────────────────────────────

@requires_db
def test_get_run_returns_full_row(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    wf, ver = _seed_workflow_with_version(db, ws_id, "wf-1")
    run = _seed_run(db, ws_id, ver.id, status="succeeded")

    out = ex._tool_get_run(run_id=str(run.id))
    assert out["run_id"] == str(run.id)
    assert out["workflow_name"] == "wf-1"
    assert out["status"] == "succeeded"
    assert out["actual_turns"] == 3


@requires_db
def test_get_run_missing_returns_error(ws_and_executor):
    _db, _ws_id, ex = ws_and_executor
    out = ex._tool_get_run(run_id=str(uuid.uuid4()))
    assert "error" in out


@requires_db
def test_get_run_rejects_non_uuid(ws_and_executor):
    _db, _ws_id, ex = ws_and_executor
    out = ex._tool_get_run(run_id="not-a-uuid")
    assert "error" in out
