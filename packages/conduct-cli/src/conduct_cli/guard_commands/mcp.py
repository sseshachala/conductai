"""Guard CLI: mcp."""
from __future__ import annotations

from pathlib import Path
import json

from . import instructions as _guard_instructions
from . import shared as _guard_shared


def _vscode_mcp_paths() -> list[tuple[Path, str]]:
    """VS Code Copilot MCP config locations (macOS + Linux). Only if Copilot is installed."""
    ext_dir = Path.home() / ".vscode" / "extensions"
    if not ext_dir.exists() or not any(p.name.startswith("github.copilot") for p in ext_dir.iterdir() if p.is_dir()):
        return []
    candidates = [
        Path.home() / "Library" / "Application Support" / "Code" / "User" / "mcp.json",
        Path.home() / ".config" / "Code" / "User" / "mcp.json",
    ]
    return [(p, "VS Code Copilot") for p in candidates if p.parent.exists()]


_MCP_TARGETS = [
    (Path.home() / ".claude"   / "settings.json", "Claude Code"),
    (Path.home() / ".cursor"   / "mcp.json",       "Cursor"),
    (Path.home() / ".windsurf" / "mcp.json",        "Windsurf"),
    (Path.home() / ".codex"    / "mcp.json",        "Codex"),
    # ~/.copilot/mcp-config.json handled separately by _patch_copilot_mcp (SSE + token)
    # Claude Desktop — only if already installed
    (Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json", "Claude Desktop"),
    (Path.home() / "AppData"  / "Roaming" / "Claude" / "claude_desktop_config.json",             "Claude Desktop"),
]


def _register_mcp(workspace_id: str, agent_token: str, api_url: str, dry_run: bool = False) -> None:
    """Write conduct + agent-booster MCP entries into every AI tool config found.

    Uses `npx -y mcp-remote` as the stdio bridge (#1219 Phase 3 M3 Option A)
    since the retired `conductguard-mcp` binary no longer exists. Native
    Python bridge tracked in #1229 for enterprise SBOM ask.

    The Bearer token is embedded in the args list because mcp-remote needs
    it to authenticate against the remote /mcp endpoint. This is the same
    token guard sync writes to ~/.conduct/config.json — treat as sensitive.
    """
    import shutil
    _mcp_url = api_url.rstrip("/") + "/mcp"
    servers: dict[str, dict] = {
        "conduct": {
            "command": "npx",
            "args": [
                "-y", "mcp-remote", _mcp_url,
                "--header", f"Authorization: Bearer {agent_token}",
            ],
        },
    }
    # Register agent-booster only if the binary is available
    if shutil.which("booster"):
        servers["agent-booster"] = {"command": "booster", "args": ["serve"]}

    vscode_paths = _vscode_mcp_paths()
    targets = list(_MCP_TARGETS) + vscode_paths
    vscode_cfg_paths = {p for p, _ in vscode_paths}
    found_any = False
    for cfg_path, label in targets:
        if not cfg_path.exists():
            # Create mcp.json for VS Code if Copilot is confirmed installed
            if cfg_path in vscode_cfg_paths:
                cfg_path.write_text("{}")
            else:
                continue
        found_any = True
        try:
            existing = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
        mcp = existing.setdefault("mcpServers", {})
        changed = False
        # Cut over from the retired `conductguard-mcp` binary if present —
        # else users end up with both entries and Claude Desktop shows two
        # servers pointing at the same tools.
        if "conductguard" in mcp:
            mcp.pop("conductguard")
            changed = True
        for name, entry in servers.items():
            if mcp.get(name) == entry:
                print(f"  {_guard_shared.GRAY}{name} MCP already registered in {label}{_guard_shared.RESET}")
            else:
                mcp[name] = entry
                changed = True
                print(f"  {_guard_shared.GREEN}{name} MCP registered in {label}{_guard_shared.RESET}")
        if changed:
            cfg_path.write_text(json.dumps(existing, indent=2))
    if not found_any:
        print(f"  {_guard_shared.GRAY}No AI tool configs found for MCP registration{_guard_shared.RESET}")

    # Copilot CLI supports HTTP and stdio; use the authenticated central HTTP server.
    _patch_copilot_mcp(agent_token, api_url)

    # Claude Desktop doesn't source shell env — patch apiBaseUrl directly in config
    # so all LLM calls route through the Guard proxy (PII blocking, spend limits, audit).
    _patch_claude_desktop_proxy(api_url, agent_token)

    # Cursor global rules — write Guard policies as user rules so they apply across all projects.
    _guard_instructions._patch_cursor_global_rules()
    _guard_instructions._patch_tool_instruction_files(agent_token, api_url, dry_run=dry_run)


def _patch_claude_desktop_proxy(api_url: str, agent_token: str) -> None:
    """Patch Claude Desktop config to route LLM calls through the Guard proxy.

    Claude Desktop reads apiBaseUrl from its config JSON — it does not source
    shell env vars, so ANTHROPIC_BASE_URL has no effect. We write the proxy
    URL directly so PII blocking, spend limits, and audit apply to Desktop too.
    """
    proxy_url = f"{api_url.rstrip('/')}/gateway/v1/anthropic"
    candidates = [
        Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
    ]
    for cfg_path in candidates:
        if not cfg_path.exists():
            continue
        try:
            cfg = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
        current = cfg.get("apiBaseUrl", "")
        if current == proxy_url:
            print(f"  {_guard_shared.GRAY}Claude Desktop proxy already set → {proxy_url}{_guard_shared.RESET}")
            continue
        cfg["apiBaseUrl"] = proxy_url
        cfg_path.write_text(json.dumps(cfg, indent=2))
        print(f"  {_guard_shared.GREEN}Claude Desktop proxy set → {proxy_url}{_guard_shared.RESET}")
        print(f"  {_guard_shared.YELLOW}Restart Claude Desktop for proxy routing to take effect{_guard_shared.RESET}")


def _patch_copilot_mcp(agent_token: str, api_url: str) -> None:
    """Keep ~/.copilot/mcp-config.json and any .mcp.json in cwd in sync with current agent token."""
    import shutil
    sse_entry = {
        "type": "http",
        "url": f"{api_url}/mcp",
        "headers": {"Authorization": f"Bearer {agent_token}"},
    }
    booster_entry = {"command": "booster", "args": ["serve"]} if shutil.which("booster") else None

    # ~/.copilot/mcp-config.json (global Copilot config)
    global_path = _guard_shared._copilot_home() / "mcp-config.json"
    if _guard_shared._copilot_cli_installed():
        global_path.parent.mkdir(parents=True, exist_ok=True)
        if global_path.exists():
            try:
                existing = json.loads(global_path.read_text())
                if not isinstance(existing, dict) or not isinstance(existing.get("mcpServers", {}), dict):
                    raise ValueError("Invalid MCP config")
            except (OSError, ValueError):
                print(f"  {_guard_shared.YELLOW}Copilot MCP config is unreadable or invalid; left unchanged.{_guard_shared.RESET}")
                return
        _write_mcp_file(global_path, "conduct-guard", sse_entry, booster_entry, "GitHub Copilot (global)")
        global_path.chmod(0o600)

    # .mcp.json in cwd (project-level, picked up by VS Code Copilot)
    local_path = Path.cwd() / ".mcp.json"
    if local_path.exists():
        _write_mcp_file(local_path, "conduct-guard", sse_entry, booster_entry, "GitHub Copilot (.mcp.json)")


def _write_mcp_file(
    cfg_path: Path,
    guard_key: str,
    sse_entry: dict,
    booster_entry: dict | None,
    label: str,
) -> None:
    try:
        cfg = json.loads(cfg_path.read_text())
    except FileNotFoundError:
        cfg = {}
    except (json.JSONDecodeError, OSError):
        print(f"  {_guard_shared.YELLOW}MCP config is unreadable or invalid in {label}; left unchanged.{_guard_shared.RESET}")
        return
    if not isinstance(cfg, dict) or not isinstance(cfg.get("mcpServers", {}), dict):
        print(f"  {_guard_shared.YELLOW}MCP config is invalid in {label}; left unchanged.{_guard_shared.RESET}")
        return
    mcp = cfg.setdefault("mcpServers", {})
    changed = False
    current = mcp.get(guard_key)
    # Headerless remote entries use native OAuth discovery, including DCR.
    preserve_oauth = isinstance(current, dict) and (
        any(key.startswith("oauth") for key in current)
        or (
            current.get("type") in {"http", "sse", "streamable-http"}
            and current.get("url")
            and isinstance(current.get("headers", {}), dict)
            and not any(key.lower() == "authorization" for key in current.get("headers", {}))
        )
    )
    if preserve_oauth:
        print(f"  {_guard_shared.GRAY}conduct-guard native OAuth configuration preserved in {label}{_guard_shared.RESET}")
    elif current != sse_entry:
        mcp[guard_key] = sse_entry
        changed = True
        print(f"  {_guard_shared.GREEN}conduct-guard MCP registered in {label}{_guard_shared.RESET}")
    else:
        print(f"  {_guard_shared.GRAY}conduct-guard MCP already registered in {label}{_guard_shared.RESET}")
    if booster_entry and mcp.get("agent-booster") != booster_entry:
        mcp["agent-booster"] = booster_entry
        changed = True
    if changed:
        cfg_path.write_text(json.dumps(cfg, indent=2))
