"""Guard CLI: discovery."""
from __future__ import annotations

from pathlib import Path
import json
import urllib.error
import urllib.request

from . import gateway as _guard_gateway
from . import shared as _guard_shared
from .copilot import configured as copilot_configured


def _detect_ai_tools() -> list[dict]:
    """Return list of detected AI coding tools with mcp_registered, hook_registered, proxy_routed."""
    home = Path.home()

    def _check_json_mcp(path: Path) -> bool:
        try:
            d = json.loads(path.read_text()) if path.exists() else {}
            return any("conduct" in k for k in d.get("mcpServers", {}))
        except Exception:
            return False

    def _check_json_hook(path: Path) -> bool:
        try:
            d = json.loads(path.read_text()) if path.exists() else {}
            hooks = d.get("hooks", {})
            pre = hooks.get("PreToolUse", [])
            return any("conductguard" in str(h) or "conduct" in str(h).lower() for h in pre)
        except Exception:
            return False

    def _check_toml_str(path: Path, needle: str) -> bool:
        try:
            return needle in (path.read_text() if path.exists() else "")
        except Exception:
            return False

    def _claude_desktop_proxied() -> bool:
        candidates = [
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        ]
        for p in candidates:
            if p.exists():
                try:
                    url = json.loads(p.read_text()).get("apiBaseUrl", "")
                    return "conductai.ai" in url or "conduct" in url.lower()
                except Exception:
                    pass
        return False

    tools = []

    claude_dir = home / ".claude"
    if claude_dir.exists():
        settings = claude_dir / "settings.json"
        tools.append({
            "name": "claude-code",
            "mcp_registered": _check_json_mcp(settings),
            "hook_registered": _check_json_hook(settings),
            "proxy_routed": _guard_gateway._is_anthropic_proxied(),
        })

    codex_dir = home / ".codex"
    if codex_dir.exists():
        config = codex_dir / "config.toml"
        is_desktop = _check_toml_str(config, "[desktop]")
        # Codex Desktop uses the same provider configuration as Codex CLI.
        # Do not report it as partial when the Conduct provider is selected.
        codex_proxy = _check_toml_str(config, 'model_provider = "conduct"')
        codex_mcp = _check_toml_str(config, "mcp_servers.conduct") or _check_toml_str(config, "conduct-mcp")
        if is_desktop:
            tools.append({
                "name": "codex-desktop",
                "mcp_registered": codex_mcp,
                "hook_registered": _check_toml_str(config, "conductguard") or _check_toml_str(config, "conduct"),
                "proxy_routed": codex_proxy,
            })
        else:
            tools.append({
                "name": "codex",
                "mcp_registered": codex_mcp,
                "hook_registered": _check_toml_str(config, "conductguard") or _check_toml_str(config, "conduct"),
                "proxy_routed": _guard_gateway._is_openai_proxied(),
            })

    cursor_dir = home / ".cursor"
    if cursor_dir.exists():
        tools.append({
            "name": "cursor",
            "mcp_registered": _check_json_mcp(cursor_dir / "mcp.json"),
            "hook_registered": False,
            "proxy_routed": _guard_gateway._is_anthropic_proxied(),
        })

    windsurf_dir = home / ".codeium" / "windsurf"
    if windsurf_dir.exists():
        tools.append({
            "name": "windsurf",
            "mcp_registered": _check_json_mcp(windsurf_dir / "mcp_config.json"),
            "hook_registered": False,
            "proxy_routed": _guard_gateway._is_anthropic_proxied(),
        })

    claude_desktop_candidates = [
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
    ]
    if any(p.exists() for p in claude_desktop_candidates):
        tools.append({
            "name": "claude-desktop",
            "mcp_registered": False,
            "hook_registered": False,
            "proxy_routed": _claude_desktop_proxied(),
        })

    if _guard_shared._copilot_cli_installed():
        try:
            copilot_mcp = json.loads((_guard_shared._copilot_home() / "mcp-config.json").read_text())
            mcp_registered = "conduct-guard" in copilot_mcp.get("mcpServers", {})
        except (OSError, ValueError, AttributeError, TypeError):
            mcp_registered = False
        tools.append({
            "name": "copilot-cli", "mcp_registered": mcp_registered,
            "hook_registered": (_guard_shared._copilot_home() / "hooks" / "conduct-guard.json").exists(),
            "proxy_routed": copilot_configured(),
        })

    vscode_ext_dir = home / ".vscode" / "extensions"
    copilot_installed = vscode_ext_dir.exists() and any(
        p.name.startswith("github.copilot") for p in vscode_ext_dir.iterdir() if p.is_dir()
    )
    if copilot_installed:
        vscode_candidates = [
            home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
            home / ".config" / "Code" / "User" / "settings.json",
            home / ".vscode" / "settings.json",
        ]
        vscode_settings = next((p for p in vscode_candidates if p.exists()), None)
        try:
            d = json.loads(vscode_settings.read_text()) if vscode_settings else {}
            mcp_reg = any("conduct" in k for k in d.get("mcp", {}).get("servers", {}))
        except Exception:
            mcp_reg = False
        # Also check ~/.copilot/mcp-config.json (SSE entry written by guard sync)
        if not mcp_reg:
            try:
                copilot_cfg = home / ".copilot" / "mcp-config.json"
                mcp_reg = "conduct-guard" in json.loads(copilot_cfg.read_text()).get("mcpServers", {})
            except Exception:
                pass
        tools.append({
            "name": "copilot",
            "mcp_registered": mcp_reg,
            "hook_registered": False,
            "proxy_routed": False,
        })

    return tools


def _report_tools_to_server() -> None:
    """Detect AI coding tools on this machine and POST coverage to Guard API. Silent on failure."""
    tools = _detect_ai_tools()

    if not tools:
        return

    try:
        cfg = _guard_shared._load_guard_config()
        base_url = _guard_shared._api_url(cfg)
        email = cfg.get("user_email", "")
        token = cfg.get("agent_token", "")
        if not email:
            return
        conduct_cfg_path = Path.home() / ".conduct" / "config.json"
        conduct_agent_token = ""
        if conduct_cfg_path.exists():
            try:
                conduct_agent_token = json.loads(conduct_cfg_path.read_text()).get("agent_token", "")
            except Exception:
                pass

        payload = json.dumps({"email": email, "tools": tools}).encode()
        headers = {"Content-Type": "application/json"}
        if conduct_agent_token:
            headers["Authorization"] = f"Bearer {conduct_agent_token}"
        elif token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"{base_url}/guard/developer-tools",
            data=payload,
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


def _discover_config_agents() -> list[tuple]:
    """Compatibility wrapper: configuration findings are not protection evidence."""
    from .inventory import collect, tool_root
    return [(a["framework"], tool_root(a["framework"]), False)
            for a in collect(config_only=True)["agents"] if a["detection"] == "installed"]


def _scan_processes() -> list[dict]:
    """Compatibility wrapper without command-line collection."""
    from .inventory import collect
    return [a for a in collect()["agents"] if a["detection"] == "running"]


def cmd_guard_discover(args):
    """Report local facts and server-linked evidence using the same inventory as watch."""
    from .inventory import collect, verify_gateway
    cfg = _guard_shared._load_guard_config()
    report = collect(getattr(args, "config_only", False))
    if getattr(args, "verify_gateway", True):
        verify_gateway(report, cfg.get("agent_token", ""), cfg)
        print("Gateway check uses the CLI credential; it does not prove this tool's inference traffic.")
    report["triggered_by"] = "cli"
    print(f"\nDiscovery: {len(report['agents'])} local findings ({report['status']})")
    try:
        result = _guard_shared._req("POST", f"{_guard_shared._api_url(cfg)}/guard/discover/scan",
                                    body=report, token=cfg.get("agent_token", ""))
        if isinstance(result, dict) and "summary" in result and "agents" in result:
            report["server_inventory"] = result
    except (Exception, SystemExit):
        print("Upload failed; local findings only. Server evidence unavailable.")
    for item in report.get("server_inventory", {}).get("agents", report["agents"]):
        evidence = item.get("evidence", {})
        hooks = item.get("hooks_status", "configured" if evidence.get("hooks_configured") else "unverified")
        mcp = item.get("mcp_configured", evidence.get("mcp_configured", False))
        gateway = item.get("gateway_status", evidence.get("gateway_connection_status",
                           "configured" if evidence.get("gateway_configured") else "unverified"))
        print(f"  {item['framework']} [{item['detection']}] | hooks: {hooks} | MCP: {'configured' if mcp else 'unverified'} | gateway: {gateway}")
    print("Configuration is not proof of enforcement. Run conduct guard sync for supported tool setup.")
    if getattr(args, "report", None):
        Path(args.report).write_text(json.dumps(report, indent=2))
