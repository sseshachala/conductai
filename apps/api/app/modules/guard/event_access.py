"""Resource authorization for an exact Flight Recorder citation."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select, text

from app.core.auth import check_permission
from app.modules.agent_identity.models import AgentIdentity
from app.modules.guard.models import GuardAuditEvent


def restrict_event_query(query, db, workspace_id, user_id, event_id):
    ws = UUID(str(workspace_id))
    if not isinstance(user_id, str) or not db.execute(text(
        "SELECT 1 FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"
    ), {"ws": str(ws), "uid": user_id}).fetchone():
        raise HTTPException(status_code=403, detail="Activity access denied")
    query = query.filter(GuardAuditEvent.workspace_id == ws, GuardAuditEvent.id == event_id)
    try:
        check_permission(user_id=user_id, workspace_id=str(ws), credentials=None,
                         db=db, permission="guard.activity.view_all")
        return query
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
    check_permission(user_id=user_id, workspace_id=str(ws), credentials=None,
                     db=db, permission="guard.activity.view_own")
    owned = select(AgentIdentity.id).where(
        AgentIdentity.workspace_id == ws, AgentIdentity.owner_user_id == user_id,
    )
    return query.filter(or_(GuardAuditEvent.clerk_user_id == user_id,
                            GuardAuditEvent.agent_identity_id.in_(owned)))
