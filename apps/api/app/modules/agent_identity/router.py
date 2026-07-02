import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.modules.agent_identity.adapters import TOKEN_PREFIX
from app.modules.agent_identity.models import AgentIdentity
from app.modules.agent_identity.schemas import (
    AgentIdentityCreate,
    AgentIdentityCreated,
    AgentIdentityOut,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/agent-identities",
    tags=["agent-identities"],
)

_DISPLAY_PREFIX_LEN = len(TOKEN_PREFIX) + 4


def _generate_token() -> tuple[str, str]:
    raw = TOKEN_PREFIX + os.urandom(32).hex()
    return raw, raw[:_DISPLAY_PREFIX_LEN]


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


@router.post("", response_model=AgentIdentityCreated, status_code=201)
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
        token=plaintext,
    )


@router.get("", response_model=list[AgentIdentityOut])
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
    ) for r in rows]


@router.delete("/{identity_id}", status_code=204)
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


@router.post("/{identity_id}/regenerate", response_model=AgentIdentityCreated)
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


@router.get("/{identity_id}/run-tokens")
def list_run_tokens(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    from app.modules.agent_identity.run_token_model import AgentRunToken
    from app.models.run import Run
    from app.models.workflow_version import WorkflowVersion
    from app.models.workflow import Workflow
    import logging as _log
    _logger = _log.getLogger(__name__)

    # Debug: count ALL rows for this workspace and for this identity
    _total = db.query(AgentRunToken).filter(
        AgentRunToken.workspace_id == uuid.UUID(workspace_id)
    ).count()
    _by_identity = db.query(AgentRunToken).filter(
        AgentRunToken.agent_identity_id == identity_id
    ).count()
    _logger.warning(
        "run_tokens.query identity_id=%s workspace_id=%s total_in_ws=%s by_identity=%s",
        identity_id, workspace_id, _total, _by_identity
    )

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
        run = db.query(Run).filter(Run.id == r.run_id).first()
        if run:
            try:
                wv = db.query(WorkflowVersion).filter(WorkflowVersion.id == run.workflow_version_id).first()
                if wv:
                    wf = db.query(Workflow).filter(Workflow.id == wv.workflow_id).first()
                    workflow_name = wf.name if wf else None
            except Exception:
                pass
        result.append({
            "id": r.id,
            "run_id": r.run_id,
            "workflow_name": workflow_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "first_used_at": r.first_used_at.isoformat() if r.first_used_at else None,
            "invalidated_at": r.invalidated_at.isoformat() if r.invalidated_at else None,
        })
    return result
