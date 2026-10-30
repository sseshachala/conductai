"""GET /guard/session-reports/{id}/html scopes the report to the caller's workspace."""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.workspace import Workspace
from app.modules.guard.models import SessionReport
from app.modules.guard.routers import session_reports as sr


def _db_reachable() -> bool:
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1 FROM workspace_users LIMIT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="Postgres not reachable")


@pytest.fixture()
def db():
    s = SessionLocal()
    created: list[uuid.UUID] = []
    s._created = created  # type: ignore[attr-defined]
    try:
        yield s
    finally:
        s.rollback()
        for ws in created:
            s.execute(text("DELETE FROM session_reports WHERE workspace_id = :w"), {"w": ws})
            s.execute(text("DELETE FROM workspace_users WHERE workspace_id = :w"), {"w": ws})
            s.execute(text("DELETE FROM workspaces WHERE id = :w"), {"w": ws})
        s.commit()
        s.close()


def _workspace(db, member: str | None = None) -> uuid.UUID:
    ws_id = uuid.uuid4()
    db.add(Workspace(id=ws_id, name="html-auth-test"))
    db.flush()
    db._created.append(ws_id)
    if member:
        db.execute(
            text("INSERT INTO workspace_users (workspace_id, clerk_user_id, role) VALUES (:w, :u, 'admin')"),
            {"w": ws_id, "u": member},
        )
    return ws_id


def _report(db, ws_id) -> SessionReport:
    r = SessionReport(
        workspace_id=ws_id, developer_email="dev@example.com",
        sessions=1, prompts=1, commits=1, report_md="SECRET-BODY",
    )
    db.add(r)
    db.commit()
    return r


def _get(db, report_id, workspace_id, user="user_member"):
    with patch.object(sr, "_verify_clerk_token", return_value={"sub": user}):
        return asyncio.run(
            sr.get_session_report_html(
                report_id=str(report_id), token="jwt", workspace_id=str(workspace_id),
                credentials=None, db=db,
            )
        )


def test_member_can_fetch_report(db):
    ws = _workspace(db, member="user_member")
    r = _report(db, ws)
    resp = _get(db, r.id, ws)
    assert resp.status_code == 200


def test_non_member_gets_403(db):
    ws = _workspace(db, member="someone_else")
    r = _report(db, ws)
    resp = _get(db, r.id, ws, user="user_outsider")
    assert resp.status_code == 403
    assert b"SECRET-BODY" not in resp.body


def test_report_must_belong_to_resolved_workspace(db):
    own_ws = _workspace(db, member="user_member")
    other_ws = _workspace(db, member="someone_else")
    other_report = _report(db, other_ws)
    resp = _get(db, other_report.id, own_ws)
    assert resp.status_code == 404
    assert b"SECRET-BODY" not in resp.body
