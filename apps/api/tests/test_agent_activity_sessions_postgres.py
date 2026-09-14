"""Activity aggregation against PostgreSQL in the disposable credential-test schema."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.test_credential_sessions_postgres import database, issue, WS
from app.modules.agent_identity.router import list_activity_sessions, list_agent_identities


def test_recorded_sessions_exclude_other_agents_workspaces_and_unattributed_rows(database):
    with Session(database) as db:
        identity, _, _ = issue(db)
        identity_id = identity.id
        db.execute(text("""CREATE TABLE guard_audit_events (
            id uuid PRIMARY KEY, workspace_id uuid, agent_identity_id varchar(36),
            hook_session_id text, ai_tool text, ts timestamptz, decision text)"""))
        foreign_workspace = str(uuid.uuid4())
        entries = [
            (WS, identity_id, "thread-one", "warned"),
            (WS, identity_id, "thread-one", "warned"),
            (WS, identity_id, "thread-two", "blocked"),
            (WS, None, "unattributed", "allowed"),
            (WS, str(uuid.uuid4()), "another-agent", "allowed"),
            (foreign_workspace, identity_id, "foreign-workspace", "allowed"),
            (WS, identity_id, None, "allowed"),
        ]
        for workspace, agent, session, decision in entries:
            db.execute(text("INSERT INTO guard_audit_events VALUES (:id, :ws, :agent, :session, 'codex-desktop', now(), :decision)"),
                       {"id": str(uuid.uuid4()), "ws": workspace, "agent": agent, "session": session, "decision": decision})
        db.flush()
        page = list_activity_sessions(WS, identity_id, limit=1, offset=0, _="test", db=db)
        assert page.has_more
        assert page.sessions[0].session_id == "thread-one"
        assert page.sessions[0].event_count == 2
        assert page.sessions[0].warned_count == 2
        second = list_activity_sessions(WS, identity_id, limit=1, offset=1, _="test", db=db)
        assert not second.has_more
        assert second.sessions[0].session_id == "thread-two"
        assert second.sessions[0].blocked_count == 1
        identities = list_agent_identities(WS, _ws=WS, _="test", db=db)
        assert len(identities) == 1
        assert identities[0].recorded_session_count == 2
        assert identities[0].last_activity_at is not None
        with pytest.raises(HTTPException) as exc:
            list_activity_sessions(foreign_workspace, identity_id, limit=50, offset=0, _="test", db=db)
        assert exc.value.status_code == 404
