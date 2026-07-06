"""
ConductGuard — Remote MCP server over HTTP.

POST /guard/mcp   — stateless JSON-RPC 2.0 endpoint (MCP HTTP transport)

Claude.ai / Claude for Work users add this URL in their MCP settings:
  https://api.conductai.ai/guard/mcp?workspace_id=<uuid>
  Authorization: Bearer <member_token>

Claude Desktop users can also point here instead of running a local process.
Auth: workspace_id in query, member_token in `Authorization: Bearer` header.
Legacy `?token=` query param accepted for Claude.ai web compat — emits a
deprecation warning (issue #800). Slated for removal in issue #810.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from sqlalchemy import text as _sql

from app.core.database import SessionLocal
from app.core.auth import get_clerk_user_email
from app.core.pii import redact_secrets
from app.models.workspace import Workspace
from app.modules.guard.models import DiscoveredAgent, GuardAuditEvent, GuardConfig, GuardMemberConfig
from app.modules.guard.policy_engine import compute_policy

router = APIRouter(prefix="/guard/mcp", tags=["guard-mcp"])

PROTOCOL_VERSION = "2024-11-05"

_TOOLS = [
    {
        "name": "guard_status",
        "description": (
            "Returns current ConductGuard policy status: team name, your email, "
            "number of active rules, and the policy version timestamp."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_check",
        "description": (
            "ALWAYS call this before executing any of the following actions: "
            "running shell commands, reading or writing files, accessing the network, "
            "calling external APIs, modifying code, deleting data, or any action that "
            "affects the filesystem or environment. "
            "This enforces your team's ConductGuard security policy — the response will "
            "be ALLOWED, BLOCKED, or WARNING. "
            "If BLOCKED: stop immediately and tell the user the policy rule that blocked it. "
            "If WARNING: proceed but surface the warning to the user. "
            "If ALLOWED: proceed normally. "
            "Pass tool_name as the action you are about to take (e.g. 'bash', 'read_file', "
            "'write_file', 'curl', 'git', 'npm') and tool_input as the relevant parameters."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name":  {"type": "string", "description": "The action you are about to take (e.g. bash, read_file, write_file, curl, git)"},
                "tool_input": {"type": "object", "description": "Relevant parameters — e.g. {\"command\": \"rm -rf /\"} or {\"file_path\": \"/etc/passwd\"}"},
                "conduct_run_id":   {"type": "string", "description": "Conduct run ID if called from within a workflow run — pass the value from your run context."},
                "conduct_workflow": {"type": "string", "description": "Conduct workflow slug if called from within a workflow run."},
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "guard_sync",
        "description": "Returns current active ruleset (no-op for remote MCP — policy is always live).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_enable",
        "description": (
            "Call this when the user asks to 'enable conductguard', 'load mcp', 'activate guard', "
            "or any similar onboarding request. Confirms ConductGuard is connected, returns the "
            "number of active policy rules, and provides the Project Instruction snippet the user "
            "should paste into their Claude.ai Project settings to make guard_check fire automatically."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_spend",
        "description": (
            "Returns LLM spend through the Conduct Guard Proxy, grouped by provider and model. "
            "Use when the user asks 'how much did I spend on LLMs today?' or 'what's our team's "
            "Claude bill this week?'. Optional 'days' argument (default 1, max 30) widens the "
            "window. Only proxy-routed calls are counted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days (default 1, max 30)"},
            },
            "required": [],
        },
    },
    {
        "name": "guard_local_risks",
        "description": (
            "Returns open local key risk findings — pre-existing real provider API keys "
            "(sk-ant-, sk-, pplx-) detected on developers' machines during conduct guard sync. "
            "Use when the user asks 'do we still have raw API keys on dev laptops?' or for "
            "CISO audit prep. Each finding includes provider, file path, masked fragment, "
            "and which developer it was on."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_activity",
        "description": (
            "ALWAYS call this at the start of every conversation, immediately after the user sends "
            "their first message. Pass a one-line summary of what the user is asking you to do. "
            "This logs session intent to the team's ConductGuard audit trail so admins can see "
            "what work is being done across the team's AI usage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One-line summary of what the user is asking you to do in this conversation.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category: coding, debugging, review, research, writing, devops, security, other",
                },
                "conduct_run_id":   {"type": "string", "description": "Conduct run ID if called from within a workflow run."},
                "conduct_workflow": {"type": "string", "description": "Conduct workflow slug if called from within a workflow run."},
            },
            "required": ["summary"],
        },
    },
    {
        "name": "guard_discover",
        "description": "Show all AI agents discovered in this org and Guard coverage. Returns total agents found, how many are under Guard, coverage %, and a list of shadow agents not yet governed.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_discover_register",
        "description": "Bring a discovered shadow agent under Guard governance by agent ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID from guard_discover results"},
            },
            "required": ["agent_id"],
        },
    },
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
]



# ── Conduct platform helpers ──────────────────────────────────────────────────

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
        {"id": run_id, "wf": workflow_id, "ws": str(ws_uuid),
         "by": user_email, "pl": json.dumps(payload), "ts": datetime.now(timezone.utc)},
    )
    db.commit()
    return {"run_id": run_id, "status": "pending"}


def _get_run_status(db, ws_uuid: uuid.UUID, workflow_id: str, run_id: str) -> dict:
    row = db.execute(
        _sql("SELECT status, outcome, started_at, completed_at FROM runs WHERE id = :r AND workflow_id = :wf AND workspace_id = :ws LIMIT 1"),
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


# ── Surface detection ─────────────────────────────────────────────────────────

def _detect_surface(client_info: dict) -> str:
    name = (client_info.get("name") or "").lower()
    if "desktop" in name:
        return "claude_desktop"
    if "work" in name or "teams" in name or "enterprise" in name:
        return "claude_work"
    if "claude" in name:
        return "claude_chat"
    if "codex" in name:
        return "codex"
    if "cursor" in name:
        return "cursor"
    if "windsurf" in name:
        return "windsurf"
    return "unknown"


# ── Policy matching ───────────────────────────────────────────────────────────

_ACTION_PRIORITY = {"block": 0, "approval": 1, "warn": 2, "audit": 3}


def _match_policy(tool_name: str, tool_input: dict, rules: list) -> dict | None:
    """Return the most restrictive matching rule (block > approval > warn > audit)."""
    inp_text  = json.dumps(tool_input)
    path_keys = ["file_path", "path", "command"]
    path_text = " ".join(str(tool_input.get(k, "")) for k in path_keys)

    best: dict | None = None
    best_priority = 999

    for rule in rules:
        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            allowed = [t.strip() for t in match_tool.split(",")]
            if tool_name.lower() not in allowed:
                continue

        pattern = rule.get("match_pattern")
        if pattern:
            try:
                if not re.search(pattern, inp_text, re.IGNORECASE):
                    continue
            except re.error:
                continue

        path_pattern = rule.get("match_path_pattern")
        if path_pattern:
            try:
                if not re.search(path_pattern, path_text, re.IGNORECASE):
                    continue
            except re.error:
                continue

        priority = _ACTION_PRIORITY.get(rule.get("action", "audit"), 3)
        if priority < best_priority:
            best_priority = priority
            best = rule

    return best


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_rules(db: Session, ws_uuid: uuid.UUID) -> list[dict]:
    """Active ruleset for the agent persona — governs what AI does on the machine."""
    rules = compute_policy(db, ws_uuid, "agent")
    return [
        {
            "rule_id":           r.get("id") or r.get("rule_id"),
            "match_tool":        r.get("match_tool"),
            "match_pattern":     r.get("match_pattern"),
            "match_path_pattern": r.get("match_path_pattern"),
            "action":            r.get("action"),
            "message":           r.get("message"),
        }
        for r in rules
    ]


def _record_event(
    db: Session,
    ws_uuid: uuid.UUID,
    tool_name: str,
    tool_input: dict,
    decision: str,
    rule_id: str | None,
    ai_tool: str,
    user_email: str,
    session_id: str,
    *,
    conductai_run_id: str | None = None,
    conductai_workflow: str | None = None,
) -> None:
    ts = datetime.now(timezone.utc)
    # ponytail: per-workspace SELECT FOR UPDATE — serialises concurrent inserts, upgrade to per-org lock if throughput demands
    last = (
        db.query(GuardAuditEvent.entry_hash)
        .filter(GuardAuditEvent.workspace_id == ws_uuid)
        .order_by(GuardAuditEvent.ts.desc())
        .with_for_update(skip_locked=False)
        .first()
    )
    prev_hash = (last.entry_hash or "") if last else ""
    _tool = tool_name or ""
    entry_hash = hashlib.sha256(f"{ts.isoformat()}|{_tool}|{decision}|{prev_hash}".encode()).hexdigest()

    event = GuardAuditEvent(
        workspace_id=ws_uuid,
        clerk_user_id=user_email,
        user_email=user_email,
        ai_tool=ai_tool,
        tool_call=tool_name,
        input_summary=redact_secrets(json.dumps(tool_input)[:500])[0][:200],
        decision=decision,
        rule_id=rule_id,
        hook_session_id=session_id,
        ts=ts,
        conductai_run_id=conductai_run_id,
        conductai_workflow=conductai_workflow,
        previous_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(event)
    db.commit()

    # Slack notification — one path for all blocks/warns
    if decision in ("blocked", "warned"):
        try:
            from app.modules.guard.routers.events import notify_guard_block
            notify_guard_block(db, ws_uuid, decision=decision, rule_id=rule_id,
                               user_email=user_email, tool=tool_name, source="hook")
        except Exception:
            pass


# ── JSON-RPC response helpers ─────────────────────────────────────────────────

def _ok(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _text(msg_id, text: str) -> dict:
    return _ok(msg_id, {"content": [{"type": "text", "text": text}]})


# ── Main endpoint ─────────────────────────────────────────────────────────────

def _extract_token(request: Request, query_token: str | None) -> str | None:
    """Authorization: Bearer header first, ?token= fallback for legacy MCP clients.

    URL fallback emits a deprecation warning — once Claude.ai web ships header
    support, the query param path is removed (issue #810).
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() or None
    if query_token:
        # Deprecation signal — every URL-token request is logged so we can track
        # when it's safe to drop the fallback.
        from structlog import get_logger
        get_logger(__name__).warning("guard.mcp.token_in_query_deprecated")
        return query_token
    return None


@router.get("")
async def mcp_sse(
    request: Request,
    workspace_id: str | None = Query(None),
    token: str | None = Query(None),
):
    """SSE endpoint required by MCP Streamable HTTP transport (GET establishes the stream).
    For stateless policy checks we don't push server-initiated messages, so this just
    holds the connection open with keepalive pings until the client disconnects.

    Auth: Authorization: Bearer <token> header preferred. ?token= legacy fallback.
    workspace_id is optional — when omitted, the Bearer token identifies the workspace.
    """
    import asyncio

    if not _extract_token(request, token):
        ws_param = f"?workspace_id={workspace_id}" if workspace_id else ""
        return JSONResponse(
            status_code=401,
            content={"error": "missing or invalid token"},
            headers={
                "WWW-Authenticate": (
                    'Bearer realm="https://api.conductai.ai/guard/mcp",'
                    f' resource_metadata="https://api.conductai.ai/.well-known/oauth-protected-resource/guard/mcp{ws_param}"'
                )
            },
        )

    async def event_stream():
        yield ": keepalive\n\n"
        while True:
            await asyncio.sleep(15)
            yield ": keepalive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("")
async def mcp_endpoint(
    request: Request,
    workspace_id: str | None = Query(None, description="Guard workspace UUID — optional when using OAuth Bearer token"),
    token: str | None = Query(None, description="Legacy fallback; prefer Authorization: Bearer header"),
):
    """Stateless MCP JSON-RPC endpoint for Claude.ai / Claude Desktop / Claude for Work."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid JSON"})

    msg_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params") or {}

    # Header-first, query-fallback per issue #800
    resolved_token = _extract_token(request, token)
    if not resolved_token:
        return JSONResponse(status_code=401, content=_err(msg_id, -32600, "missing token (use Authorization: Bearer)"))

    db = SessionLocal()
    try:
        # Validate token — member_token (conduct login) or cond_live_ API key (Settings → API Keys)
        import hashlib as _hashlib
        if resolved_token.startswith("cond_live_"):
            key_hash = _hashlib.sha256(resolved_token.encode()).hexdigest()
            api_key_row = db.execute(
                _sql("SELECT workspace_id, user_id FROM conduct_api_keys WHERE key_hash = :h AND (expires_at IS NULL OR expires_at > now()) LIMIT 1"),
                {"h": key_hash},
            ).fetchone()
            if not api_key_row:
                return JSONResponse(status_code=401, content=_err(msg_id, -32600, "invalid API key"))
            if workspace_id and str(api_key_row.workspace_id) != str(uuid.UUID(workspace_id)):
                return JSONResponse(status_code=401, content=_err(msg_id, -32600, "invalid API key"))
            ws_uuid = api_key_row.workspace_id
            clerk_user_id = api_key_row.user_id or "api_key"
            user_email = get_clerk_user_email(clerk_user_id) if clerk_user_id != "api_key" else f"apikey@{str(ws_uuid)[:8]}"
        else:
            # member_token — look up workspace from token when workspace_id not in URL
            if workspace_id:
                try:
                    ws_uuid = uuid.UUID(workspace_id)
                except ValueError:
                    return JSONResponse(status_code=422, content=_err(msg_id, -32600, "invalid workspace_id"))
                member_row = db.execute(
                    _sql("SELECT clerk_user_id FROM guard_member_config WHERE workspace_id = :w AND member_token = :t AND active = true LIMIT 1"),
                    {"w": str(ws_uuid), "t": resolved_token},
                ).fetchone()
            else:
                member_row = db.execute(
                    _sql("SELECT clerk_user_id, workspace_id FROM guard_member_config WHERE member_token = :t AND active = true LIMIT 1"),
                    {"t": resolved_token},
                ).fetchone()
                if member_row:
                    ws_uuid = member_row.workspace_id
            if not member_row:
                return JSONResponse(status_code=401, content=_err(msg_id, -32600, "invalid token"))
            clerk_user_id = member_row.clerk_user_id
            user_email = get_clerk_user_email(clerk_user_id) or clerk_user_id

        config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
        if not config:
            return JSONResponse(status_code=404, content=_err(msg_id, -32600, "workspace not found"))

        if method == "initialize":
            client_info = params.get("clientInfo") or {}
            surface = _detect_surface(client_info)
            return JSONResponse(_ok(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities":    {"tools": {}},
                "serverInfo":      {"name": "conductguard", "version": "1.0.0"},
                "_surface":        surface,
                "instructions": (
                    "ConductGuard is active and enforcing your team's security policy. "
                    "ALWAYS call guard_activity at the start of every conversation with a one-line summary of what the user is asking you to do. "
                    "ALWAYS call guard_check before executing any of the following: "
                    "shell commands, file reads or writes, network requests, external API calls, "
                    "code modifications, or any action that affects the filesystem or environment. "
                    "If the response is BLOCKED: stop immediately and explain the policy rule to the user. "
                    "If WARNING: proceed but surface the warning to the user. "
                    "If ALLOWED: proceed normally. "
                    "Never skip guard_activity or guard_check — both are required for compliance."
                ),
            }))

        elif method == "notifications/initialized":
            return JSONResponse(status_code=204, content=None)

        elif method == "tools/list":
            return JSONResponse(_ok(msg_id, {"tools": _TOOLS}))

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments") or {}
            # Remote MCP = always a web surface; clientInfo not available on tools/call
            ai_tool = request.headers.get("x-claude-surface") or "claude_chat"
            session_id = request.headers.get("x-session-id", str(uuid.uuid4()))

            # Self-register: every tool call proves this agent is under Guard.
            try:
                _now = datetime.now(timezone.utc)
                db.execute(_sql("""
                    INSERT INTO discovered_agents
                        (id, workspace_id, name, framework, source, location, under_guard, first_seen_at, last_seen_at)
                    VALUES
                        (gen_random_uuid(), :ws, :name, :fw, 'mcp', 'remote-mcp', true, :now, :now)
                    ON CONFLICT (workspace_id, framework, source)
                    DO UPDATE SET under_guard = true, last_seen_at = :now
                """), {"ws": ws_uuid, "name": ai_tool, "fw": ai_tool, "now": _now})
                db.commit()
            except Exception:
                pass  # never block a tool call over a telemetry write


            if tool_name == "guard_status":
                rules = _get_rules(db, ws_uuid)
                result = json.dumps({
                    "workspace_id": workspace_id,
                    "email":        user_email,
                    "rules_active": len(rules),
                }, indent=2)
                return JSONResponse(_text(msg_id, result))

            elif tool_name == "guard_check":
                inner_tool  = arguments.get("tool_name", "")
                inner_input = arguments.get("tool_input") or {}
                _run_id   = arguments.get("conduct_run_id") or None
                _workflow = arguments.get("conduct_workflow") or None
                rules = _get_rules(db, ws_uuid)

                rule  = _match_policy(inner_tool, inner_input, rules)

                if rule is None:
                    _record_event(db, ws_uuid, inner_tool, inner_input, "allowed", None, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow)
                    return JSONResponse(_text(msg_id, f"ALLOWED — no policy rule matches '{inner_tool}'."))

                action  = rule.get("action", "audit")
                rule_id = rule.get("rule_id", "unknown")
                message = rule.get("message") or f"Policy violation ({rule_id})"

                if action == "block":
                    _record_event(db, ws_uuid, inner_tool, inner_input, "blocked", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow)
                    return JSONResponse(_text(msg_id, f"BLOCKED — {message}  [rule: {rule_id}]"))
                if action in ("warn", "approval"):
                    already_warned = db.query(GuardAuditEvent).filter(
                        GuardAuditEvent.workspace_id == ws_uuid,
                        GuardAuditEvent.hook_session_id == session_id,
                        GuardAuditEvent.rule_id == rule_id,
                        GuardAuditEvent.decision == "warned",
                    ).first()
                    if already_warned:
                        return JSONResponse(_text(msg_id, f"ALLOWED — warning already issued this session [rule: {rule_id}]"))
                    _record_event(db, ws_uuid, inner_tool, inner_input, "warned", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow)
                    return JSONResponse(_text(msg_id, f"WARNING — {message}  [rule: {rule_id}]"))

                _record_event(db, ws_uuid, inner_tool, inner_input, "audited", rule_id, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow)
                return JSONResponse(_text(msg_id, f"AUDITED — {message}  [rule: {rule_id}]"))

            elif tool_name == "guard_sync":
                rules = _get_rules(db, ws_uuid)
                return JSONResponse(_text(msg_id, f"Policy is live — {len(rules)} active rule(s). Remote MCP always uses latest."))

            elif tool_name == "guard_enable":
                rules = _get_rules(db, ws_uuid)
                # Record a connection event so Tool Coverage surfaces this user
                _record_event(db, ws_uuid, "guard_enable", {}, "allowed", None, ai_tool, user_email, session_id)
                snippet = (
                    "You have ConductGuard active. "
                    "ALWAYS call guard_activity at the start of every conversation with a one-line summary of what the user is asking. "
                    "ALWAYS call guard_check before running shell commands, reading or writing files, "
                    "calling external APIs, or any action that affects the filesystem or environment. "
                    "If the response is BLOCKED, stop immediately and explain the policy rule to the user. "
                    "If WARNING, proceed but surface the warning."
                )
                mcp_url = f"https://api.conductai.ai/guard/mcp?workspace_id={workspace_id}"
                desktop_config = (
                    '{\n'
                    '  "mcpServers": {\n'
                    '    "conductguard": {\n'
                    '      "command": "npx",\n'
                    '      "args": ["-y", "mcp-remote", "' + mcp_url + '",\n'
                    '               "--header", "Authorization: Bearer ' + resolved_token + '"]\n'
                    '    }\n'
                    '  }\n'
                    '}'
                )
                result = (
                    f"✓ ConductGuard is connected — {len(rules)} active rule(s).\n\n"
                    f"**Claude.ai Projects** — paste this into Project Instructions "
                    f"(Projects → your project → Instructions):\n\n"
                    f"---\n{snippet}\n---\n\n"
                    f"**Claude Desktop** — add this to ~/Library/Application Support/Claude/claude_desktop_config.json "
                    f"(Mac) or %APPDATA%\\Claude\\claude_desktop_config.json (Windows), then restart Claude Desktop:\n\n"
                    f"```json\n{desktop_config}\n```\n\n"
                    f"Until then, Guard is active for this conversation only."
                )
                return JSONResponse(_text(msg_id, result))

            elif tool_name == "guard_spend":
                from sqlalchemy import text as _text_sql
                days = max(1, min(int(arguments.get("days", 1)), 30))
                rows = db.execute(
                    _text_sql("""
                        SELECT provider, model,
                               COUNT(*)            AS calls,
                               SUM(tokens_before)  AS in_tokens,
                               SUM(tokens_after)   AS out_tokens,
                               SUM(cost_usd_after) AS usd
                        FROM guard_audit_events
                        WHERE workspace_id = :ws AND source = 'proxy'
                          AND ts > now() - (:days || ' days')::interval
                        GROUP BY provider, model
                        ORDER BY usd DESC NULLS LAST
                        LIMIT 20
                    """),
                    {"ws": ws_uuid, "days": days},
                ).fetchall()
                if not rows:
                    msg = f"No proxy traffic in the last {days} day(s)."
                else:
                    total = sum(float(r[5] or 0) for r in rows)
                    lines = [f"Proxy spend - last {days} day(s):  ${total:.4f} total", ""]
                    for prov, model, calls, in_t, out_t, usd in rows:
                        lines.append(
                            f"  {prov}/{model or '?'}: {calls} calls, "
                            f"in {int(in_t or 0):,} / out {int(out_t or 0):,}, "
                            f"${(usd or 0):.4f}"
                        )
                    msg = "\n".join(lines)
                return JSONResponse(_text(msg_id, msg))

            elif tool_name == "guard_local_risks":
                from sqlalchemy import text as _text_sql
                rows = db.execute(
                    _text_sql("""
                        SELECT provider, ai_tool, input_summary AS path,
                               user_email, ts
                        FROM guard_audit_events
                        WHERE workspace_id = :ws AND source = 'local_audit'
                        ORDER BY ts DESC LIMIT 50
                    """),
                    {"ws": ws_uuid},
                ).fetchall()
                if not rows:
                    msg = "No local key risks flagged. All devs are clean."
                else:
                    lines = [f"Open local key risks ({len(rows)}):", ""]
                    for prov, ai_tool, path, email, ts in rows:
                        who = email or "unknown dev"
                        lines.append(f"  [{prov}] {path} ({ai_tool}) - {who}")
                    msg = "\n".join(lines)
                return JSONResponse(_text(msg_id, msg))

            elif tool_name == "guard_activity":
                summary  = arguments.get("summary", "")
                category = arguments.get("category", "other")
                _run_id   = arguments.get("conduct_run_id") or None
                _workflow = arguments.get("conduct_workflow") or None
                _record_event(db, ws_uuid, "guard_activity", {"summary": summary, "category": category}, "allowed", None, ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow)
                return JSONResponse(_text(msg_id, f"Activity logged — '{summary}'"))

            elif tool_name == "guard_discover":
                from app.modules.guard.models import DiscoveredAgent
                _ws = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
                if _ws and _ws.org_id:
                    _org_ws = db.query(Workspace.id).filter(Workspace.org_id == _ws.org_id)
                elif _ws and _ws.owner_id:
                    _org_ws = db.query(Workspace.id).filter(Workspace.owner_id == _ws.owner_id)
                else:
                    _org_ws = db.query(Workspace.id).filter(Workspace.id == ws_uuid)
                total   = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id.in_(_org_ws)).count()
                covered = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id.in_(_org_ws), DiscoveredAgent.under_guard == True).count()
                missing = total - covered
                pct     = round(covered / total * 100) if total else 0
                shadow  = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id.in_(_org_ws), DiscoveredAgent.under_guard == False).limit(20).all()
                shadow_list = [{"id": str(a.id), "name": a.name, "framework": a.framework, "source": a.source, "location": a.location} for a in shadow]
                result = {"total": total, "under_guard": covered, "missing": missing, "coverage_pct": pct, "shadow_agents": shadow_list}
                if total == 0:
                    msg = "No discovery scan found. Run `conduct guard discover` from your machine first."
                else:
                    msg = f"Guard coverage: {covered} of {total} agents ({pct}%)\n{missing} shadow agents not under Guard.\n\n" + json.dumps(shadow_list, indent=2)
                return JSONResponse(_text(msg_id, msg))

            elif tool_name == "guard_discover_register":
                import uuid as _uuid
                from app.modules.guard.models import DiscoveredAgent
                from datetime import datetime, timezone
                agent_id = arguments.get("agent_id", "")
                try:
                    row = db.query(DiscoveredAgent).filter(
                        DiscoveredAgent.id == _uuid.UUID(agent_id),
                        DiscoveredAgent.workspace_id == ws_uuid,
                    ).first()
                    if not row:
                        return JSONResponse(_text(msg_id, f"Agent {agent_id} not found."))
                    row.under_guard = True
                    row.last_seen_at = datetime.now(timezone.utc)
                    db.commit()
                    return JSONResponse(_text(msg_id, f"Agent '{row.name or agent_id}' ({row.framework}) is now under Guard."))
                except Exception as e:
                    return JSONResponse(_text(msg_id, f"Error registering agent: {e}"))

            elif tool_name == "conduct_list_agents":
                return JSONResponse(_text(msg_id, json.dumps(_list_agents(db, ws_uuid), indent=2)))

            elif tool_name == "conduct_list_projects":
                return JSONResponse(_text(msg_id, json.dumps(_list_projects(db, ws_uuid), indent=2)))

            elif tool_name == "conduct_list_playbooks":
                return JSONResponse(_text(msg_id, json.dumps(_list_playbooks(db, ws_uuid), indent=2)))

            elif tool_name == "conduct_run_workflow":
                wf_id   = arguments.get("workflow_id", "")
                payload = arguments.get("payload") or {}
                if not wf_id:
                    return JSONResponse(_text(msg_id, "Error — workflow_id is required."))
                try:
                    result = _run_workflow(db, ws_uuid, wf_id, payload, user_email)
                    return JSONResponse(_text(msg_id, json.dumps(result, indent=2)))
                except ValueError as e:
                    return JSONResponse(_text(msg_id, f"Error — {e}"))

            elif tool_name == "conduct_get_run":
                wf_id  = arguments.get("workflow_id", "")
                run_id = arguments.get("run_id", "")
                if not wf_id or not run_id:
                    return JSONResponse(_text(msg_id, "Error — workflow_id and run_id are required."))
                try:
                    result = _get_run_status(db, ws_uuid, wf_id, run_id)
                    return JSONResponse(_text(msg_id, json.dumps(result, indent=2)))
                except ValueError as e:
                    return JSONResponse(_text(msg_id, f"Error — {e}"))

            else:
                return JSONResponse(_text(msg_id, f"Unknown tool: {tool_name}"))

        elif method == "ping":
            return JSONResponse(_ok(msg_id, {}))

        else:
            if msg_id is not None:
                return JSONResponse(_err(msg_id, -32601, f"Method not found: {method}"))
            return JSONResponse(status_code=204, content=None)

    finally:
        db.close()


# ---------------------------------------------------------------------------
# OAuth support endpoints
# ---------------------------------------------------------------------------

well_known_router = APIRouter(tags=["guard-mcp"])


@well_known_router.get("/.well-known/oauth-protected-resource/guard/mcp")
async def oauth_protected_resource(workspace_id: str | None = Query(None)):
    """RFC 9728 — tells OAuth clients where the authorization server lives.

    workspace_id is echoed into the resource URI so it flows into the RFC 8707
    resource parameter that MCP clients (Claude.ai) send to the authorize endpoint.
    """
    resource = "https://api.conductai.ai/guard/mcp"
    if workspace_id:
        resource += f"?workspace_id={workspace_id}"
    return JSONResponse({
        "resource": resource,
        "authorization_servers": [os.environ.get("APP_URL", "https://app.conductai.ai")],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["guard:read"],
    })


@router.post("/oauth/member-token")
async def oauth_member_token(request: Request):
    """Exchange a Clerk JWT for a guard member_token (called by the Next.js complete handler).

    Validates the Clerk token, then upserts the user into guard_member_config
    and returns their member_token. Creates one on first call.
    """
    import secrets as _secrets
    from app.core.auth import _verify_clerk_token

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"error": "missing Clerk token"})

    clerk_token = auth_header[7:].strip()
    claims = _verify_clerk_token(clerk_token)
    if not claims:
        return JSONResponse(status_code=401, content={"error": "invalid Clerk token"})

    body = await request.json()
    workspace_id = body.get("workspace_id", "")
    email = body.get("email", "")

    if not email:
        return JSONResponse(status_code=422, content={"error": "email required"})

    clerk_user_id = claims.get("sub", email)

    db = SessionLocal()
    try:
        # If no workspace_id provided (Claude.ai doesn't send resource param),
        # look up the user's most recently joined workspace.
        if not workspace_id:
            row = db.execute(
                _sql("SELECT workspace_id FROM guard_member_config WHERE clerk_user_id = :uid AND active = true ORDER BY joined_at DESC LIMIT 1"),
                {"uid": clerk_user_id},
            ).fetchone()
            if not row:
                return JSONResponse(status_code=404, content={"error": "no guard workspace found for this user — join via invite first"})
            workspace_id = str(row.workspace_id)

        try:
            ws_uuid = uuid.UUID(workspace_id)
        except ValueError:
            return JSONResponse(status_code=422, content={"error": "invalid workspace_id"})

        existing = db.execute(
            _sql("SELECT member_token FROM guard_member_config WHERE workspace_id = :ws AND clerk_user_id = :uid AND active = true LIMIT 1"),
            {"ws": str(ws_uuid), "uid": clerk_user_id},
        ).fetchone()

        if existing:
            member_token = existing.member_token
        else:
            member_token = _secrets.token_hex(32)
            db.execute(
                _sql("""
                    INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
                    VALUES (:ws, :uid, :token, true, :now)
                    ON CONFLICT (workspace_id, clerk_user_id) DO UPDATE SET active = true
                """),
                {"ws": str(ws_uuid), "uid": clerk_user_id, "token": member_token, "now": datetime.now(timezone.utc)},
            )
            db.commit()

        return JSONResponse({"member_token": member_token})
    finally:
        db.close()
