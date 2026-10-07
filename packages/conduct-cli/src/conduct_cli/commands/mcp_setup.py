"""`conduct mcp install` and MCP client config writers."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from conduct_cli import deployment
from conduct_cli.commands.shared import GRAY, GREEN, RED, RESET, YELLOW, _load_config


# ── Commands ──────────────────────────────────────────────────────────────────

# #1219 Phase 3 M3 (Option A): stdio bridge is Cloudflare's `mcp-remote`.
# `npx -y mcp-remote <url> --header "Authorization: Bearer <token>"` is what
# Claude.ai / Claude Code / Cursor / Codex / VS Code Copilot all speak — one
# bridge, one endpoint. Native Python bridge tracked in #1229.
def _mcp_remote_args(api_url: str, token: str) -> list:
    """Args list for the mcp-remote invocation. Kept as a helper so JSON and
    TOML writers stay in sync."""
    cfg = _load_config()
    if deployment.api_url(cfg) != api_url.rstrip("/"):
        cfg = {"api_url": api_url}
    return ["-y", "mcp-remote", deployment.resolve(cfg).mcp,
            "--header", f"Authorization: Bearer {token}"]


def _write_mcp_config(
    path: Path,
    *,
    api_url: str,
    token: str,
    keys: tuple = ("mcpServers",),
    create: bool = False,
) -> bool:
    """Update managed MCP credentials without replacing user-owned entries."""
    from conduct_cli.tool_config import edit_document
    from conduct_cli.guard_commands.tool_lifecycle import managed_mcp, owned_mcp
    if not create and not path.parent.exists():
        return False
    try:
        args = _mcp_remote_args(api_url, token)
        entry = {"command": "npx", "args": args}
        with edit_document(path) as document:
            node = document
            for key in keys:
                node = node.setdefault(key, {})
                if not isinstance(node, dict):
                    raise ValueError("Invalid MCP configuration")
            prior = node.get("conduct")
            if prior is not None and prior != entry and not managed_mcp(prior):
                return False
            retired = node.get("conductguard")
            if retired is not None and owned_mcp(retired, args[2]):
                del node["conductguard"]
            node["conduct"] = entry
        return True
    except (OSError, ValueError, TimeoutError):
        return False


def _write_codex_mcp_config(api_url: str, token: str) -> bool:
    """Use the structured editor for Codex credential refreshes too."""
    from conduct_cli.tool_adapters import ADAPTERS
    path = ADAPTERS["codex"].root() / "config.toml"
    return _write_mcp_config(path, api_url=api_url, token=token, keys=("mcp_servers",))


def _detect_ai_tools() -> list:
    """Use the same configuration evidence as guard discovery."""
    from conduct_cli.guard_commands.discovery import _detect_ai_tools as detect
    return detect()


def _report_tool_coverage() -> None:
    """Detect AI tools on this machine and POST coverage to Guard API. Silent on failure."""
    try:
        cfg = _load_config()
        server  = (cfg.get("server") or cfg.get("api_url") or "").rstrip("/")
        api_key = cfg.get("agent_token", "")
        token   = cfg.get("token", "")
        email   = cfg.get("email", "")


        if not server or not email:
            return

        tools = _detect_ai_tools()
        if not tools:
            return

        payload = json.dumps({"email": email, "tools": tools}).encode()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"{server}/guard/developer-tools",
            data=payload,
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass  # Never surface errors — this is background telemetry


def cmd_mcp_install(args):
    """Register the Conduct MCP server in Claude Code, Codex, Cursor, Windsurf,
    and VS Code. Uses `npx -y mcp-remote` as the stdio bridge (#1219 Phase 3
    M3 Option A) — one server, one endpoint, no local binaries. Native
    Python bridge tracked in #1229 for enterprise SBOM ask.
    """
    import shutil
    import subprocess

    cfg = _load_config()
    api_url = deployment.api_url(cfg)
    token = cfg.get("agent_token") or ""
    if not token:
        print(f"{RED}No Conduct token found — run `conduct login` first, then re-run `conduct mcp install`.{RESET}")
        return
    if not shutil.which("npx"):
        print(f"{YELLOW}⚠ `npx` not on PATH.{RESET}")
        print(f"{GRAY}  MCP stdio bridge (mcp-remote) needs Node.js. Install Node 18+ then re-run.{RESET}")
        print(f"{GRAY}  Or track #1229 for a native Python bridge (no Node dep).{RESET}")
        return

    home = Path.home()
    # claude mcp add --global writes to project-level settings; write directly instead.
    _MCP_TARGETS = [
        ("Claude Code",      home / ".claude" / "settings.json",                             ("mcpServers",),    True),
        ("Cursor",           home / ".cursor" / "mcp.json",                                  ("mcpServers",),    False),
        ("Windsurf",         home / ".codeium" / "windsurf" / "mcp_config.json",             ("mcpServers",),    False),
        ("VS Code (Copilot)",next((p for p in [
            home / ".vscode" / "settings.json",
            home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
            home / ".config" / "Code" / "User" / "settings.json",
        ] if p.exists()), None),                                                              ("mcp", "servers"), False),
    ]

    registered = []
    for label, path, keys, create in _MCP_TARGETS:
        if path and _write_mcp_config(path, api_url=api_url, token=token, keys=keys, create=create):
            registered.append(label)
    if _write_codex_mcp_config(api_url=api_url, token=token):
        registered.append("Codex")

    if registered:
        print(f"{GREEN}✓ Conduct MCP registered in: {', '.join(registered)}{RESET}")
        print(f"{GRAY}  Bridge: npx -y mcp-remote {deployment.resolve(cfg).mcp}{RESET}")
        print(f"{GRAY}  MCP surface consolidated — the old `conductguard-mcp` binary and{RESET}")
        print(f"{GRAY}  `/guard/mcp` URL are being retired in favor of one `/mcp` endpoint (#1219).{RESET}")
        print(f"{GRAY}  Restart your AI tools to pick up the new server.{RESET}")
    else:
        print(f"{YELLOW}⚠ No supported AI tools detected on this machine.{RESET}")
        print(f"{GRAY}  Supported: Claude Code, Codex, Cursor, Windsurf, VS Code{RESET}")
        print(f"{GRAY}  After installing any of these, re-run: conduct mcp install{RESET}")

    tools = _detect_ai_tools()
    if tools:
        print(f"{GRAY}  Detected tools: {', '.join(t['name'] for t in tools)}{RESET}")
        covered = [t['name'] for t in tools if t['mcp_registered']]
        if covered:
            print(f"{GREEN}  MCP registered: {', '.join(covered)}{RESET}")
        uncovered = [t['name'] for t in tools if not t['mcp_registered']]
        if uncovered:
            print(f"{YELLOW}  Not covered: {', '.join(uncovered)} — run: conduct mcp install{RESET}")

    # Push updated coverage to Guard so the dashboard reflects the new state immediately
    try:
        _report_tool_coverage()
    except Exception:
        pass
