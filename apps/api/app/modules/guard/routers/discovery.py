"""
POST /guard/discover/scan          — CLI pushes scan results
GET  /guard/discover/scans         — list scan history
GET  /guard/discover/agents        — list discovered agents (filterable)
POST /guard/discover/agents/{id}/register — bring agent under Guard
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_guard_hook_auth, get_workspace_id
from app.core.database import get_db
from app.models.workspace import Workspace
from app.modules.guard.models import DiscoveredAgent, DiscoveryScan

router = APIRouter(prefix="/guard/discover", tags=["guard"])


def _org_ws_subquery(db: Session, workspace_id: str):
    """Return a subquery of all workspace IDs in the same org.

    Resolution: org_id (when set) → owner_id (same person's workspaces) → single workspace.
    """
    ws_uuid = uuid.UUID(workspace_id)
    ws = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
    if ws and ws.org_id:
        return db.query(Workspace.id).filter(Workspace.org_id == ws.org_id)
    if ws and ws.owner_id:
        return db.query(Workspace.id).filter(Workspace.owner_id == ws.owner_id)
    return db.query(Workspace.id).filter(Workspace.id == ws_uuid)


# ── Schemas ───────────────────────────────────────────────────────────────────

class AgentIn(BaseModel):
    name: Optional[str] = None
    framework: Optional[str] = None
    source: Optional[str] = None      # config | process
    location: Optional[str] = None
    evidence: Optional[dict] = None
    risk_score: Optional[int] = None
    under_guard: bool = False


class ScanIn(BaseModel):
    triggered_by: str = "cli"
    agents: list[AgentIn]


class AgentOut(BaseModel):
    id: str
    name: Optional[str]
    framework: Optional[str]
    source: Optional[str]
    location: Optional[str]
    risk_score: Optional[int]
    under_guard: bool
    first_seen_at: datetime
    last_seen_at: datetime

    class Config:
        from_attributes = True


class ScanOut(BaseModel):
    id: str
    triggered_by: str
    status: str
    agents_found: Optional[int]
    guard_coverage: Optional[int]
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/scan", status_code=201)
def ingest_scan(
    body: ScanIn,
    workspace_id: str = Depends(get_guard_hook_auth),
    db: Session = Depends(get_db),
):
    """CLI pushes discovery scan results. Creates scan record + upserts agents."""
    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)

    under_guard_count = sum(1 for a in body.agents if a.under_guard)

    scan = DiscoveryScan(
        workspace_id=ws_uuid,
        triggered_by=body.triggered_by,
        status="complete",
        agents_found=len(body.agents),
        guard_coverage=under_guard_count,
        started_at=now,
        completed_at=now,
    )
    db.add(scan)
    db.flush()

    for a in body.agents:
        # upsert by workspace + framework + location
        existing = (
            db.query(DiscoveredAgent)
            .filter(
                DiscoveredAgent.workspace_id == ws_uuid,
                DiscoveredAgent.framework == a.framework,
                DiscoveredAgent.location == a.location,
            )
            .first()
        )
        if existing:
            existing.scan_id = scan.id
            existing.under_guard = a.under_guard
            existing.risk_score = a.risk_score
            existing.last_seen_at = now
        else:
            db.add(DiscoveredAgent(
                workspace_id=ws_uuid,
                scan_id=scan.id,
                name=a.name,
                framework=a.framework,
                source=a.source,
                location=a.location,
                evidence=a.evidence,
                risk_score=a.risk_score,
                under_guard=a.under_guard,
            ))

    db.commit()
    return {"scan_id": str(scan.id), "agents_found": len(body.agents), "guard_coverage": under_guard_count}


@router.get("/scans", response_model=list[ScanOut])
def list_scans(
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    limit: int = Query(20, le=100),
):
    org_ws = _org_ws_subquery(db, workspace_id)
    rows = (
        db.query(DiscoveryScan)
        .filter(DiscoveryScan.workspace_id.in_(org_ws))
        .order_by(DiscoveryScan.started_at.desc())
        .limit(limit)
        .all()
    )
    return [ScanOut(
        id=str(r.id), triggered_by=r.triggered_by, status=r.status,
        agents_found=r.agents_found, guard_coverage=r.guard_coverage,
        started_at=r.started_at, completed_at=r.completed_at,
    ) for r in rows]


@router.get("/agents", response_model=list[AgentOut])
def list_agents(
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    under_guard: Optional[bool] = Query(None),
    limit: int = Query(100, le=500),
):
    org_ws = _org_ws_subquery(db, workspace_id)
    q = db.query(DiscoveredAgent).filter(
        DiscoveredAgent.workspace_id.in_(org_ws)
    )
    if under_guard is not None:
        q = q.filter(DiscoveredAgent.under_guard == under_guard)
    rows = q.order_by(DiscoveredAgent.last_seen_at.desc()).limit(limit).all()
    return [AgentOut(
        id=str(r.id), name=r.name, framework=r.framework, source=r.source,
        location=r.location, risk_score=r.risk_score, under_guard=r.under_guard,
        first_seen_at=r.first_seen_at, last_seen_at=r.last_seen_at,
    ) for r in rows]


@router.post("/agents/{agent_id}/register", status_code=200)
def register_agent(
    agent_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """Mark a discovered agent as under Guard governance."""
    row = db.query(DiscoveredAgent).filter(
        DiscoveredAgent.id == uuid.UUID(agent_id),
        DiscoveredAgent.workspace_id == uuid.UUID(workspace_id),
    ).first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Agent not found")
    row.under_guard = True
    row.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": agent_id, "under_guard": True}


@router.get("/summary")
def discovery_summary(
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """Coverage meter: total found, under Guard, coverage %."""
    org_ws = _org_ws_subquery(db, workspace_id)
    total = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id.in_(org_ws)).count()
    covered = db.query(DiscoveredAgent).filter(
        DiscoveredAgent.workspace_id.in_(org_ws),
        DiscoveredAgent.under_guard == True,
    ).count()
    pct = round(covered / total * 100) if total else 0
    return {"total": total, "under_guard": covered, "missing": total - covered, "coverage_pct": pct}
