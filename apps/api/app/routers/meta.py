from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.auth import require_permission
from app.core.database import get_db
from app.runtime.block_schemas import BLOCK_SCHEMAS

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/block-schemas")
def get_block_schemas(
    _: str = Depends(require_permission("platform.workflows.view")),
):
    """Return the full block schema registry — drives canvas field rendering and DSL validation."""
    return BLOCK_SCHEMAS


@router.get("/routing-table")
def get_routing_table(
    _: str = Depends(require_permission("platform.workflows.view")),
    db: Session = Depends(get_db),
):
    """Return the model routing policy table keyed by category → preference."""
    rows = db.execute(
        text(
            "SELECT category, preference, provider, model_id, reason "
            "FROM model_routing_policies WHERE enabled = true ORDER BY category, preference"
        )
    ).fetchall()

    table: dict = {}
    for r in rows:
        cat = r.category or ""
        if cat not in table:
            table[cat] = {}
        table[cat][r.preference] = {
            "provider": r.provider,
            "model_id": r.model_id,
            "reason":   r.reason,
        }
    return table
