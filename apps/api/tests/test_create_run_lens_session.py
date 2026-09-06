"""#1515 — Canvas Run: mint Lens session at run trigger time.

Verifies the `create_lens_session` flag on `POST /workflows/{id}/runs`.
Uses raw SQL for setup + assertions to sidestep the sys.modules stubs that
`tests/test_token_paths.py` installs for app.models.run / app.models.workflow.
Same pattern as `tests/glens/test_run_tools.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch as _patch

import pytest
from sqlalchemy import event
from sqlalchemy import text as _sql
from sqlalchemy.orm import Session

from tests.regression.conftest import requires_db


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def ws_and_workflow():
    """Fresh workspace + workflow + version via raw SQL — bypasses the
    sys.modules stubs from tests/test_token_paths.py that coerce ORM models
    into MagicMocks. Same pattern as tests/glens/test_run_tools.py.

    Cleanup uses the SQLAlchemy SAVEPOINT pattern (closes #1643): one
    connection, outer transaction never commits, router's own db.commit()
    calls release nested SAVEPOINTs instead of the outer txn. Teardown
    rollback wipes everything — no destructive DDL/DML in source, so
    ConductGuard's account-deletion rule doesn't fire.
    """
    from app.core.database import engine

    conn = engine.connect()
    outer = conn.begin()
    db = Session(bind=conn)
    db.begin_nested()

    @event.listens_for(db, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    ws_id = uuid.uuid4()
    wf_id = uuid.uuid4()
    version_id = uuid.uuid4()
    tag = ws_id.hex[:8]

    db.execute(_sql(
        "INSERT INTO workspaces "
        "(id, name, owner_id, plan, is_approved, created_at, updated_at) "
        "VALUES (:id, :nm, :oid, 'free', TRUE, :now, :now)"
    ), {"id": ws_id, "nm": "run-lens-" + tag,
        "oid": "user_test_run_lens_" + tag, "now": _now()})
    db.execute(_sql(
        "INSERT INTO workflows "
        "(id, workspace_id, name, default_mode, guard_enabled, "
        " agent_identity_required, created_at, updated_at, is_template) "
        "VALUES (:id, :ws, :nm, 'dag', TRUE, TRUE, :now, :now, FALSE)"
    ), {"id": wf_id, "ws": ws_id, "nm": "Test WF", "now": _now()})
    db.execute(_sql(
        "INSERT INTO workflow_versions "
        "(id, workflow_id, graph, created_at) "
        "VALUES (:id, :wid, CAST(:graph AS jsonb), :now)"
    ), {"id": version_id, "wid": wf_id,
        "graph": '{"nodes":[],"edges":[]}', "now": _now()})
    db.execute(_sql(
        "UPDATE workflows SET current_version_id = :vid WHERE id = :wid"
    ), {"vid": version_id, "wid": wf_id})
    db.flush()

    try:
        yield db, str(ws_id), str(wf_id)
    finally:
        db.close()
        if outer.is_active:
            outer.rollback()
        conn.close()


@requires_db
def test_no_lens_session_by_default(ws_and_workflow):
    """No flag → run.session_id stays NULL, no GlensChatSession row."""
    from app.routers.runs import create_run
    from app.schemas.run import RunCreate

    db, ws_id, wf_id = ws_and_workflow
    ws_uuid = uuid.UUID(ws_id)

    before = db.execute(_sql(
        "SELECT COUNT(*) FROM glens_chat_sessions WHERE workspace_id = :ws"
    ), {"ws": ws_uuid}).scalar()

    body = RunCreate(triggered_by="manual", dry_run=False,
                     initial_state={"__manual": True})
    # Mock the Redis enqueue — CI runs without a redis service.
    with _patch("app.routers.runs._enqueue_run"):
        result = create_run(
            workflow_id=uuid.UUID(wf_id),
            body=body,
            db=db,
            workspace_id=ws_id,
            _="dummy-permission-token",
            caller_id="user_test",
        )

    assert result.session_id is None
    row = db.execute(_sql(
        "SELECT session_id FROM runs WHERE id = :id"
    ), {"id": result.id}).first()
    assert row is not None
    assert row[0] is None
    after = db.execute(_sql(
        "SELECT COUNT(*) FROM glens_chat_sessions WHERE workspace_id = :ws"
    ), {"ws": ws_uuid}).scalar()
    assert after == before


@requires_db
def test_create_lens_session_flag_mints_and_links(ws_and_workflow):
    """Flag ON → new GlensChatSession row; run.session_id links; response
    carries it."""
    from app.routers.runs import create_run
    from app.schemas.run import RunCreate

    db, ws_id, wf_id = ws_and_workflow
    ws_uuid = uuid.UUID(ws_id)

    body = RunCreate(triggered_by="manual", dry_run=False,
                     create_lens_session=True,
                     initial_state={"__manual": True})
    with _patch("app.routers.runs._enqueue_run"):
        result = create_run(
            workflow_id=uuid.UUID(wf_id),
            body=body,
            db=db,
            workspace_id=ws_id,
            _="dummy-permission-token",
            caller_id="user_test",
        )

    assert result.session_id is not None
    row = db.execute(_sql(
        "SELECT session_id FROM runs WHERE id = :id"
    ), {"id": result.id}).first()
    assert row is not None
    assert row[0] == result.session_id

    sess = db.execute(_sql(
        "SELECT title, messages, token_hash "
        "FROM glens_chat_sessions "
        "WHERE id = :sid AND workspace_id = :ws"
    ), {"sid": result.session_id, "ws": ws_uuid}).first()
    assert sess is not None
    assert sess[0] == "Run: Test WF"
    assert sess[1] == "[]"
    # Token + AgentIdentity mint lazily on first chat message; both stay NULL
    # here. That's the whole point — canvas Run doesn't need chat auth.
    assert sess[2] is None


@requires_db
def test_session_and_run_commit_atomically(ws_and_workflow):
    """Self-review guard: session mint + Run insert must live in the same
    transaction. If the commit fails, the session must roll back — otherwise
    the user sees a ghost 'Run: X' entry in the Lens sidebar for a run that
    was never created."""
    from app.routers.runs import create_run
    from app.schemas.run import RunCreate

    db, ws_id, wf_id = ws_and_workflow
    ws_uuid = uuid.UUID(ws_id)

    before = db.execute(_sql(
        "SELECT COUNT(*) FROM glens_chat_sessions WHERE workspace_id = :ws"
    ), {"ws": ws_uuid}).scalar()

    body = RunCreate(triggered_by="manual", dry_run=False,
                     create_lens_session=True,
                     initial_state={"__manual": True})

    original_commit = db.commit
    call_count = {"n": 0}

    def _fail_first_commit():
        call_count["n"] += 1
        if call_count["n"] == 1:
            db.rollback()
            raise RuntimeError("simulated commit failure")
        return original_commit()

    with _patch.object(db, "commit", side_effect=_fail_first_commit):
        try:
            create_run(
                workflow_id=uuid.UUID(wf_id),
                body=body,
                db=db,
                workspace_id=ws_id,
                _="dummy-permission-token",
                caller_id="user_test",
            )
        except Exception:
            pass

    # Rollback wiped the staged session row.
    after = db.execute(_sql(
        "SELECT COUNT(*) FROM glens_chat_sessions WHERE workspace_id = :ws"
    ), {"ws": ws_uuid}).scalar()
    assert after == before, "session must roll back with the run when the commit fails"
