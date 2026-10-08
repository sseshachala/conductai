import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.core.auth import (
    get_user_id,
    get_user_workspace_role,
    get_workspace_id,
    require_permission,
)
from app.core.crypto import encrypt
from app.core.database import get_db
from app.modules.agent_identity.models import AgentCredentialSession, AgentIdentity
from app.modules.agent_identity.schemas import (
    AgentIdentityCreate,
    AgentIdentityCreated,
    AgentIdentityOut,
    AgentIdentityPatch,
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    CredentialSessionOut,
    CredentialSessionPage,
    ActivitySessionOut,
    ActivitySessionPage,
)
from app.modules.agent_identity.router_helpers import (
    _credential_session_member_active,
    _credential_session_out,
    _generate_token,
    _require_workspace_environment,
    _require_workspace_identity,
    _write_token_to_env,
)

# Re-exported for callers that import these names from this module.
from app.modules.agent_identity.router_helpers import (  # noqa: E402,F401
    mint_agent_identity,
)


def _require_path_workspace(
    workspace_id: str,
    authorized_workspace_id: str = Depends(get_workspace_id),
) -> None:
    """Bind every route's data scope to the scope used by permission checks."""
    if workspace_id != authorized_workspace_id:
        raise HTTPException(status_code=403, detail="Workspace path does not match authorized workspace")


router = APIRouter(
    prefix="/workspaces/{workspace_id}",
    tags=["agent-identities"],
    dependencies=[Depends(_require_path_workspace)],
)


@router.post("/agent-identities", response_model=AgentIdentityCreated, status_code=201)
def create_agent_identity(
    workspace_id: str,
    body: AgentIdentityCreate,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    if body.environment_id:
        _require_workspace_environment(db, workspace_id, body.environment_id)

    plaintext, prefix = _generate_token()
    encrypted = encrypt({"token": plaintext})

    row = AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=body.name.strip(),
        provider="conduct",
        source="conduct_api",
        token_prefix=prefix,
        token_encrypted=encrypted,
        environment_id=body.environment_id,
        created_at=datetime.now(timezone.utc),
        last_used_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if body.environment_id:
        _write_token_to_env(db, workspace_id, body.environment_id, plaintext)

    return AgentIdentityCreated(
        id=row.id, name=row.name, provider=row.provider,
        token_prefix=row.token_prefix, created_at=row.created_at,
        last_used_at=row.last_used_at, environment_id=row.environment_id,
        source=row.source, source_id=row.source_id,
        platform_of_origin=row.platform_of_origin,
        owner_user_id=row.owner_user_id, agent_role_id=row.agent_role_id,
        lifecycle_state=row.lifecycle_state, last_certified_at=row.last_certified_at,
        certification_cadence_days=row.certification_cadence_days,
        risk_tier=row.risk_tier, deactivated_at=row.deactivated_at,
        expires_at=row.expires_at,
        token=plaintext,
    )


@router.get("/agent-identities", response_model=list[AgentIdentityOut])
def list_agent_identities(
    workspace_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AgentIdentity)
        .filter(AgentIdentity.workspace_id == workspace_id)
        .order_by(AgentIdentity.created_at.desc())
        .all()
    )
    from app.modules.guard.models import GuardAuditEvent as Event
    activity = {
        row.agent_identity_id: row
        for row in db.query(
            Event.agent_identity_id,
            func.count(func.distinct(Event.hook_session_id)).label("session_count"),
            func.max(Event.ts).label("last_activity"),
        ).filter(
            Event.workspace_id == uuid.UUID(workspace_id),
            Event.agent_identity_id.isnot(None),
            Event.hook_session_id.isnot(None),
            Event.hook_session_id != "",
        ).group_by(Event.agent_identity_id).all()
    }
    return [AgentIdentityOut(
        id=r.id, name=r.name, provider=r.provider, token_prefix=r.token_prefix,
        created_at=r.created_at, last_used_at=r.last_used_at, environment_id=r.environment_id,
        source=r.source, source_id=r.source_id,
        platform_of_origin=r.platform_of_origin,
        owner_user_id=r.owner_user_id, agent_role_id=r.agent_role_id,
        lifecycle_state=r.lifecycle_state, last_certified_at=r.last_certified_at,
        certification_cadence_days=r.certification_cadence_days,
        risk_tier=r.risk_tier, deactivated_at=r.deactivated_at,
        expires_at=r.expires_at,
        recorded_session_count=activity[r.id].session_count if r.id in activity else 0,
        last_activity_at=activity[r.id].last_activity if r.id in activity else None,
    ) for r in rows]


@router.get("/agent-identities/{identity_id}/activity-sessions", response_model=ActivitySessionPage)
def list_activity_sessions(
    workspace_id: str, identity_id: str,
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    identity = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id, AgentIdentity.workspace_id == workspace_id,
    ).first()
    if identity is None:
        raise HTTPException(404, detail="Agent identity not found")
    from app.modules.guard.models import GuardAuditEvent as Event
    rows = db.query(
        Event.hook_session_id.label("session_id"),
        func.array_agg(func.distinct(Event.ai_tool)).label("tools"),
        func.min(Event.ts).label("first_seen"),
        func.max(Event.ts).label("last_seen"),
        func.count(Event.id).label("event_count"),
        func.sum(case((Event.decision == "warned", 1), else_=0)).label("warned_count"),
        func.sum(case((Event.decision == "blocked", 1), else_=0)).label("blocked_count"),
    ).filter(
        Event.workspace_id == uuid.UUID(workspace_id),
        Event.agent_identity_id == identity_id,
        Event.hook_session_id.isnot(None), Event.hook_session_id != "",
    ).group_by(Event.hook_session_id).order_by(
        func.max(Event.ts).desc(), Event.hook_session_id,
    ).offset(offset).limit(limit + 1).all()
    return ActivitySessionPage(sessions=[ActivitySessionOut(
        session_id=r.session_id, tools=sorted(t for t in r.tools if t),
        first_seen=r.first_seen, last_seen=r.last_seen, event_count=r.event_count,
        warned_count=r.warned_count, blocked_count=r.blocked_count,
    ) for r in rows[:limit]], has_more=len(rows) > limit)


@router.get("/agent-identities/{identity_id}/sessions", response_model=CredentialSessionPage)
def list_credential_sessions(
    workspace_id: str, identity_id: str, request: Request,
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    identity = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id, AgentIdentity.workspace_id == workspace_id,
    ).first()
    if identity is None:
        raise HTTPException(404, detail="Agent identity not found")
    rows = db.query(AgentCredentialSession).filter(
        AgentCredentialSession.agent_identity_id == identity.id,
    ).order_by(AgentCredentialSession.created_at.desc(), AgentCredentialSession.id.desc()).offset(offset).limit(limit + 1).all()
    member_active = _credential_session_member_active(db, identity)
    return CredentialSessionPage(
        sessions=[_credential_session_out(row, identity, request, member_active) for row in rows[:limit]],
        has_more=len(rows) > limit,
    )


@router.post("/agent-identities/{identity_id}/sessions/{session_id}/revoke", response_model=CredentialSessionOut)
def revoke_credential_session(
    workspace_id: str, identity_id: str, session_id: str, request: Request,
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    identity = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id, AgentIdentity.workspace_id == workspace_id,
    ).first()
    if identity is None:
        raise HTTPException(404, detail="Agent identity not found")
    row = db.query(AgentCredentialSession).filter(
        AgentCredentialSession.id == session_id,
        AgentCredentialSession.agent_identity_id == identity.id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(404, detail="Credential session not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        # PR 6b canary — publish invalidation so the auth cache drops
        # any entries backed by this session's tokens within bus
        # latency instead of waiting for TTL expiry. Fire-and-forget.
        from app.core.auth_events import publish_identity_disabled
        publish_identity_disabled(str(identity.id))
    return _credential_session_out(row, identity, request, _credential_session_member_active(db, identity))


@router.delete("/agent-identities/{identity_id}", status_code=204)
def delete_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    row = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id,
        AgentIdentity.workspace_id == workspace_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")
    db.delete(row)
    db.commit()


@router.patch("/agent-identities/{identity_id}", response_model=AgentIdentityOut)
def patch_agent_identity(
    workspace_id: str,
    identity_id: str,
    body: AgentIdentityPatch,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    role: str = Depends(get_user_workspace_role),
    db: Session = Depends(get_db),
):
    """Update identity metadata: owner, risk_tier, lifecycle_state, certification cadence, platform_of_origin.

    Token/credential fields are immutable via this endpoint. Regenerate uses a
    separate endpoint. Setting lifecycle_state to deactivated is a soft-delete
    and also stamps deactivated_at.

    Field-level auth: developer+ can update owner/cadence/platform/metadata.
    Only admins can change risk_tier or lifecycle_state.
    """
    if (body.risk_tier is not None or body.lifecycle_state is not None) and role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only admins can change risk_tier or lifecycle_state",
        )
    VALID_LIFECYCLE = {"active", "pending_review", "deactivated", "expired"}
    VALID_TIERS = {"tier_1", "tier_2", "tier_3"}

    row = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id,
        AgentIdentity.workspace_id == workspace_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")

    updated = False

    if body.owner_user_id is not None:
        row.owner_user_id = body.owner_user_id.strip() or None
        updated = True

    if body.risk_tier is not None:
        if body.risk_tier not in VALID_TIERS:
            raise HTTPException(status_code=422, detail=f"risk_tier must be one of {sorted(VALID_TIERS)}")
        row.risk_tier = body.risk_tier
        updated = True

    if body.lifecycle_state is not None:
        if body.lifecycle_state not in VALID_LIFECYCLE:
            raise HTTPException(status_code=422, detail=f"lifecycle_state must be one of {sorted(VALID_LIFECYCLE)}")
        row.lifecycle_state = body.lifecycle_state
        if body.lifecycle_state == "deactivated" and not row.deactivated_at:
            row.deactivated_at = datetime.now(timezone.utc)
        if body.lifecycle_state == "active":
            row.deactivated_at = None
        updated = True

    if body.certification_cadence_days is not None:
        if body.certification_cadence_days < 1:
            raise HTTPException(status_code=422, detail="certification_cadence_days must be >= 1")
        row.certification_cadence_days = body.certification_cadence_days
        updated = True

    if body.platform_of_origin is not None:
        row.platform_of_origin = body.platform_of_origin.strip() or "registry"
        updated = True

    if body.metadata is not None:
        row.metadata_json = body.metadata
        updated = True

    if updated:
        db.commit()
        db.refresh(row)
        # PR 6b canary — publish invalidation for the changes.
        from app.core.auth_events import (
            publish_identity_disabled,
            publish_risk_tier_changed,
        )
        if body.lifecycle_state is not None and body.lifecycle_state != "active":
            publish_identity_disabled(str(row.id))
        elif body.lifecycle_state == "active":
            # Re-activating still bumps entries — the previous entries
            # may have been cached during a brief pre-deactivation
            # window; drop them for consistency.
            publish_identity_disabled(str(row.id))
        if body.risk_tier is not None:
            publish_risk_tier_changed(str(row.id))

    return AgentIdentityOut(
        id=row.id, name=row.name, provider=row.provider, token_prefix=row.token_prefix,
        created_at=row.created_at, last_used_at=row.last_used_at, environment_id=row.environment_id,
        source=row.source, source_id=row.source_id,
        platform_of_origin=row.platform_of_origin,
        owner_user_id=row.owner_user_id, agent_role_id=row.agent_role_id,
        lifecycle_state=row.lifecycle_state, last_certified_at=row.last_certified_at,
        certification_cadence_days=row.certification_cadence_days,
        risk_tier=row.risk_tier, deactivated_at=row.deactivated_at,
        expires_at=row.expires_at,
    )


@router.post("/agent-identities/{identity_id}/certify", response_model=AgentIdentityOut)
def certify_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    """Owner attestation. Records the current time as last_certified_at and
    transitions the identity back to active if it was in pending_review.
    """
    row = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id,
        AgentIdentity.workspace_id == workspace_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")

    row.last_certified_at = datetime.now(timezone.utc)
    if row.lifecycle_state == "pending_review":
        row.lifecycle_state = "active"
    db.commit()
    db.refresh(row)

    return AgentIdentityOut(
        id=row.id, name=row.name, provider=row.provider, token_prefix=row.token_prefix,
        created_at=row.created_at, last_used_at=row.last_used_at, environment_id=row.environment_id,
        source=row.source, source_id=row.source_id,
        platform_of_origin=row.platform_of_origin,
        owner_user_id=row.owner_user_id, agent_role_id=row.agent_role_id,
        lifecycle_state=row.lifecycle_state, last_certified_at=row.last_certified_at,
        certification_cadence_days=row.certification_cadence_days,
        risk_tier=row.risk_tier, deactivated_at=row.deactivated_at,
        expires_at=row.expires_at,
    )


@router.post("/agent-identities/{identity_id}/regenerate", response_model=AgentIdentityCreated)
def regenerate_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    row = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id,
        AgentIdentity.workspace_id == workspace_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")
    if row.environment_id:
        _require_workspace_environment(db, workspace_id, str(row.environment_id))

    plaintext, prefix = _generate_token()
    row.token_prefix = prefix
    row.token_encrypted = encrypt({"token": plaintext})
    # An explicit administrator rotation revokes every login for this identity.
    from app.modules.agent_identity.models import AgentCredentialSession
    db.query(AgentCredentialSession).filter(
        AgentCredentialSession.agent_identity_id == row.id,
        AgentCredentialSession.revoked_at.is_(None),
    ).update({AgentCredentialSession.revoked_at: datetime.now(timezone.utc)})
    row.refresh_token_hash = None
    row.refresh_token_expires_at = None
    db.commit()
    db.refresh(row)

    if row.environment_id:
        _write_token_to_env(db, workspace_id, row.environment_id, plaintext)

    return AgentIdentityCreated(
        id=row.id, name=row.name, provider=row.provider,
        token_prefix=row.token_prefix, created_at=row.created_at,
        last_used_at=row.last_used_at, environment_id=row.environment_id,
        token=plaintext,
    )


@router.get("/agent-identities/{identity_id}/run-tokens")
def list_run_tokens(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.modules.agent_identity.run_token_model import AgentRunToken

    _require_workspace_identity(db, workspace_id, identity_id)

    rows = (
        db.query(AgentRunToken)
        .filter(
            AgentRunToken.agent_identity_id == identity_id,
            AgentRunToken.workspace_id == uuid.UUID(workspace_id),
        )
        .order_by(AgentRunToken.created_at.desc())
        .limit(50)
        .all()
    )

    result = []
    for r in rows:
        workflow_name = None
        workflow_id = None
        run = db.query(Run).filter(Run.id == r.run_id).first()
        if run:
            try:
                wv = db.query(WorkflowVersion).filter(WorkflowVersion.id == run.workflow_version_id).first()
                if wv:
                    wf = db.query(Workflow).filter(Workflow.id == wv.workflow_id).first()
                    if wf:
                        workflow_name = wf.name
                        workflow_id = str(wf.id)
            except Exception:
                pass
        result.append({
            "id": r.id,
            "run_id": r.run_id,
            "token_prefix": r.token_prefix,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "first_used_at": r.first_used_at.isoformat() if r.first_used_at else None,
            "invalidated_at": r.invalidated_at.isoformat() if r.invalidated_at else None,
        })
    return result


@router.get("/agent-run-tokens")
def list_workspace_run_tokens(
    workspace_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.modules.agent_identity.run_token_model import AgentRunToken

    rows = (
        db.query(AgentRunToken)
        .filter(AgentRunToken.workspace_id == uuid.UUID(workspace_id))
        .order_by(AgentRunToken.created_at.desc())
        .limit(100)
        .all()
    )

    result = []
    for r in rows:
        workflow_name = None
        workflow_id = None
        run = db.query(Run).filter(Run.id == r.run_id).first()
        if run:
            try:
                wv = db.query(WorkflowVersion).filter(WorkflowVersion.id == run.workflow_version_id).first()
                if wv:
                    wf = db.query(Workflow).filter(Workflow.id == wv.workflow_id).first()
                    if wf:
                        workflow_name = wf.name
                        workflow_id = str(wf.id)
            except Exception:
                pass
        result.append({
            "id": r.id,
            "run_id": r.run_id,
            "token_prefix": r.token_prefix,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "first_used_at": r.first_used_at.isoformat() if r.first_used_at else None,
            "invalidated_at": r.invalidated_at.isoformat() if r.invalidated_at else None,
        })
    return result


# ─── Long-lived API tokens (cond_api_*) ─────────────────────────────────────

API_TOKEN_PREFIX = "cond_api_"
_API_TOKEN_PREFIX_LEN = len(API_TOKEN_PREFIX) + 4


@router.post("/api-tokens", response_model=None)
def create_api_token(
    workspace_id: str,
    body: "ApiTokenCreate",
    _ws: str = Depends(get_workspace_id),
    creator_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    """Create a long-lived machine token (cond_api_*). Returned once — store it securely."""
    import secrets
    plaintext = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    prefix = plaintext[:_API_TOKEN_PREFIX_LEN]
    now = datetime.now(timezone.utc)
    expires_at = None
    if body.expires_in_days is not None:
        from datetime import timedelta
        expires_at = now + timedelta(days=body.expires_in_days)

    row = AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=body.name,
        provider="conduct",
        token_prefix=prefix,
        token_encrypted=encrypt({"token": plaintext}),
        token_type="api",
        token_name=body.name,
        created_by_clerk_user_id=creator_id,
        environment_id=None,
        created_at=now,
        last_used_at=None,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return ApiTokenCreated(
        id=row.id,
        token_name=row.token_name,
        token_prefix=row.token_prefix,
        token_type=row.token_type,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        token=plaintext,
    )


@router.get("/api-tokens", response_model=None)
def list_api_tokens(
    workspace_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    """List all long-lived API tokens for the workspace. Token values are never returned."""
    rows = (
        db.query(AgentIdentity)
        .filter(
            AgentIdentity.workspace_id == workspace_id,
            AgentIdentity.token_type == "api",
        )
        .order_by(AgentIdentity.created_at.desc())
        .all()
    )
    return [
        ApiTokenOut(
            id=row.id,
            token_name=row.token_name,
            token_prefix=row.token_prefix,
            token_type=row.token_type,
            expires_at=row.expires_at,
            last_used_at=row.last_used_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete("/api-tokens/{token_id}", status_code=204)
def delete_api_token(
    workspace_id: str,
    token_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
    db: Session = Depends(get_db),
):
    """Delete a long-lived API token. Immediately revokes access."""
    row = (
        db.query(AgentIdentity)
        .filter(
            AgentIdentity.id == token_id,
            AgentIdentity.workspace_id == workspace_id,
            AgentIdentity.token_type == "api",
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="API token not found")
    db.delete(row)
    db.commit()
