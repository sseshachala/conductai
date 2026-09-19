"""Shared helpers for the env-vars routers (#2054 Phase 1).

Both ``env_vars.py`` and ``env_vars_reveal.py`` need to refuse a request
whose ``env_id`` doesn't belong to the caller's workspace. Keeping the
check in one place stops one router from tightening (or loosening) it
without the other noticing.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session


def verify_env_ownership(db: Session, env_id: str, workspace_id: str) -> None:
    """Refuse cross-workspace access to an environment.

    404 (not 403) leaks nothing about whether the env exists in another
    workspace.
    """
    from app.models.environment import Environment
    env = db.query(Environment).filter(
        Environment.id == env_id,
        Environment.workspace_id == workspace_id,
    ).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
