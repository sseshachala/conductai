"""Direct DB tests for the two agent-identity tools on GLens Executor (#1252).

Exercises:
- `_tool_list_agent_identities` — status filter (default active), scoping to workspace
- `_tool_get_agent_identity_count` — status filter + total via 'all'
"""
from __future__ import annotations

from app.tools.registrations.lens.workspace import get_agent_identity_count, list_agent_identities


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
            id=ws_id,
            name="glens-ai-" + tag,
            owner_id="user_test_glens_ai_" + tag,
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
            from app.modules.agent_identity.models import AgentIdentity
            db2.query(AgentIdentity).filter(AgentIdentity.workspace_id == ws_id).delete()
            ws = db2.get(Workspace, ws_id)
            if ws is not None:
                db2.delete(ws)
            db2.commit()


def _seed_identity(db, workspace_id: str, name: str, lifecycle_state: str = "active"):
    from app.modules.agent_identity.models import AgentIdentity
    ai = AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=uuid.UUID(workspace_id),
        name=name,
        provider="conduct",
        token_prefix="cond_agt_" + uuid.uuid4().hex[:8],
        token_encrypted="stub",
        created_at=_now(),
        lifecycle_state=lifecycle_state,
        deactivated_at=_now() if lifecycle_state == "deactivated" else None,
    )
    db.add(ai)
    db.commit()
    return ai.id


@requires_db
def test_list_agent_identities_active_by_default(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _seed_identity(db, ws_id, "alpha")
    _seed_identity(db, ws_id, "beta")
    _seed_identity(db, ws_id, "old-token", lifecycle_state="deactivated")

    rows = list_agent_identities(ex)
    names = {r["name"] for r in rows}
    assert names == {"alpha", "beta"}, names
    assert all(r["lifecycle_state"] == "active" for r in rows)
    assert all(r["token_prefix"].startswith("cond_agt_") for r in rows)


@requires_db
def test_list_agent_identities_status_filter(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _seed_identity(db, ws_id, "live")
    _seed_identity(db, ws_id, "dead", lifecycle_state="deactivated")

    assert {r["name"] for r in list_agent_identities(ex, status="deactivated")} == {"dead"}
    assert {r["name"] for r in list_agent_identities(ex, status="all")} == {"live", "dead"}


@requires_db
def test_get_agent_identity_count(ws_and_executor):
    db, ws_id, ex = ws_and_executor
    _seed_identity(db, ws_id, "a")
    _seed_identity(db, ws_id, "b")
    _seed_identity(db, ws_id, "c", lifecycle_state="deactivated")

    assert get_agent_identity_count(ex)["count"] == 2
    assert get_agent_identity_count(ex, status="deactivated")["count"] == 1
    assert get_agent_identity_count(ex, status="all")["count"] == 3


@requires_db
def test_agent_identities_scoped_to_workspace(ws_and_executor):
    """Rows in a different workspace must NOT leak in."""
    db, ws_id, ex = ws_and_executor
    _seed_identity(db, ws_id, "mine")

    # Foreign workspace identity
    from app.core.database import SessionLocal
    from app.models.workspace import Workspace
    other_ws = uuid.uuid4()
    with SessionLocal() as db2:
        db2.add(Workspace(
            id=other_ws, name="other", owner_id="u_other",
            plan="free", is_approved=True, created_at=_now(), updated_at=_now(),
        ))
        db2.commit()
    try:
        with SessionLocal() as db2:
            _seed_identity(db2, str(other_ws), "not-mine")

        rows = list_agent_identities(ex)
        assert {r["name"] for r in rows} == {"mine"}
    finally:
        from app.modules.agent_identity.models import AgentIdentity
        with SessionLocal() as db2:
            db2.query(AgentIdentity).filter(AgentIdentity.workspace_id == other_ws).delete()
            ws = db2.get(Workspace, other_ws)
            if ws is not None:
                db2.delete(ws)
            db2.commit()
