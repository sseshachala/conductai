"""Guard CLI: discovery."""
from __future__ import annotations

from pathlib import Path
import json
import urllib.error
import urllib.request

from . import gateway as _guard_gateway
from . import shared as _guard_shared


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
            "proxy_routed": False,
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
    """Detect installed AI tools from config dirs + .env files. No cross-module import.
    Returns list of (name, config_path, under_guard) tuples.
    """
    home = Path.home()
    results = []

    def _mcp_registered(path: Path) -> bool:
        try:
            if not path.exists():
                return False
            text = path.read_text()
            if path.suffix == ".toml":
                # conduct-mcp or conductai in mcp_servers section
                return "conduct" in text and "mcp_servers" in text
            import json as _j
            d = _j.loads(text)
            return any("conduct" in k for k in d.get("mcpServers", {}))
        except Exception:
            return False

    def _hook_registered(path: Path) -> bool:
        try:
            if not path.exists():
                # Codex: check hooks.json sibling
                hooks_path = path.parent / "hooks.json"
                if hooks_path.exists():
                    _content = hooks_path.read_text()
                    return "conductguard" in _content or "conduct" in _content
                return False
            import json as _j
            d = _j.loads(path.read_text())
            hooks = d.get("hooks", {})
            return any("conductguard" in str(h).lower() or "conduct" in str(h).lower()
                       for h in hooks.get("PreToolUse", []))
        except Exception:
            return False

    # Known tool config locations
    TOOLS = [
        ("claude-code", home / ".claude",  home / ".claude"  / "settings.json", "mcp"),
        ("codex",       home / ".codex",   home / ".codex"   / "config.toml",    "mcp"),
        ("cursor",      home / ".cursor",  home / ".cursor"  / "mcp.json",       "mcp"),
        ("windsurf",    home / ".codeium" / "windsurf", home / ".codeium" / "windsurf" / "mcp_config.json", "mcp"),
        ("copilot",     home / ".copilot", home / ".copilot" / "mcp-config.json", "mcp"),
    ]
    for name, check_dir, config_path, _ in TOOLS:
        if check_dir.exists():
            under = _mcp_registered(config_path) or _hook_registered(config_path)
            results.append((name, config_path, under))

    # .env file scan for LLM API keys — shadow agents not using known tools
    LLM_KEYS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"]
    search_paths = [home, home / "projects", home / "code", home / "dev", Path.cwd()]
    seen_envs: set[str] = set()
    for base in search_paths:
        if not base.exists():
            continue
        try:
            candidates = list(base.glob(".env"))
            # ponytail: shallow glob only — deep ** hits system dirs (WhatsApp containers etc.)
            for sub in base.iterdir() if base.exists() else []:
                try:
                    if sub.is_dir() and not sub.name.startswith("."):
                        env = sub / ".env"
                        if env.exists():
                            candidates.append(env)
                except OSError:
                    pass
        except OSError:
            continue
        for env_file in candidates:
            if str(env_file) in seen_envs or ".git" in str(env_file):
                continue
            seen_envs.add(str(env_file))
            try:
                content = env_file.read_text(errors="ignore")
                found_keys = [k for k in LLM_KEYS if k in content]
                if found_keys:
                    results.append(("env-agent", env_file, False))  # .env with LLM key = unregistered
            except OSError:
                pass

    return results


def _scan_processes() -> list[dict]:
    """Detect AI agent processes using psutil. Returns list of discovered agent dicts."""
    try:
        import psutil
    except ImportError:
        return []

    # Known framework signatures: (framework_name, cmdline_patterns)
    SIGNATURES = [
        ("langchain",      ["langchain"]),
        ("crewai",         ["crewai", "crew_ai"]),
        ("autogen",        ["autogen", "pyautogen"]),
        ("openai-agents",  ["openai-agents", "openai_agents"]),
        ("llama-index",    ["llama_index", "llamaindex"]),
        ("claude-code",    ["claude"]),
        ("codex",          ["codex"]),
        ("cursor",         ["cursor"]),
        ("windsurf",       ["windsurf"]),
        ("copilot",        ["copilot-language-server", "github.copilot"]),
    ]

    found = []
    seen = set()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or []).lower()
            name    = (proc.info["name"] or "").lower()
            combined = f"{name} {cmdline}"
            for framework, patterns in SIGNATURES:
                if any(p in combined for p in patterns):
                    key = (framework, proc.info["name"])
                    if key not in seen:
                        seen.add(key)
                        found.append({
                            "name": proc.info["name"],
                            "framework": framework,
                            "source": "process",
                            "location": f"pid:{proc.info['pid']} {proc.info['name']}",
                            "evidence": {"pid": proc.info["pid"], "cmdline": cmdline[:200]},
                            "risk_score": 60,
                        })
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return found


def cmd_guard_discover(args):
    """Scan for AI agents across config files and processes, report Guard coverage."""
    import json as _json

    cfg      = _guard_shared._load_guard_config()
    api_url  = _guard_shared._api_url(cfg)
    token    = cfg.get("agent_token", "")
    hdrs     = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Config file scan — detect AI tools from known config dirs
    config_agents = []
    for name, config_path, mcp_key in _discover_config_agents():
        under = mcp_key
        config_agents.append({
            "name": name,
            "framework": name,
            "source": "config",
            "location": str(config_path),
            "evidence": {"config_path": str(config_path), "under_guard": under},
            "risk_score": 20 if under else 70,
            "under_guard": under,
        })

    # Process scan
    process_agents: list[dict] = []
    if not getattr(args, "config_only", False):
        process_agents = _scan_processes()
        # Mark as under Guard if same framework is already registered
        registered_frameworks = {a["framework"] for a in config_agents if a["under_guard"]}
        for a in process_agents:
            a["under_guard"] = a["framework"] in registered_frameworks

    all_agents = config_agents + process_agents
    total      = len(all_agents)
    covered    = sum(1 for a in all_agents if a["under_guard"])
    missing    = total - covered
    pct        = round(covered / total * 100) if total else 0

    # Print coverage meter
    print(f"\n  Discovered {total} AI agents across your environment\n")
    config_count  = len(config_agents)
    process_count = len(process_agents)
    config_cov    = sum(1 for a in config_agents if a["under_guard"])
    process_cov   = sum(1 for a in process_agents if a["under_guard"])
    if config_count:
        print(f"  Config files:  {config_count:3d} agents   ({config_cov} under Guard, {config_count - config_cov} not)")
    if process_count:
        print(f"  Processes:     {process_count:3d} running   ({process_cov} under Guard, {process_count - process_cov} not)")
    print(f"  {'─' * 52}")
    print(f"  Guard coverage: {covered} of {total} agents  ({pct}%)\n")
    if missing:
        print(f"  Run: conduct guard discover --register to close the gap")
    print(f"  GitHub scan available — coming in v2\n")

    # POST to API
    try:
        agents_payload = list(all_agents)
        for t in _detect_ai_tools():
            agents_payload.append({
                "name": t["name"],
                "framework": t["name"],
                "source": "ai-tool",
                "under_guard": t.get("mcp_registered", False),
                "proxy_routed": t.get("proxy_routed", False),
            })
        payload = {"triggered_by": "cli", "agents": agents_payload}
        _guard_shared._req("POST", f"{api_url}/guard/discover/scan", body=payload, token=token)
    except SystemExit:
        pass  # 401/network errors — local output still useful

    # Write report if requested
    report_path = getattr(args, "report", None)
    if report_path:
        report = {"total": total, "under_guard": covered, "missing": missing, "coverage_pct": pct, "agents": all_agents}
        Path(report_path).write_text(_json.dumps(report, indent=2))
        print(f"  Report written to {report_path}")
