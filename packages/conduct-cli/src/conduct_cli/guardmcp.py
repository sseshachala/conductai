#!/usr/bin/env python3
"""
conductguard-mcp — ConductGuard MCP server.

Runs as a subprocess started by Claude Code / Codex / Cursor / Windsurf via
the mcpServers config written by `conduct guard sync`. Communicates over
stdin/stdout using JSON-RPC 2.0 (MCP stdio transport).

Exposes three tools:
  guard_status  — current policy + team info
  guard_check   — check whether a tool call would be blocked by policy
  guard_sync    — pull latest policy from the ConductGuard API
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import uuid
import urllib.request
import urllib.error
from pathlib import Path

GUARD_DIR   = Path.home() / ".conductguard"
POLICY_PATH = GUARD_DIR / "policy.json"
CONFIG_PATH = GUARD_DIR / "config.json"

PROTOCOL_VERSION = "2024-11-05"

# Session ID shared across all events in this MCP server process
_SESSION_ID = str(uuid.uuid4())

# Populated during MCP initialize handshake — used to identify the surface
_CLIENT_INFO: dict = {}

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
                "tool_name": {
                    "type": "string",
                    "description": "The action you are about to take (e.g. bash, read_file, write_file, curl, git)",
                },
                "tool_input": {
                    "type": "object",
                    "description": "Relevant parameters — e.g. {\"command\": \"rm -rf /\"} or {\"file_path\": \"/etc/passwd\"}",
                },
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "guard_sync",
        "description": (
            "Fetch the latest policy from the ConductGuard server and save it locally. "
            "Run this after your security team updates policies."
        ),
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
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_policy() -> dict:
    if POLICY_PATH.exists():
        try:
            return json.loads(POLICY_PATH.read_text())
        except Exception:
            pass
    return {"rules": []}


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _detect_surface(client_info: dict) -> str:
    """Map MCP clientInfo.name → ai_tool label sent to Guard API."""
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


def _post_audit_event(
    tool_name: str,
    tool_input: dict,
    decision: str,
    rule_id: str | None,
    workspace_id: str,
    token: str,
    ai_tool: str,
) -> None:
    """Fire-and-forget: post a guard audit event to the Conduct API."""
    if not workspace_id:
        return
    cfg     = _load_config()
    api_url = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    payload = json.dumps({
        "workspace_id":    workspace_id,
        "clerk_user_id":   cfg.get("user_email", ""),
        "user_email":      cfg.get("user_email", ""),
        "ai_tool":         ai_tool,
        "tool_call":       tool_name,
        "input_summary":   json.dumps(tool_input)[:200],
        "decision":        decision,
        "rule_id":         rule_id,
        "hook_session_id": _SESSION_ID,
    }).encode()
    try:
        req = urllib.request.Request(
            f"{api_url}/guard/events",
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # never crash the MCP server over telemetry


def _match_policy(tool_name: str, tool_input: dict) -> dict | None:
    """Return the first matching rule dict, or None if no rule fires."""
    policy    = _load_policy()
    rules     = policy.get("rules", [])
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


# ── Tool handlers ─────────────────────────────────────────────────────────────

def _handle_guard_status(workspace_id: str) -> str:
    cfg    = _load_config()
    policy = _load_policy()
    return json.dumps({
        "workspace_id":   workspace_id,
        "email":          cfg.get("user_email", ""),
        "rules_active":   len(policy.get("rules", [])),
        "policy_version": policy.get("version", ""),
    }, indent=2)


def _handle_guard_check(arguments: dict, workspace_id: str, token: str, ai_tool: str) -> str:
    tool_name  = arguments.get("tool_name", "")
    tool_input = arguments.get("tool_input") or {}

    rule = _match_policy(tool_name, tool_input)
    if rule is None:
        _post_audit_event(tool_name, tool_input, "allowed", None, workspace_id, token, ai_tool)
        return f"ALLOWED — no policy rule matches '{tool_name}'."

    action  = rule.get("action", "audit")
    rule_id = rule.get("rule_id", "unknown")
    message = rule.get("message") or f"Policy violation ({rule_id})"

    if action == "block":
        _post_audit_event(tool_name, tool_input, "blocked", rule_id, workspace_id, token, ai_tool)
        return f"BLOCKED — {message}  [rule: {rule_id}]"
    if action in ("warn", "approval"):
        _post_audit_event(tool_name, tool_input, "warned", rule_id, workspace_id, token, ai_tool)
        return f"WARNING — {message}  [rule: {rule_id}]"

    _post_audit_event(tool_name, tool_input, "audited", rule_id, workspace_id, token, ai_tool)
    return f"AUDITED — {message}  [rule: {rule_id}]"


def _handle_guard_sync(workspace_id: str, token: str) -> str:
    cfg     = _load_config()
    api_url = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    url     = f"{api_url}/guard/policies/sync?workspace_id={workspace_id}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            policy = json.loads(resp.read())
        GUARD_DIR.mkdir(parents=True, exist_ok=True)
        POLICY_PATH.write_text(json.dumps(policy, indent=2))
        rule_count = len(policy.get("rules", []))
        return f"Policy synced — {rule_count} rule(s) active (version: {policy.get('version', 'unknown')})."
    except urllib.error.HTTPError as e:
        return f"Sync failed — HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"Sync failed — {e}"


def _dispatch_tool(name: str, arguments: dict, workspace_id: str, token: str, ai_tool: str) -> str:
    if name == "guard_status":
        return _handle_guard_status(workspace_id)
    if name == "guard_check":
        return _handle_guard_check(arguments, workspace_id, token, ai_tool)
    if name == "guard_sync":
        return _handle_guard_sync(workspace_id, token)
    if name == "guard_enable":
        policy = _load_policy()
        rule_count = len(policy.get("rules", []))
        snippet = (
            "You have ConductGuard active. "
            "ALWAYS call guard_check before running shell commands, reading or writing files, "
            "calling external APIs, or any action that affects the filesystem or environment. "
            "If the response is BLOCKED, stop immediately and explain the policy rule to the user. "
            "If WARNING, proceed but surface the warning."
        )
        return (
            f"✓ ConductGuard is connected — {rule_count} active rule(s).\n\n"
            f"To make Guard fire automatically on every conversation, paste this into your "
            f"Claude.ai Project Instructions (Projects → your project → Instructions):\n\n"
            f"---\n{snippet}\n---\n\n"
            f"Until then, Guard is active for this conversation only."
        )
    return f"Unknown tool: {name}"


# ── JSON-RPC helpers ──────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def _ok(msg_id, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _err(msg_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(prog="conductguard-mcp")
    parser.add_argument("--workspace", default=None, help="Guard workspace ID (falls back to ~/.conductguard/config.json)")
    parser.add_argument("--token",     default=None, help="Member token (falls back to ~/.conductguard/config.json)")
    parser.add_argument("--api-url",   default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    cfg = _load_config()
    workspace_id = args.workspace or cfg.get("workspace_id", "")
    token        = args.token     or cfg.get("member_token", "")
    ai_tool      = "unknown"  # resolved from clientInfo during initialize

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")          # None for notifications
        method = msg.get("method", "")
        params = msg.get("params") or {}

        if method == "initialize":
            client_info = params.get("clientInfo") or {}
            _CLIENT_INFO.update(client_info)
            ai_tool = _detect_surface(client_info)
            _ok(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities":    {"tools": {}},
                "serverInfo":      {"name": "conductguard", "version": "1.0.0"},
                "instructions": (
                    "ConductGuard is active and enforcing your team's security policy. "
                    "ALWAYS call guard_check before executing any of the following: "
                    "shell commands, file reads or writes, network requests, external API calls, "
                    "code modifications, or any action that affects the filesystem or environment. "
                    "If the response is BLOCKED: stop immediately and explain the policy rule to the user. "
                    "If WARNING: proceed but surface the warning to the user. "
                    "If ALLOWED: proceed normally. "
                    "Never skip guard_check to save time — policy enforcement is non-negotiable."
                ),
            })

        elif method == "notifications/initialized":
            pass  # notification — no response

        elif method == "tools/list":
            _ok(msg_id, {"tools": _TOOLS})

        elif method == "tools/call":
            tool_name  = params.get("name", "")
            arguments  = params.get("arguments") or {}
            text       = _dispatch_tool(tool_name, arguments, workspace_id, token, ai_tool)
            _ok(msg_id, {"content": [{"type": "text", "text": text}]})

        elif method == "ping":
            _ok(msg_id, {})

        else:
            if msg_id is not None:
                _err(msg_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
