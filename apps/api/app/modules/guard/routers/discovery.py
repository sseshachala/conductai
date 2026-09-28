"""Installation inventory. Scans report configuration, never enforcement authority."""
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.core.auth import get_guard_hook_auth, get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import DiscoveredAgent, DiscoveryScan
from app.modules.guard.discovery_inventory import FRAMEWORKS, agent_view, clean_evidence, summarize, workspace_inventory

router = APIRouter(prefix="/guard/discover", tags=["guard"])


class AgentIn(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    framework: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=20)
    installation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    detection: Literal["installed", "running", "possible_integration"] | None = None
    evidence: dict | None = None


class ScanIn(BaseModel):
    schema_version: Literal[1, 2] = 1
    device_id: uuid.UUID | None = None
    triggered_by: Literal["cli", "watch"] = "cli"
    status: Literal["complete", "partial", "failed"] = "complete"
    errors: list[str] = Field(default_factory=list, max_length=20)
    config_only: bool = False
    agents: list[AgentIn] = Field(max_length=1000)

    @model_validator(mode="after")
    def validate_identity(self):
        if self.schema_version == 2:
            if self.device_id is None:
                raise ValueError("Device identity required")
            if any(not a.installation_id or not a.detection or a.framework not in FRAMEWORKS for a in self.agents):
                raise ValueError("Each finding requires a supported framework, installation identity and detection type")
            identities = [a.installation_id for a in self.agents]
            if len(set(identities)) != len(identities):
                raise ValueError("Duplicate installation identity")
        return self


@router.post("/scan", status_code=201)
def ingest_scan(body: ScanIn, workspace_id: str = Depends(get_guard_hook_auth), db: Session = Depends(get_db)):
    ws = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)
    valid_errors = {"config_unreadable", "manifest_unreadable", "process_unreadable", "process_scan_unavailable", "scan_failed"}
    scan = DiscoveryScan(
        workspace_id=ws, triggered_by=body.triggered_by, status=body.status,
        agents_found=len(body.agents) if body.status != "failed" else 0, guard_coverage=None,
        started_at=now, completed_at=now,
        scan_config={"schema_version": body.schema_version, "device_id": str(body.device_id) if body.device_id else None,
                     "config_only": body.config_only, "errors": sorted(set(body.errors) & valid_errors)},
    )
    db.add(scan)
    db.flush()
    ids = []
    if body.status != "failed":
        for agent in body.agents:
            normalized = body.schema_version == 2
            values = dict(
                scan_id=scan.id, name=agent.framework, framework=agent.framework,
                source=None if normalized else (agent.source or "legacy"),
                location=None, risk_score=None, under_guard=False, proxy_routed=False,
                evidence=clean_evidence(agent.evidence) if normalized else None, last_seen_at=now,
            )
            statement = insert(DiscoveredAgent).values(
                id=uuid.uuid4(), workspace_id=ws, first_seen_at=now,
                device_id=body.device_id if normalized else None,
                installation_id=agent.installation_id if normalized else None,
                detection=agent.detection if normalized else None, **values,
            )
            if normalized:
                statement = statement.on_conflict_do_update(
                    constraint="uq_discovered_agents_installation", set_={**values, "detection": agent.detection})
            else:
                statement = statement.on_conflict_do_update(
                    constraint="uq_discovered_agents_workspace_framework_source", set_=values)
            ids.append(db.execute(statement.returning(DiscoveredAgent.id)).scalar_one())
    db.commit()
    rows = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id == ws, DiscoveredAgent.id.in_(ids)).all() if ids else []
    agents = [agent_view(row, now) for row in rows]
    return {"scan_id": str(scan.id), "agents_found": len(agents), "status": body.status,
            "summary": summarize(agents), "agents": agents}


@router.get("/scans")
def list_scans(workspace_id: str = Depends(get_workspace_id), db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100)):
    rows = db.query(DiscoveryScan).filter(DiscoveryScan.workspace_id == uuid.UUID(workspace_id)).order_by(
        DiscoveryScan.started_at.desc()).limit(limit).all()
    return [{"id": str(r.id), "triggered_by": r.triggered_by, "status": r.status,
             "agents_found": r.agents_found, "started_at": r.started_at, "completed_at": r.completed_at,
             "device_id": (r.scan_config or {}).get("device_id"),
             "errors": (r.scan_config or {}).get("errors", [])} for r in rows]


@router.get("/agents")
def list_agents(workspace_id: str = Depends(get_workspace_id), db: Session = Depends(get_db),
                under_guard: bool | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    agents = workspace_inventory(db, workspace_id)
    if under_guard is not None:
        agents = [a for a in agents if a["under_guard"] == under_guard]
    return agents[offset:offset + limit]


@router.post("/agents/{agent_id}/register")
def register_agent(agent_id: uuid.UUID, workspace_id: str = Depends(get_workspace_id), db: Session = Depends(get_db)):
    row = db.query(DiscoveredAgent).filter(DiscoveredAgent.id == agent_id, DiscoveredAgent.workspace_id == uuid.UUID(workspace_id)).first()
    if row is None:
        raise HTTPException(404, "Agent not found")
    raise HTTPException(409, detail={"message": "Registration cannot prove protection. Configure the integration and rescan.",
                                     "remediation": agent_view(row)["remediation"]})


@router.get("/summary")
def discovery_summary(workspace_id: str = Depends(get_workspace_id), db: Session = Depends(get_db)):
    result = summarize(workspace_inventory(db, workspace_id))
    latest = db.query(DiscoveryScan).filter(DiscoveryScan.workspace_id == uuid.UUID(workspace_id), DiscoveryScan.status == "complete").order_by(
        DiscoveryScan.completed_at.desc()).first()
    result["last_successful_scan_at"] = latest.completed_at if latest else None
    return result
