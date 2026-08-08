import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, get_user_id, require_permission
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.modules.agent_identity.adapters import TOKEN_PREFIX
from app.modules.agent_identity.models import AgentIdentity
from app.modules.agent_identity.schemas import (
    AgentIdentityCreate,
    AgentIdentityCreated,
    AgentIdentityOut,
    AgentIdentityPatch,
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}",
    tags=["agent-identities"],
)

_DISPLAY_PREFIX_LEN = len(TOKEN_PREFIX) + 4


def _generate_token() -> tuple[str, str]:
    raw = TOKEN_PREFIX + os.urandom(32).hex()
    return raw, raw[:_DISPLAY_PREFIX_LEN]


def mint_agent_identity(db: Session, workspace_id: str, name: str) -> tuple[AgentIdentity, str]:
    """Internal helper — mint an Agent Identity for a user without auth checks.

    Returns (AgentIdentity row, plaintext token). Caller must commit if needed.
    Used by guard join flow to auto-mint on invite accept.
    """
    plaintext, prefix = _generate_token()
    now = datetime.now(timezone.utc)
    row = AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=name,
        provider="conduct",
        token_prefix=prefix,
        token_encrypted=encrypt({"token": plaintext}),
        environment_id=None,
        created_at=now,
        last_used_at=None,
        expires_at=now + __import__("datetime").timedelta(hours=8),
    )
    db.add(row)
    return row, plaintext


def _write_token_to_env(db: Session, workspace_id: str, environment_id: str, plaintext: str) -> None:
    """Merge CONDUCT_AGENT_TOKEN into the env_vars credential blob for the environment."""
    existing = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "env_vars",
        Integration.environment_id == environment_id,
    ).first()

    if existing:
        current = decrypt(existing.encrypted_credentials) if existing.encrypted_credentials else {}
        current["CONDUCT_AGENT_TOKEN"] = plaintext
        existing.encrypted_credentials = encrypt(current)
    else:
        stmt = (
            pg_insert(Integration)
            .values(
                workspace_id=workspace_id,
                service="agent_identity",
                handle="env_vars",
                auth_method="api_key",
                encrypted_credentials=encrypt({"CONDUCT_AGENT_TOKEN": plaintext}),
                environment_id=environment_id,
            )
            .on_conflict_do_update(
                constraint="uq_integrations_workspace_handle_env",
                set_=dict(encrypted_credentials=encrypt({"CONDUCT_AGENT_TOKEN": plaintext})),
            )
        )
        db.execute(stmt)
    db.commit()


@router.post("/agent-identities", response_model=AgentIdentityCreated, status_code=201)
def create_agent_identity(
    workspace_id: str,
    body: AgentIdentityCreate,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Name cannot be empty")

    plaintext, prefix = _generate_token()
    encrypted = encrypt({"token": plaintext})

    row = AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=body.name.strip(),
        provider="conduct",
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
        token=plaintext,
    )


@router.get("/agent-identities", response_model=list[AgentIdentityOut])
def list_agent_identities(
    workspace_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AgentIdentity)
        .filter(AgentIdentity.workspace_id == workspace_id)
        .order_by(AgentIdentity.created_at.desc())
        .all()
    )
    return [AgentIdentityOut(
        id=r.id, name=r.name, provider=r.provider, token_prefix=r.token_prefix,
        created_at=r.created_at, last_used_at=r.last_used_at, environment_id=r.environment_id,
        source=r.source, source_id=r.source_id,
        platform_of_origin=r.platform_of_origin,
        owner_user_id=r.owner_user_id, agent_role_id=r.agent_role_id,
        lifecycle_state=r.lifecycle_state, last_certified_at=r.last_certified_at,
        certification_cadence_days=r.certification_cadence_days,
        risk_tier=r.risk_tier, deactivated_at=r.deactivated_at,
    ) for r in rows]


@router.delete("/agent-identities/{identity_id}", status_code=204)
def delete_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
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
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    """Update identity metadata: owner, risk_tier, lifecycle_state, certification cadence, platform_of_origin.

    Token/credential fields are immutable via this endpoint. Regenerate uses a
    separate endpoint. Setting lifecycle_state to deactivated is a soft-delete
    and also stamps deactivated_at.
    """
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

    return AgentIdentityOut(
        id=row.id, name=row.name, provider=row.provider, token_prefix=row.token_prefix,
        created_at=row.created_at, last_used_at=row.last_used_at, environment_id=row.environment_id,
        source=row.source, source_id=row.source_id,
        platform_of_origin=row.platform_of_origin,
        owner_user_id=row.owner_user_id, agent_role_id=row.agent_role_id,
        lifecycle_state=row.lifecycle_state, last_certified_at=row.last_certified_at,
        certification_cadence_days=row.certification_cadence_days,
        risk_tier=row.risk_tier, deactivated_at=row.deactivated_at,
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
    )


@router.post("/agent-identities/{identity_id}/regenerate", response_model=AgentIdentityCreated)
def regenerate_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    row = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id,
        AgentIdentity.workspace_id == workspace_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")

    plaintext, prefix = _generate_token()
    row.token_prefix = prefix
    row.token_encrypted = encrypt({"token": plaintext})
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
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    from app.modules.agent_identity.run_token_model import AgentRunToken
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion

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
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    from app.modules.agent_identity.run_token_model import AgentRunToken
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion

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
    _: str = Depends(require_permission("platform.workspace.edit")),
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
    _: str = Depends(require_permission("platform.workspace.edit")),
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
    _: str = Depends(require_permission("platform.workspace.edit")),
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
