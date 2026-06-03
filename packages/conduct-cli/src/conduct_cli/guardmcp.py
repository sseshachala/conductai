#!/usr/bin/env python3
"""
conductguard-mcp — ConductGuard MCP server.

Runs as a subprocess started by Claude Code / Cursor / Windsurf via the
mcpServers config written by `conduct guard join`. Communicates over
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
import urllib.request
import urllib.error
from pathlib import Path

GUARD_DIR   = Path.home() / ".conductguard"
POLICY_PATH = GUARD_DIR / "policy.json"
CONFIG_PATH = GUARD_DIR / "config.json"

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
            "Check whether a specific tool call would be blocked, warned, or allowed "
            "by your team's ConductGuard policy. Use this before taking an action you "
            "are unsure about."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool to check (e.g. 'bash', 'edit', 'write')",
                },
                "tool_input": {
                    "type": "object",
                    "description": "Input dict that would be passed to the tool",
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


def _handle_guard_check(arguments: dict) -> str:
    tool_name  = arguments.get("tool_name", "")
    tool_input = arguments.get("tool_input") or {}

    rule = _match_policy(tool_name, tool_input)
    if rule is None:
        return f"ALLOWED — no policy rule matches '{tool_name}'."

    action  = rule.get("action", "audit")
    rule_id = rule.get("rule_id", "unknown")
    message = rule.get("message") or f"Policy violation ({rule_id})"

    if action == "block":
        return f"BLOCKED — {message}  [rule: {rule_id}]"
    if action in ("warn", "approval"):
        return f"WARNING — {message}  [rule: {rule_id}]"
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


def _dispatch_tool(name: str, arguments: dict, workspace_id: str, token: str) -> str:
    if name == "guard_status":
        return _handle_guard_status(workspace_id)
    if name == "guard_check":
        return _handle_guard_check(arguments)
    if name == "guard_sync":
        return _handle_guard_sync(workspace_id, token)
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
            _ok(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities":    {"tools": {}},
                "serverInfo":      {"name": "conductguard", "version": "1.0.0"},
            })

        elif method == "notifications/initialized":
            pass  # notification — no response

        elif method == "tools/list":
            _ok(msg_id, {"tools": _TOOLS})

        elif method == "tools/call":
            tool_name  = params.get("name", "")
            arguments  = params.get("arguments") or {}
            text       = _dispatch_tool(tool_name, arguments, workspace_id, token)
            _ok(msg_id, {"content": [{"type": "text", "text": text}]})

        elif method == "ping":
            _ok(msg_id, {})

        else:
            if msg_id is not None:
                _err(msg_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
