"""Opener chips for the glens chat page — data-driven suggested prompts.

Split out of chat.py in #1459.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.tools.registrations.lens.governance import get_governance_kpis

router = APIRouter(prefix="/glens", tags=["glens"])


class _OpenerCtx:
    """Minimal ctx shim — get_governance_kpis only reads .workspace_id."""
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id


@router.get("/opener")
def glens_opener(
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    try:
        kpis = get_governance_kpis(_OpenerCtx(workspace_id))
    except Exception:
        kpis = {}

    blocked = kpis.get("blocked_today", 0)
    events = kpis.get("events_today", 0)
    blocks_mtd = kpis.get("blocks_mtd", 0)
    devs = kpis.get("active_developers_today", 0)

    chips: list[str] = []
    if blocked > 0:
        chips.append(f"Who was blocked today? ({blocked} block{'s' if blocked != 1 else ''})")
    else:
        chips.append("Show me today's Guard activity")
    if events > 0:
        chips.append(f"Show the most recent events today ({events} total)")
    else:
        chips.append("Show recent Guard events")
    if blocks_mtd > 0:
        chips.append(f"How many blocks this month? ({blocks_mtd} so far)")
    else:
        chips.append("Cost by AI tool this month")
    if devs > 1:
        chips.append(f"Who are the {devs} active developers today?")
    else:
        chips.append("Which rule triggered most this week?")

    return {"chips": chips}
