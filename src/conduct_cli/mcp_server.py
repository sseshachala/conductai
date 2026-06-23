#!/usr/bin/env python3
"""
conduct-mcp — Conduct AI MCP server.

Runs as a subprocess started by Claude Code / Cursor / Windsurf via the
mcpServers config written by `conduct mcp install`. Communicates over
stdin/stdout using JSON-RPC 2.0 (MCP stdio transport).

Exposes six tools:
  conduct_list_agents    — list agents in the workspace
  conduct_list_projects  — list projects in the workspace
  conduct_list_playbooks — list available playbook templates
  conduct_run_workflow   — trigger a workflow run
  conduct_get_run        — get run status / result
  conduct_guard_status   — ConductGuard policy status
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONDUCT_CONFIG_PATH = Path.home() / ".conduct" / "config.json"
GUARD_DIR           = Path.home() / ".conductguard"
GUARD_POLICY_PATH   = GUARD_DIR / "policy.json"
GUARD_CONFIG_PATH   = GUARD_DIR / "config.json"

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
                "workflow_id": {
                    "type": "string",
                    "description": "The workflow UUID to run",
                },
                "payload": {
                    "type": "object",
                    "description": "Optional trigger payload (key-value pairs)",
                },
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
        "description": (
            "Show current ConductGuard policy status — active rules, "
            "today's spend, and your team info."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


# ── Config helpers ─────────────────────────────────────────────────────────────

def _load_conduct_config() -> dict:
    if CONDUCT_CONFIG_PATH.exists():
        try:
            return json.loads(CONDUCT_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _load_guard_policy() -> dict:
    if GUARD_POLICY_PATH.exists():
        try:
            return json.loads(GUARD_POLICY_PATH.read_text())
        except Exception:
            pass
    return {"rules": []}


def _load_guard_config() -> dict:
    if GUARD_CONFIG_PATH.exists():
        try:
            return json.loads(GUARD_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _api_get(url: str, token: str | None, api_key: str | None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _api_post(url: str, body: dict, token: str | None, api_key: str | None) -> dict | list:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


# ── Tool handlers ──────────────────────────────────────────────────────────────

def _handle_list_agents(server: str, workspace_id: str, token: str | None, api_key: str | None) -> str:
    try:
        url    = f"{server}/agents?workspace_id={workspace_id}"
        result = _api_get(url, token, api_key)
        agents = [
            {"id": a.get("id"), "name": a.get("name"), "status": a.get("status")}
            for a in (result if isinstance(result, list) else result.get("items", []))
        ]
        return json.dumps(agents, indent=2)
    except urllib.error.HTTPError as e:
        return f"Error — HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"Error — {e}"


def _handle_list_projects(server: str, workspace_id: str, token: str | None, api_key: str | None) -> str:
    try:
        url    = f"{server}/projects?workspace_id={workspace_id}"
        result = _api_get(url, token, api_key)
        return json.dumps(result, indent=2)
    except urllib.error.HTTPError as e:
        return f"Error — HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"Error — {e}"


def _handle_list_playbooks(server: str, workspace_id: str, token: str | None, api_key: str | None) -> str:
    try:
        url    = f"{server}/playbooks?workspace_id={workspace_id}"
        result = _api_get(url, token, api_key)
        return json.dumps(result, indent=2)
    except urllib.error.HTTPError as e:
        return f"Error — HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"Error — {e}"


def _handle_run_workflow(
    arguments: dict,
    server: str,
    workspace_id: str,
    token: str | None,
    api_key: str | None,
) -> str:
    workflow_id = arguments.get("workflow_id", "")
    payload     = arguments.get("payload") or {}
    if not workflow_id:
        return "Error — workflow_id is required."
    try:
        url  = f"{server}/workflows/{workflow_id}/runs"
        body = {"workspace_id": workspace_id, "payload": payload}
        run  = _api_post(url, body, token, api_key)
        return json.dumps({"run_id": run.get("id") or run.get("run_id"), "status": run.get("status")}, indent=2)
    except urllib.error.HTTPError as e:
        return f"Error — HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"Error — {e}"


def _handle_get_run(
    arguments: dict,
    server: str,
    token: str | None,
    api_key: str | None,
) -> str:
    workflow_id = arguments.get("workflow_id", "")
    run_id      = arguments.get("run_id", "")
    if not workflow_id or not run_id:
        return "Error — workflow_id and run_id are both required."
    try:
        url = f"{server}/workflows/{workflow_id}/runs/{run_id}"
        run = _api_get(url, token, api_key)
        return json.dumps(
            {
                "status":       run.get("status"),
                "outcome":      run.get("outcome"),
                "started_at":   run.get("started_at"),
                "completed_at": run.get("completed_at"),
            },
            indent=2,
        )
    except urllib.error.HTTPError as e:
        return f"Error — HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return f"Error — {e}"


def _handle_guard_status(workspace_id: str) -> str:
    cfg    = _load_guard_config()
    policy = _load_guard_policy()
    return json.dumps(
        {
            "workspace_id":   workspace_id,
            "email":          cfg.get("user_email", ""),
            "rules_active":   len(policy.get("rules", [])),
            "policy_version": policy.get("version", ""),
        },
        indent=2,
    )


def _dispatch_tool(
    name: str,
    arguments: dict,
    server: str,
    workspace_id: str,
    token: str | None,
    api_key: str | None,
) -> str:
    if name == "conduct_list_agents":
        return _handle_list_agents(server, workspace_id, token, api_key)
    if name == "conduct_list_projects":
        return _handle_list_projects(server, workspace_id, token, api_key)
    if name == "conduct_list_playbooks":
        return _handle_list_playbooks(server, workspace_id, token, api_key)
    if name == "conduct_run_workflow":
        return _handle_run_workflow(arguments, server, workspace_id, token, api_key)
    if name == "conduct_get_run":
        return _handle_get_run(arguments, server, token, api_key)
    if name == "conduct_guard_status":
        return _handle_guard_status(workspace_id)
    return f"Unknown tool: {name}"


# ── JSON-RPC helpers ───────────────────────────────────────────────────────────

def _send(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def _ok(msg_id, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _err(msg_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


# ── Main loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    cfg          = _load_conduct_config()
    server       = cfg.get("server", "").rstrip("/")
    workspace_id = cfg.get("workspace", "")
    api_key      = cfg.get("api_key")
    token        = cfg.get("token")

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
                "serverInfo":      {"name": "conduct", "version": "1.0.0"},
            })

        elif method == "notifications/initialized":
            pass  # notification — no response

        elif method == "tools/list":
            _ok(msg_id, {"tools": _TOOLS})

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments") or {}
            text      = _dispatch_tool(tool_name, arguments, server, workspace_id, token, api_key)
            _ok(msg_id, {"content": [{"type": "text", "text": text}]})

        elif method == "ping":
            _ok(msg_id, {})

        else:
            if msg_id is not None:
                _err(msg_id, -32601, f"Method not found: {method}")


# ponytail: telemetry error interceptor (#718)
from .log_util import install_error_interceptor as _ei
main = _ei(main)

if __name__ == "__main__":
    main()
