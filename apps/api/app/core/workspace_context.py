"""
Sets app.current_workspace as a transaction-local Postgres config var before
each FastAPI request that has a resolved workspace_id. RLS policies on tenant
tables use this setting to enforce row-level isolation.

Usage — call set_workspace_rls(db, workspace_id) at the start of any endpoint
that has a workspace_id. The setting is cleared automatically when the
transaction ends (SET LOCAL semantics).
"""
from __future__ import annotations
import uuid as _uuid
from sqlalchemy.orm import Session
from sqlalchemy import text


def set_workspace_rls(db: Session, workspace_id: str | _uuid.UUID) -> None:
    """Set app.current_workspace for the current transaction.

    Safe with connection pooling — SET LOCAL clears on transaction end.
    No-op if workspace_id is None or empty.
    """
    if not workspace_id:
        return
    ws = str(workspace_id)
    try:
        _uuid.UUID(ws)
    except ValueError:
        return
    db.execute(text("SET LOCAL \"app.current_workspace\" = :ws"), {"ws": ws})
