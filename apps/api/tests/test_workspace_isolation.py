"""Workspace isolation — Group D of epic #1092.

Multi-tenant SaaS: a user with a valid token for workspace A must never
reach data in workspace B.

This is a narrow starter suite exercising the read paths that most obviously
matter. Full (route, role, target_workspace) matrix expansion lives in a
follow-up — this file validates the pattern first.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.core.auth as _auth_mod
from app.core.auth import get_user_id, get_workspace_id
from app.core.database import SessionLocal
from app.main import app
from app.models.workspace import Workspace
from app.models.workspace_user import WorkspaceUser
from app.models.workflow import Workflow


WORKSPACE_A = uuid.UUID("33333333-3333-3333-3333-000000000001")
WORKSPACE_B = uuid.UUID("33333333-3333-3333-3333-000000000002")
USER_A_ADMIN = "user_isolation_admin_A"
USER_B_OWNER = "user_isolation_owner_B"
WORKFLOW_B = uuid.UUID("33333333-3333-3333-3333-000000000010")


def _db_available() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


@pytest.fixture(scope="module")
def two_workspaces():
    """Seed workspace A (with user_A as admin) and workspace B (with a
    workflow that user_A must never touch)."""
    if not _db_available():
        pytest.skip("Postgres not reachable")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for ws_id, name, owner in [
            (WORKSPACE_A, "iso-a", USER_A_ADMIN),
            (WORKSPACE_B, "iso-b", USER_B_OWNER),
        ]:
            if db.get(Workspace, ws_id) is None:
                db.add(Workspace(id=ws_id, name=name, owner_id=owner,
                                 plan="free", is_approved=True, created_at=now, updated_at=now))
        # User A is admin only in WORKSPACE_A.
        if not db.query(WorkspaceUser).filter_by(workspace_id=WORKSPACE_A, clerk_user_id=USER_A_ADMIN).one_or_none():
            db.add(WorkspaceUser(workspace_id=WORKSPACE_A, clerk_user_id=USER_A_ADMIN,
                                 role="admin", joined_at=now))
        # Workflow lives in WORKSPACE_B (user A has no membership there).
        if db.get(Workflow, WORKFLOW_B) is None:
            db.add(Workflow(id=WORKFLOW_B, workspace_id=WORKSPACE_B, name="iso-target",
                            default_mode="dag", guard_enabled=True,
                            created_at=now, updated_at=now))
        db.commit()
    yield
    try:
        with SessionLocal() as db:
            db.execute(text("DELETE FROM workspaces WHERE id IN (:a, :b)"),
                       {"a": str(WORKSPACE_A), "b": str(WORKSPACE_B)})
            db.commit()
    except Exception as exc:
        print(f"[isolation-teardown] non-fatal: {exc!r}")


@pytest.fixture
def user_a_client_targeting_b(two_workspaces, monkeypatch):
    """TestClient acting as user A but claiming workspace B in the header —
    the exact cross-tenant probe the isolation test guards."""
    monkeypatch.setattr(_auth_mod, "_clerk_enabled", lambda: True)
    app.dependency_overrides[get_user_id] = lambda: USER_A_ADMIN
    app.dependency_overrides[get_workspace_id] = lambda: str(WORKSPACE_B)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_user_id, None)
    app.dependency_overrides.pop(get_workspace_id, None)


@requires_db
@pytest.mark.attack
def test_user_a_cannot_list_workspace_b_workflows(user_a_client_targeting_b):
    """User A (member of WORKSPACE_A only) targets WORKSPACE_B → 403."""
    resp = user_a_client_targeting_b.get("/workflows")
    assert resp.status_code == 403, (
        f"cross-tenant list returned {resp.status_code} — expected 403. "
        f"body: {resp.text[:200]}"
    )


@requires_db
@pytest.mark.attack
def test_user_a_cannot_get_workspace_b_workflow(user_a_client_targeting_b):
    """User A tries to fetch a workflow_id that lives in WORKSPACE_B → 403 or 404."""
    resp = user_a_client_targeting_b.get(f"/workflows/{WORKFLOW_B}")
    assert resp.status_code in (403, 404), (
        f"cross-tenant fetch returned {resp.status_code} — expected 403/404. "
        f"body: {resp.text[:200]}"
    )
