"""Direct DB tests for the two workflow tools on GLens Executor.

Exercises:
- `_tool_list_workflows` — active/archived/all filter, org-scoped
- `_tool_get_blocked_workflows` — group-by workflow_id, block_count rank,
  top_rule_id via Postgres MODE() WITHIN GROUP, workflow_id + rule_id filters

Requires a real Postgres (uses the same `requires_db` marker as the
regression suite). Follows the `seeded_workspace` pattern: create a fresh
workspace + insert test rows in setup, tear everything down in teardown.
"""
from __future__ import annotations

from app.tools.registrations.lens.workflows import get_blocked_workflows, list_workflows


import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.regression.conftest import requires_db


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def ws_and_executor():
    """Fresh workspace + bound Executor. Cleans up all seeded rows on teardown."""
    from app.core.database import SessionLocal
    from app.models.workspace import Workspace
    from app.modules.glens.executor import Executor

    ws_id = uuid.uuid4()
    tag = ws_id.hex[:8]
    with SessionLocal() as db:
        db.add(Workspace(
            id=ws_id,
            name="glens-wf-" + tag,
            owner_id="user_test_glens_wf_" + tag,
            plan="free",
            is_approved=True,
            created_at=_now(),
            updated_at=_now(),
        ))
        db.commit()

    db = SessionLocal()
    try:
        yield db, str(ws_id), Executor(db, str(ws_id))
    finally:
        db.close()
        with SessionLocal() as db2:
            from app.modules.guard.models import GuardAuditEvent
            from app.models.workflow import Workflow
            db2.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id == ws_id).delete()
            db2.query(Workflow).filter(Workflow.workspace_id == ws_id).delete()
            ws = db2.get(Workspace, ws_id)
            if ws is not None:
                db2.delete(ws)
            db2.commit()


def _seed_workflow(db, workspace_id, name, archived=False):
    from app.models.workflow import Workflow
    wf = Workflow(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(workspace_id),
        name=name,
        default_mode="dag",
        guard_enabled=True,
        agent_identity_required=True,
        created_at=_now(),
        updated_at=_now(),
        archived_at=_now() if archived else None,
    )
    db.add(wf)
    db.commit()
    return str(wf.id)


def _seed_event(db, workspace_id, workflow_id, workflow_name, rule_id, decision="blocked", when=None):
    """Insert with an explicit column list so the test is immune to future
    guard_audit_events column additions (ORM insert would name every column)."""
    from sqlalchemy import text as sa_text
    db.execute(
        sa_text(
            "INSERT INTO guard_audit_events "
            "(id, workspace_id, ai_tool, source, decision, rule_id, "
            " conductai_workflow_id, conductai_workflow, ts) "
            "VALUES (:id, :ws, 'test_agent', 'hook', :dec, :rule, :wfid, :wfname, :ts)"
        ),
        {
            "id": uuid.uuid4(),
            "ws": uuid.UUID(workspace_id),
            "dec": decision,
            "rule": rule_id,
            "wfid": workflow_id,
            "wfname": workflow_name,
            "ts": when or _now(),
        },
    )
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# list_workflows
# ─────────────────────────────────────────────────────────────────────────────

@requires_db
def test_list_workflows_active_by_default(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _seed_workflow(db, ws_id, "alpha")
    _seed_workflow(db, ws_id, "beta")
    _seed_workflow(db, ws_id, "gamma", archived=True)

    rows = list_workflows(ex)
    names = {r["name"] for r in rows}
    assert names == {"alpha", "beta"}, names
    assert all(r["archived"] is False for r in rows)


@requires_db
def test_list_workflows_status_archived_and_all(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _seed_workflow(db, ws_id, "active-1")
    _seed_workflow(db, ws_id, "archived-1", archived=True)

    assert {r["name"] for r in list_workflows(ex, status="archived")} == {"archived-1"}
    assert {r["name"] for r in list_workflows(ex, status="all")} == {"active-1", "archived-1"}


# ─────────────────────────────────────────────────────────────────────────────
# get_blocked_workflows — the interesting one (MODE() WITHIN GROUP)
# ─────────────────────────────────────────────────────────────────────────────

@requires_db
def test_get_blocked_workflows_ranks_by_count_and_picks_top_rule(ws_and_executor):
    """A has 3 blocks (R1×2, R2×1) → top R1. B has 5 blocks (R2×3, R3×2) → top R2.
    C has 1 allowed event only → must NOT appear. Order = B, A."""
    db, ws_id, ex = ws_and_executor
    wf_a, wf_b, wf_c = "wf-a", "wf-b", "wf-c"

    for rule in ("R1", "R1", "R2"):
        _seed_event(db, ws_id, wf_a, "Alpha", rule)
    for rule in ("R2", "R2", "R2", "R3", "R3"):
        _seed_event(db, ws_id, wf_b, "Bravo", rule)
    _seed_event(db, ws_id, wf_c, "Charlie", "R1", decision="allowed")

    rows = get_blocked_workflows(ex)

    assert [r["workflow_id"] for r in rows] == [wf_b, wf_a], rows
    assert rows[0]["name"] == "Bravo" and rows[0]["block_count"] == 5 and rows[0]["top_rule_id"] == "R2"
    assert rows[1]["name"] == "Alpha" and rows[1]["block_count"] == 3 and rows[1]["top_rule_id"] == "R1"
    assert all(r["workflow_id"] != wf_c for r in rows), "allowed-only workflow leaked in"


@requires_db
def test_get_blocked_workflows_filters_by_workflow_and_rule(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _seed_event(db, ws_id, "wf-a", "Alpha", "R1")
    _seed_event(db, ws_id, "wf-a", "Alpha", "R2")
    _seed_event(db, ws_id, "wf-b", "Bravo", "R1")

    only_a = get_blocked_workflows(ex, workflow_id="wf-a")
    assert len(only_a) == 1 and only_a[0]["workflow_id"] == "wf-a" and only_a[0]["block_count"] == 2

    only_r1 = get_blocked_workflows(ex, rule_id="R1")
    assert {r["workflow_id"] for r in only_r1} == {"wf-a", "wf-b"}
    assert all(r["block_count"] == 1 for r in only_r1)


@requires_db
def test_get_blocked_workflows_bounded_by_since_until(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    old = _now() - timedelta(days=10)
    recent = _now() - timedelta(hours=1)
    _seed_event(db, ws_id, "wf-a", "Alpha", "R1", when=old)
    _seed_event(db, ws_id, "wf-a", "Alpha", "R1", when=recent)

    since = (_now() - timedelta(days=1)).isoformat()
    rows = get_blocked_workflows(ex, since=since)
    assert len(rows) == 1 and rows[0]["block_count"] == 1
