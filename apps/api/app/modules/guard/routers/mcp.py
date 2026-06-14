"""
ConductGuard — Remote MCP server over HTTP.

POST /guard/mcp   — stateless JSON-RPC 2.0 endpoint (MCP HTTP transport)

Claude.ai / Claude for Work users add this URL in their MCP settings:
  https://api.conductai.ai/guard/mcp?workspace_id=<uuid>&token=<member_token>

Claude Desktop users can also point here instead of running a local process.
Auth: workspace_id + token as query params (header auth not supported by all MCP clients).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from sqlalchemy import text as _sql

from app.core.database import SessionLocal
from app.core.auth import get_clerk_user_email
from app.modules.guard.models import GuardAuditEvent, GuardConfig, GuardMemberConfig, GuardPolicy

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
            },
            "required": ["summary"],
        },
    },
]


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

def _match_policy(tool_name: str, tool_input: dict, rules: list) -> dict | None:
    inp_text  = json.dumps(tool_input)
    path_keys = ["file_path", "path", "command"]
    path_text = " ".join(str(tool_input.get(k, "")) for k in path_keys)

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

        return rule
    return None


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_rules(db: Session, ws_uuid: uuid.UUID) -> list[dict]:
    policies = (
        db.query(GuardPolicy)
        .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.enabled.is_(True))
        .order_by(GuardPolicy.created_at)
        .all()
    )
    return [
        {
            "rule_id":           p.rule_id,
            "match_tool":        p.match_tool,
            "match_pattern":     p.match_pattern,
            "match_path_pattern": getattr(p, "match_path_pattern", None),
            "action":            p.action,
            "message":           getattr(p, "message", None),
        }
        for p in policies
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
) -> None:
    event = GuardAuditEvent(
        workspace_id=ws_uuid,
        clerk_user_id=user_email,
        user_email=user_email,
        ai_tool=ai_tool,
        tool_call=tool_name,
        input_summary=json.dumps(tool_input)[:200],
        decision=decision,
        rule_id=rule_id,
        hook_session_id=session_id,
        ts=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()


# ── JSON-RPC response helpers ─────────────────────────────────────────────────

def _ok(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _text(msg_id, text: str) -> dict:
    return _ok(msg_id, {"content": [{"type": "text", "text": text}]})


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.get("")
async def mcp_sse(
    workspace_id: str = Query(...),
    token: str       = Query(...),
):
    """SSE endpoint required by MCP Streamable HTTP transport (GET establishes the stream).
    For stateless policy checks we don't push server-initiated messages, so this just
    holds the connection open with keepalive pings until the client disconnects."""
    import asyncio

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
    workspace_id: str = Query(..., description="Guard workspace UUID"),
    token: str       = Query(..., description="Member token from conduct guard init"),
):
    """Stateless MCP JSON-RPC endpoint for Claude.ai / Claude Desktop / Claude for Work."""
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

    db = SessionLocal()
    try:
        # Validate token against guard_member_config
        member_row = db.execute(
            _sql("SELECT clerk_user_id FROM guard_member_config WHERE workspace_id = :w AND member_token = :t AND active = true LIMIT 1"),
            {"w": str(ws_uuid), "t": token},
        ).fetchone()
        if not member_row:
            return JSONResponse(status_code=401, content=_err(msg_id, -32600, "invalid token"))

        clerk_user_id = member_row.clerk_user_id

        # Resolve email from Clerk API (workspace_users has no email column)
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
                rules = _get_rules(db, ws_uuid)
                rule  = _match_policy(inner_tool, inner_input, rules)

                if rule is None:
                    _record_event(db, ws_uuid, inner_tool, inner_input, "allowed", None, ai_tool, user_email, session_id)
                    return JSONResponse(_text(msg_id, f"ALLOWED — no policy rule matches '{inner_tool}'."))

                action  = rule.get("action", "audit")
                rule_id = rule.get("rule_id", "unknown")
                message = rule.get("message") or f"Policy violation ({rule_id})"

                if action == "block":
                    _record_event(db, ws_uuid, inner_tool, inner_input, "blocked", rule_id, ai_tool, user_email, session_id)
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
                    _record_event(db, ws_uuid, inner_tool, inner_input, "warned", rule_id, ai_tool, user_email, session_id)
                    return JSONResponse(_text(msg_id, f"WARNING — {message}  [rule: {rule_id}]"))

                _record_event(db, ws_uuid, inner_tool, inner_input, "audited", rule_id, ai_tool, user_email, session_id)
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
                mcp_url = f"https://api.conductai.ai/guard/mcp?workspace_id={workspace_id}&token={token}"
                desktop_config = (
                    '{\n'
                    '  "mcpServers": {\n'
                    '    "conductguard": {\n'
                    '      "command": "npx",\n'
                    '      "args": ["-y", "mcp-remote", "' + mcp_url + '"]\n'
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

            elif tool_name == "guard_activity":
                summary  = arguments.get("summary", "")
                category = arguments.get("category", "other")
                _record_event(db, ws_uuid, "guard_activity", {"summary": summary, "category": category}, "allowed", None, ai_tool, user_email, session_id)
                return JSONResponse(_text(msg_id, f"Activity logged — '{summary}'"))

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
