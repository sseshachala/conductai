"""Guard CLI: mcp."""
from __future__ import annotations

from pathlib import Path
import json
from conduct_cli.deployment import api_url as configured_api, is_hosted_mcp_move, resolve
from conduct_cli.tool_adapters import ADAPTERS

from . import instructions as _guard_instructions
from . import shared as _guard_shared


def _deployment(api_url: str):
    cfg = _guard_shared._load_guard_config()
    if configured_api(cfg) != api_url.rstrip("/"):
        cfg = {"api_url": api_url}
    return resolve(cfg)


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
    (Path.home() / ".codeium" / "windsurf" / "mcp_config.json", "Windsurf"),
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
    selected = _deployment(api_url)
    _mcp_url = selected.mcp
    if dry_run:
        print(f"  Would register Conduct MCP at {_mcp_url}; no files written")
        return
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
    targets = []
    for tool in ("claude-code", "cursor", "windsurf"):
        from .tool_lifecycle import disabled
        if disabled(tool):
            continue
        adapter = ADAPTERS[tool]
        if adapter.root().is_dir():
            source = next(s for s in adapter.mcp_sources() if s.scope == "user")
            targets.append((source.path, tool))
    home = Path.home()
    targets.extend((path, "Claude Desktop") for path in (
        home / "Library/Application Support/Claude/claude_desktop_config.json",
        home / "AppData/Roaming/Claude/claude_desktop_config.json",
    ) if path.exists())
    targets.extend(vscode_paths)
    vscode_cfg_paths = {p for p, _ in vscode_paths}
    found_any = False
    for cfg_path, label in targets:
        if cfg_path.is_symlink():
            print(f"  {label} MCP config is a symlink; left unchanged")
            continue
        if not cfg_path.exists():
            # Create mcp.json for VS Code if Copilot is confirmed installed
            if cfg_path in vscode_cfg_paths or label in {"claude-code", "cursor", "windsurf"}:
                cfg_path.write_text("{}")
            else:
                continue
        found_any = True
        try:
            existing = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            print(f"  {label} MCP config is unreadable; left unchanged.")
            continue
        if not isinstance(existing, dict) or not isinstance(existing.get("mcpServers", {}), dict):
            print(f"  {label} MCP config is invalid; left unchanged.")
            continue
        mcp = existing.setdefault("mcpServers", {})
        changed = False
        # Cut over from the retired `conductguard-mcp` binary if present —
        # else users end up with both entries and Claude Desktop shows two
        # servers pointing at the same tools.
        if "conductguard" in mcp:
            mcp.pop("conductguard")
            changed = True
        for name, entry in servers.items():
            prior = mcp.get(name)
            if prior is not None and prior != entry and not (
                isinstance(prior, dict) and prior.get("command") in {"npx", "conductguard-mcp", "conduct-mcp", "booster"}
                and (prior.get("command") != "npx" or isinstance(prior.get("args"), list) and "mcp-remote" in prior["args"])
            ):
                print(f"  {name} MCP override in {label}; left unchanged")
                continue
            if mcp.get(name) == entry:
                print(f"  {_guard_shared.GRAY}{name} MCP already registered in {label}{_guard_shared.RESET}")
            else:
                mcp[name] = entry
                changed = True
                print(f"  {_guard_shared.GREEN}{name} MCP registered in {label}{_guard_shared.RESET}")
        if changed:
            cfg_path.write_text(json.dumps(existing, indent=2))
            cfg_path.chmod(0o600)
    if not found_any:
        print(f"  {_guard_shared.GRAY}No AI tool configs found for MCP registration{_guard_shared.RESET}")

    # Copilot CLI supports HTTP and stdio; use the authenticated central HTTP server.
    _patch_copilot_mcp(agent_token, api_url)
    if ADAPTERS["codex"].root().is_dir() and not disabled("codex"):
        from conduct_cli.main import _write_codex_mcp_config
        if not _write_codex_mcp_config(api_url, agent_token):
            print("  Codex MCP config could not be updated; left unchanged")

    # Claude Desktop doesn't source shell env — patch apiBaseUrl directly in config
    # so all LLM calls route through the Guard proxy (PII blocking, spend limits, audit).
    if selected.gateway:
        _patch_claude_desktop_proxy(api_url, agent_token, gateway_url=selected.gateway)

    # Cursor global rules — write Guard policies as user rules so they apply across all projects.
    _guard_instructions._patch_cursor_global_rules()
    _guard_instructions._patch_tool_instruction_files(agent_token, api_url, dry_run=dry_run)


def _patch_claude_desktop_proxy(api_url: str, agent_token: str, *, gateway_url: str | None = None) -> None:
    """Patch Claude Desktop config to route LLM calls through the Guard proxy.

    Claude Desktop reads apiBaseUrl from its config JSON — it does not source
    shell env vars, so ANTHROPIC_BASE_URL has no effect. We write the proxy
    URL directly so PII blocking, spend limits, and audit apply to Desktop too.
    """
    base = gateway_url or _deployment(api_url).gateway
    if not base:
        return
    proxy_url = base.rstrip("/") + "/anthropic"
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
    from .tool_lifecycle import disabled
    if disabled("copilot-cli"):
        return
    sse_entry = {
        "type": "http",
        "url": _deployment(api_url).mcp,
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
    if preserve_oauth and is_hosted_mcp_move(current.get("url"), sse_entry.get("url")):
        # Same deployment, new hosted default. The OAuth resource metadata still names
        # api.conductai.ai/mcp, so keep native-OAuth entries (and their sign-in) where they are.
        print(f"  {_guard_shared.GRAY}conduct-guard native OAuth configuration preserved in {label}{_guard_shared.RESET}")
    elif preserve_oauth and current.get("url") != sse_entry.get("url"):
        # OAuth registrations belong to the old issuer; never carry them across.
        mcp[guard_key] = {"type": current.get("type", "http"), "url": sse_entry["url"]}
        changed = True
        print(f"  Conduct MCP endpoint updated in {label}; sign in again for this deployment.")
    elif preserve_oauth:
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
