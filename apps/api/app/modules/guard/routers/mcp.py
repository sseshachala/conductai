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
from app.core.pii import redact_secrets
from app.modules.guard.models import GuardAuditEvent, GuardConfig, GuardMemberConfig
from app.modules.guard.policy_engine import compute_policy
from app.modules.guard.routers.events import _send_guard_slack as _slack_notify

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
    """Active ruleset from skill_packs JSONB via compute_policy(). Persona is
    read from guard_config; defaults to 'standard' if absent."""
    cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    persona = (cfg.persona if cfg else None) or "standard"
    rules = compute_policy(db, ws_uuid, persona)
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
        ts=datetime.now(timezone.utc),
        conductai_run_id=conductai_run_id,
        conductai_workflow=conductai_workflow,
    )
    db.add(event)
    db.commit()

    # Slack notification — one path for all blocks/warns
    if decision in ("blocked", "warned"):
        try:
            cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
            if cfg and cfg.notify_on_block:
                from app.core.auth import get_clerk_user_info
                info = get_clerk_user_info(clerk_user_id)
                display_name = info.get("name") or info.get("email") or user_email or clerk_user_id
                display_email = info.get("email") or user_email or ""
                icon = "🚨" if decision == "blocked" else "⚠️"
                _slack_notify(db, cfg, (
                    f"{icon} *Guard {decision}* — `{rule_id or 'unknown'}`\n"
                    f"• User: {display_name} ({display_email})\n"
                    f"• Tool: `{tool_name}`\n"
                    f"• Session: `{session_id or 'n/a'}`"
                ))
        except Exception:
            pass  # never crash event recording on Slack failure


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
    workspace_id: str = Query(...),
    token: str | None = Query(None),
):
    """SSE endpoint required by MCP Streamable HTTP transport (GET establishes the stream).
    For stateless policy checks we don't push server-initiated messages, so this just
    holds the connection open with keepalive pings until the client disconnects.

    Auth: Authorization: Bearer <token> header preferred. ?token= legacy fallback.
    """
    import asyncio

    if not _extract_token(request, token):
        return JSONResponse(status_code=401, content={"error": "missing or invalid token"})

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

    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return JSONResponse(status_code=422, content=_err(msg_id, -32600, "invalid workspace_id"))

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
            if not api_key_row or str(api_key_row.workspace_id) != str(ws_uuid):
                return JSONResponse(status_code=401, content=_err(msg_id, -32600, "invalid API key"))
            clerk_user_id = api_key_row.user_id or "api_key"
            user_email = get_clerk_user_email(clerk_user_id) if clerk_user_id != "api_key" else f"apikey@{workspace_id[:8]}"
        else:
            member_row = db.execute(
                _sql("SELECT clerk_user_id FROM guard_member_config WHERE workspace_id = :w AND member_token = :t AND active = true LIMIT 1"),
                {"w": str(ws_uuid), "t": resolved_token},
            ).fetchone()
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

                # Secret scan — fires before pattern matching so raw values never reach the log
                _secret_rule = next((r for r in rules if r.get("rule_id") == "secret-redact"), None)
                if _secret_rule:
                    _inp_text = json.dumps(inner_input)
                    _, _found = redact_secrets(_inp_text)
                    if _found:
                        _secret_msg = _secret_rule.get("message") or "Credential detected in tool input."
                        _record_event(db, ws_uuid, inner_tool, inner_input, "blocked", "secret-redact", ai_tool, user_email, session_id, conductai_run_id=_run_id, conductai_workflow=_workflow)
                        return JSONResponse(_text(msg_id, f"BLOCKED — {_secret_msg}  [types: {', '.join(_found)}]"))

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
