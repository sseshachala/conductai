"""Block receipt endpoints (#1712 Track 1 quick win 2/3).

Every Guard block response carries `receipt_id` + `receipt_url` so an SDK
error message can jump straight to a Lens receipt page. Two read paths:

- ``GET /guard/blocks/{id}`` — workspace-authenticated. Any member with
  ``guard.activity.view_own`` can read blocks in their own workspace.
- ``GET /guard/blocks/public/{id}/{token}`` — no auth. The receipt row must
  have a ``share_token_hash`` (populated only for trial workspaces) that
  matches sha256(token), and the row's workspace must still be plan='trial'
  at read time (so a converted paid workspace can't leak old trial receipts).

Payload is a redacted subset of the audit row — enough to render the
receipt card + seed a Lens chat about the block, without exposing raw
prompts or PII to arbitrary link recipients.
"""
from __future__ import annotations

import uuid as _uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.guard.receipts import hash_share_token

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/blocks", tags=["guard-blocks"])


def _row_to_receipt(row) -> dict:
    """Redacted receipt payload. Keeps rule + decision + provider context
    but strips the raw prompt — the summary already lives in input_summary
    which is bounded to 200 chars and pre-redacted upstream."""
    return {
        "receipt_id": str(row.id),
        "ts": row.ts.isoformat() if row.ts else None,
        "decision": row.decision,
        "rule_id": row.rule_id,
        "rule_message": row.rule_message,
        "provider": row.provider,
        "model": row.model,
        "ai_tool": row.ai_tool,
        "input_summary": row.input_summary,
        "evaluated_rules": row.evaluated_rules,
        "defense_score": row.defense_score,
        "conductai_run_id": row.conductai_run_id,
        "hook_session_id": row.hook_session_id,
    }


def _fetch_blocked(db: Session, receipt_id: _uuid.UUID):
    return db.execute(
        text("""
            SELECT id, workspace_id, ts, decision, rule_id, rule_message,
                   provider, model, ai_tool, input_summary,
                   evaluated_rules, defense_score,
                   conductai_run_id, hook_session_id,
                   share_token_hash
            FROM guard_audit_events
            WHERE id = :id
              AND decision IN ('blocked', 'budget_exceeded', 'rate_limited')
            LIMIT 1
        """),
        {"id": str(receipt_id)},
    ).fetchone()


@router.get("/{receipt_id}")
def get_receipt(
    receipt_id: _uuid.UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_own")),
):
    """Workspace-scoped receipt read. Cross-workspace requests get 404."""
    row = _fetch_blocked(db, receipt_id)
    if row is None or str(row.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=404, detail="receipt_not_found")
    return _row_to_receipt(row)


@router.get("/public/{receipt_id}/{token}")
def get_receipt_public(
    receipt_id: _uuid.UUID,
    token: str,
    db: Session = Depends(get_db),
):
    """Anonymous receipt read for trial signup users. Hash-check the token
    against the row and re-verify the workspace is still on the trial plan
    — a converted paid workspace must not leak old trial receipts."""
    row = _fetch_blocked(db, receipt_id)
    if row is None or not row.share_token_hash:
        raise HTTPException(status_code=404, detail="receipt_not_found")
    if row.share_token_hash != hash_share_token(token):
        raise HTTPException(status_code=404, detail="receipt_not_found")
    plan = db.execute(
        text("SELECT plan FROM workspaces WHERE id = :ws"),
        {"ws": str(row.workspace_id)},
    ).scalar()
    if plan != "trial":
        raise HTTPException(status_code=404, detail="receipt_not_found")
    return _row_to_receipt(row)
