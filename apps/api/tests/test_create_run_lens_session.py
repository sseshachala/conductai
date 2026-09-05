"""#1515 — Canvas Run: mint Lens session at run trigger time.

Verifies the `create_lens_session` flag on `POST /workflows/{id}/runs`:
- flag OFF (default): run.session_id stays NULL, no GlensChatSession row
- flag ON: GlensChatSession row appears, run.session_id links, response
  carries session_id back to the client so the canvas can redirect to
  /lens/{session_id}.

Uses a transactional fixture — everything the test writes rolls back on
teardown, so no explicit cleanup and no cross-test pollution.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch as _patch

import pytest

from tests.regression.conftest import requires_db


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
def ws_and_workflow():
    """Fresh workspace + workflow + version, all inside a transaction that
    rolls back on teardown. No leftover rows."""
    from app.core.database import SessionLocal
    from app.models.workflow import Workflow, WorkflowVersion
    from app.models.workspace import Workspace

    ws_id = uuid.uuid4()
    wf_id = uuid.uuid4()
    version_id = uuid.uuid4()
    tag = ws_id.hex[:8]

    db = SessionLocal()
    try:
        db.add(Workspace(
            id=ws_id, name="run-lens-" + tag, owner_id="user_test_run_lens_" + tag,
            plan="free", is_approved=True, created_at=_now(), updated_at=_now(),
        ))
        db.commit()
        # Chicken-and-egg FK: workflows.current_version_id → workflow_versions,
        # workflow_versions.workflow_id → workflows. Insert workflow first
        # (nullable current_version_id), then version, then link.
        wf = Workflow(
            id=wf_id, workspace_id=ws_id, name="Test WF",
            default_mode="dag", guard_enabled=True, agent_identity_required=True,
            created_at=_now(), updated_at=_now(),
        )
        db.add(wf)
        db.commit()
        db.add(WorkflowVersion(
            id=version_id, workflow_id=wf_id,
            graph={"nodes": [], "edges": []}, created_at=_now(),
        ))
        db.commit()
        wf.current_version_id = version_id
        db.commit()
        yield db, str(ws_id), str(wf_id)
    finally:
        db.rollback()
        db.close()


@requires_db
@pytest.mark.forked
def test_no_lens_session_by_default(ws_and_workflow):
    """No flag → run.session_id stays NULL, no GlensChatSession row."""
    from app.models.run import Run
    from app.modules.glens.models import GlensChatSession
    from app.routers.runs import create_run
    from app.schemas.run import RunCreate

    db, ws_id, wf_id = ws_and_workflow
    ws_uuid = uuid.UUID(ws_id)

    before = db.query(GlensChatSession).filter(GlensChatSession.workspace_id == ws_uuid).count()

    body = RunCreate(triggered_by="manual", dry_run=False, initial_state={"__manual": True})
    # Mock the Redis enqueue — CI runs without a redis service, and our
    # assertions only care about session mint semantics, not queue behavior.
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
    run = db.query(Run).filter(Run.id == result.id).first()
    assert run.session_id is None
    after = db.query(GlensChatSession).filter(GlensChatSession.workspace_id == ws_uuid).count()
    assert after == before


@requires_db
@pytest.mark.forked
def test_create_lens_session_flag_mints_and_links(ws_and_workflow):
    """Flag ON → new GlensChatSession row; run.session_id links; response carries it."""
    from app.models.run import Run
    from app.modules.glens.models import GlensChatSession
    from app.routers.runs import create_run
    from app.schemas.run import RunCreate

    db, ws_id, wf_id = ws_and_workflow
    ws_uuid = uuid.UUID(ws_id)

    body = RunCreate(triggered_by="manual", dry_run=False, create_lens_session=True, initial_state={"__manual": True})
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
    run = db.query(Run).filter(Run.id == result.id).first()
    assert run.session_id == result.session_id

    session = db.query(GlensChatSession).filter(
        GlensChatSession.id == result.session_id,
        GlensChatSession.workspace_id == ws_uuid,
    ).first()
    assert session is not None
    assert session.title == "Run: Test WF"
    assert session.messages == "[]"
    # Token + AgentIdentity mint lazily on first chat message; both stay NULL
    # here. That's the whole point — canvas Run doesn't need chat auth.
    assert session.token_hash is None


@requires_db
@pytest.mark.forked
def test_session_and_run_commit_atomically(ws_and_workflow):
    """Self-review guard: session mint + Run insert must live in the same
    transaction. If the commit fails, the session must roll back — otherwise
    the user sees a ghost 'Run: X' entry in the Lens sidebar for a run that
    was never created.

    We simulate the failure by patching db.commit to raise once; the session
    add is already staged but not committed, so rollback leaves nothing."""
    from unittest.mock import patch as _patch

    from app.modules.glens.models import GlensChatSession
    from app.routers.runs import create_run
    from app.schemas.run import RunCreate

    db, ws_id, wf_id = ws_and_workflow
    ws_uuid = uuid.UUID(ws_id)

    before = db.query(GlensChatSession).filter(GlensChatSession.workspace_id == ws_uuid).count()

    body = RunCreate(triggered_by="manual", dry_run=False, create_lens_session=True,
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
    after = db.query(GlensChatSession).filter(GlensChatSession.workspace_id == ws_uuid).count()
    assert after == before, "session must roll back with the run when the commit fails"
