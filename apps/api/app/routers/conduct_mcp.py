"""
Conduct platform — Remote MCP server over HTTP.

POST /conduct/mcp   — stateless JSON-RPC 2.0 (MCP HTTP transport)
GET  /conduct/mcp   — SSE keepalive (MCP Streamable HTTP)

GitHub Copilot / Cursor / Windsurf users add:
  URL:     https://api.conductai.ai/conduct/mcp?workspace_id=<uuid>
  Header:  Authorization: Bearer <member_token>

Exposes 6 platform tools: list_agents, list_projects, list_playbooks,
run_workflow, get_run, guard_status.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text as _sql

from app.core.database import SessionLocal
from app.core.auth import get_clerk_user_email

router = APIRouter(prefix="/conduct/mcp", tags=["conduct-mcp"])

PROTOCOL_VERSION = "2024-11-05"

_TOOLS = [
    {
        "name": "conduct_list_agents",
        "description": "List all installed agents in your Conduct workspace.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "conduct_list_projects",
        "description": "List all projects in your Conduct workspace.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "conduct_list_playbooks",
        "description": "List available Conduct playbooks (workflow templates).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "conduct_run_workflow",
        "description": "Trigger a workflow run in Conduct. Returns the run ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "The workflow UUID to run"},
                "payload":     {"type": "object", "description": "Optional trigger payload (key-value pairs)"},
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "conduct_get_run",
        "description": "Get the status and result of a workflow run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "run_id":      {"type": "string"},
            },
            "required": ["workflow_id", "run_id"],
        },
    },
    {
        "name": "conduct_guard_status",
        "description": "Return ConductGuard policy status for the workspace — active rules, persona, policy version.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


# ── Auth ──────────────────────────────────────────────────────────────────────

def _extract_token(request: Request, query_token: str | None) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() or None
    return query_token or None


def _ok(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _text(msg_id, text: str) -> dict:
    return _ok(msg_id, {"content": [{"type": "text", "text": text}]})


# ── DB helpers ────────────────────────────────────────────────────────────────

def _resolve_token(db, ws_uuid: uuid.UUID, token: str) -> tuple[str | None, str | None]:
    """Returns (clerk_user_id, user_email). Accepts member_token or cond_live_ API key."""
    import hashlib
    if token.startswith("cond_live_"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        row = db.execute(
            _sql("SELECT workspace_id, user_id FROM conduct_api_keys WHERE key_hash = :h AND (expires_at IS NULL OR expires_at > now()) LIMIT 1"),
            {"h": key_hash},
        ).fetchone()
        if not row or str(row.workspace_id) != str(ws_uuid):
            return None, None
        uid = row.user_id or "api_key"
        email = get_clerk_user_email(uid) if uid != "api_key" else f"apikey@{str(ws_uuid)[:8]}"
        return uid, email
    else:
        row = db.execute(
            _sql("SELECT clerk_user_id FROM guard_member_config WHERE workspace_id = :w AND member_token = :t AND active = true LIMIT 1"),
            {"w": str(ws_uuid), "t": token},
        ).fetchone()
        if not row:
            return None, None
        uid = row.clerk_user_id
        return uid, get_clerk_user_email(uid) or uid


def _list_agents(db, ws_uuid: uuid.UUID) -> list[dict]:
    rows = db.execute(
        _sql("SELECT id, name, status FROM agents WHERE workspace_id = :w ORDER BY name LIMIT 100"),
        {"w": str(ws_uuid)},
    ).fetchall()
    return [{"id": str(r.id), "name": r.name, "status": r.status} for r in rows]


def _list_projects(db, ws_uuid: uuid.UUID) -> list[dict]:
    rows = db.execute(
        _sql("SELECT id, name, description FROM projects WHERE workspace_id = :w ORDER BY name LIMIT 100"),
        {"w": str(ws_uuid)},
    ).fetchall()
    return [{"id": str(r.id), "name": r.name, "description": r.description} for r in rows]


def _list_playbooks(db, ws_uuid: uuid.UUID) -> list[dict]:
    rows = db.execute(
        _sql("SELECT id, name, description FROM playbooks WHERE workspace_id = :w ORDER BY name LIMIT 100"),
        {"w": str(ws_uuid)},
    ).fetchall()
    return [{"id": str(r.id), "name": r.name, "description": r.description} for r in rows]


def _run_workflow(db, ws_uuid: uuid.UUID, workflow_id: str, payload: dict, user_email: str) -> dict:
    row = db.execute(
        _sql("SELECT id FROM workflows WHERE id = :wf AND workspace_id = :ws LIMIT 1"),
        {"wf": workflow_id, "ws": str(ws_uuid)},
    ).fetchone()
    if not row:
        raise ValueError(f"workflow {workflow_id} not found")

    run_id = str(uuid.uuid4())
    db.execute(
        _sql("""
            INSERT INTO runs (id, workflow_id, workspace_id, status, triggered_by, payload, created_at)
            VALUES (:id, :wf, :ws, 'pending', :by, :pl, :ts)
        """),
        {
            "id":  run_id,
            "wf":  workflow_id,
            "ws":  str(ws_uuid),
            "by":  user_email,
            "pl":  json.dumps(payload),
            "ts":  datetime.now(timezone.utc),
        },
    )
    db.commit()
    return {"run_id": run_id, "status": "pending"}


def _get_run(db, ws_uuid: uuid.UUID, workflow_id: str, run_id: str) -> dict:
    row = db.execute(
        _sql("""
            SELECT status, outcome, started_at, completed_at
            FROM runs WHERE id = :r AND workflow_id = :wf AND workspace_id = :ws LIMIT 1
        """),
        {"r": run_id, "wf": workflow_id, "ws": str(ws_uuid)},
    ).fetchone()
    if not row:
        raise ValueError(f"run {run_id} not found")
    return {
        "status":       row.status,
        "outcome":      row.outcome,
        "started_at":   row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _guard_status(db, ws_uuid: uuid.UUID) -> dict:
    from app.modules.guard.models import GuardConfig
    from app.modules.guard.policy_engine import compute_policy
    cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    persona = (cfg.persona if cfg else None) or "standard"
    rules = compute_policy(db, ws_uuid, persona)
    return {"rules_active": len(rules), "persona": persona}


# ── SSE keepalive (GET) ───────────────────────────────────────────────────────

@router.get("")
async def conduct_mcp_sse(
    request: Request,
    workspace_id: str = Query(...),
    token: str | None = Query(None),
):
    if not _extract_token(request, token):
        return JSONResponse(status_code=401, content={"error": "missing token"})

    async def stream():
        yield ": keepalive\n\n"
        while True:
            await asyncio.sleep(15)
            yield ": keepalive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Main JSON-RPC endpoint (POST) ─────────────────────────────────────────────

@router.post("")
async def conduct_mcp_endpoint(
    request: Request,
    workspace_id: str = Query(...),
    token: str | None = Query(None),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid JSON"})

    msg_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params") or {}

    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return JSONResponse(status_code=422, content=_err(msg_id, -32600, "invalid workspace_id"))

    resolved_token = _extract_token(request, token)
    if not resolved_token:
        return JSONResponse(status_code=401, content=_err(msg_id, -32600, "missing token"))

    db = SessionLocal()
    try:
        clerk_user_id, user_email = _resolve_token(db, ws_uuid, resolved_token)
        if not clerk_user_id:
            return JSONResponse(status_code=401, content=_err(msg_id, -32600, "invalid token"))

        if method == "initialize":
            return JSONResponse(_ok(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities":    {"tools": {}},
                "serverInfo":      {"name": "conduct", "version": "1.0.0"},
                "instructions": (
                    "Conduct platform MCP is active. Use conduct_list_agents to see installed agents, "
                    "conduct_run_workflow to trigger a workflow, and conduct_get_run to poll run status."
                ),
            }))

        elif method == "notifications/initialized":
            return JSONResponse(status_code=204, content=None)

        elif method == "tools/list":
            return JSONResponse(_ok(msg_id, {"tools": _TOOLS}))

        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}

            if name == "conduct_list_agents":
                return JSONResponse(_text(msg_id, json.dumps(_list_agents(db, ws_uuid), indent=2)))

            elif name == "conduct_list_projects":
                return JSONResponse(_text(msg_id, json.dumps(_list_projects(db, ws_uuid), indent=2)))

            elif name == "conduct_list_playbooks":
                return JSONResponse(_text(msg_id, json.dumps(_list_playbooks(db, ws_uuid), indent=2)))

            elif name == "conduct_run_workflow":
                wf_id   = args.get("workflow_id", "")
                payload = args.get("payload") or {}
                if not wf_id:
                    return JSONResponse(_text(msg_id, "Error — workflow_id is required."))
                try:
                    result = _run_workflow(db, ws_uuid, wf_id, payload, user_email)
                    return JSONResponse(_text(msg_id, json.dumps(result, indent=2)))
                except ValueError as e:
                    return JSONResponse(_text(msg_id, f"Error — {e}"))

            elif name == "conduct_get_run":
                wf_id  = args.get("workflow_id", "")
                run_id = args.get("run_id", "")
                if not wf_id or not run_id:
                    return JSONResponse(_text(msg_id, "Error — workflow_id and run_id are required."))
                try:
                    result = _get_run(db, ws_uuid, wf_id, run_id)
                    return JSONResponse(_text(msg_id, json.dumps(result, indent=2)))
                except ValueError as e:
                    return JSONResponse(_text(msg_id, f"Error — {e}"))

            elif name == "conduct_guard_status":
                return JSONResponse(_text(msg_id, json.dumps(_guard_status(db, ws_uuid), indent=2)))

            else:
                return JSONResponse(_text(msg_id, f"Unknown tool: {name}"))

        elif method == "ping":
            return JSONResponse(_ok(msg_id, {}))

        else:
            if msg_id is not None:
                return JSONResponse(_err(msg_id, -32601, f"Method not found: {method}"))
            return JSONResponse(status_code=204, content=None)

    finally:
        db.close()
