import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from conduct_cli import api
from conduct_cli import guard as _guard

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
RED    = "\033[31m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"

CONFIG_PATH  = Path.home() / ".conduct" / "config.json"
_UPDATE_CACHE = Path.home() / ".conduct" / "update_check.json"
_UPDATE_TTL   = 86400  # check PyPI at most once per 24 hours


def _auto_update() -> None:
    """Check PyPI for a newer conduct-cli version and upgrade + re-exec if found."""
    # Skip inside CI or if explicitly disabled
    if os.environ.get("CONDUCT_NO_AUTOUPDATE") or os.environ.get("CI"):
        return

    now = time.time()

    # Respect the 24-hour cache
    if _UPDATE_CACHE.exists():
        try:
            cached = json.loads(_UPDATE_CACHE.read_text())
            if now - cached.get("ts", 0) < _UPDATE_TTL:
                return
        except Exception:
            pass

    # Get installed version
    try:
        current = importlib.metadata.version("conduct-cli")
    except Exception:
        return

    # Fetch latest from PyPI (short timeout — never block the user)
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/conduct-cli/json",
            headers={"Accept": "application/json", "User-Agent": f"conduct-cli/{current}"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            latest = json.loads(resp.read())["info"]["version"]
    except Exception:
        return

    # Save check timestamp regardless of result
    try:
        _UPDATE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _UPDATE_CACHE.write_text(json.dumps({"ts": now, "latest": latest, "current": current}))
    except Exception:
        pass

    if latest == current:
        return

    print(f"{YELLOW}conduct-cli {current} → {latest} available. Updating…{RESET}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "conduct-cli", "-q"],
        capture_output=True,
    )
    if result.returncode == 0:
        print(f"{GREEN}✓ Updated to {latest}.{RESET}\n")
        # Re-exec so the new version handles this command
        os.execv(sys.executable, [sys.executable, "-m", "conduct_cli.main"] + sys.argv[1:])
    else:
        print(f"{YELLOW}Auto-update failed — run: pip install --upgrade conduct-cli{RESET}\n")


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def _resolve(args, key: str, config_key=None):
    """Return value from CLI args first, then config file."""
    val = getattr(args, key.replace("-", "_"), None)
    if val:
        return val
    cfg = _load_config()
    return cfg.get(config_key or key)


def _require_auth(args):
    """Return (server, workspace_id, api_key, token) — exit if not configured."""
    server     = _resolve(args, "server")
    workspace  = _resolve(args, "workspace")
    api_key    = _resolve(args, "api_key", "api_key")
    token      = _resolve(args, "token")

    if not server:
        print(f"{RED}No server set. Run: conduct login --server <url> --api-key <key>{RESET}")
        sys.exit(1)
    if not workspace:
        print(f"{RED}No workspace set. Run: conduct login --workspace <id>{RESET}")
        sys.exit(1)
    if not api_key and not token:
        print(f"{RED}No credentials. Run: conduct login --api-key <key>{RESET}")
        sys.exit(1)

    return server.rstrip("/"), workspace, api_key, token


# ── Stream helper ─────────────────────────────────────────────────────────────

def _stream_run(server: str, workflow_id: str, run_id: str, workspace_id: str, token=None, api_key=None) -> bool:
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    # SSE endpoint reads auth from query params (EventSource can't set headers)
    qs_parts = [f"workspace_id={workspace_id}"]
    if token:
        qs_parts.append(f"token={token}")
    if api_key:
        qs_parts.append(f"api_key={api_key}")
    url  = f"{server}/workflows/{workflow_id}/runs/{run_id}/stream?{'&'.join(qs_parts)}"

    for data in api.stream(url, hdrs):
        kind    = data.get("kind", "")
        bid     = data.get("block_id") or ""
        payload = data.get("payload", data)
        prefix  = f"[{bid}] " if bid else ""

        if kind == "block_started":
            label = payload.get("label") or payload.get("type", "")
            print(f"{BLUE}    ▶ {prefix}{label}{RESET}")
        elif kind == "block_completed":
            summary = payload.get("summary") or json.dumps(payload, default=str)[:120]
            print(f"{GREEN}    ✓ {prefix}{summary}{RESET}")
        elif kind == "block_failed":
            err = payload.get("error", json.dumps(payload, default=str)[:200])
            print(f"{RED}    ✗ {prefix}{err}{RESET}")
        elif kind == "brain_tool_call":
            summary = payload.get("summary", payload.get("tool", ""))
            print(f"{GRAY}      · {summary}{RESET}")
        elif kind == "run_completed":
            print(f"{BOLD}{GREEN}    ✓ done{RESET}")
        elif kind == "run_failed":
            err = payload.get("error", "")
            print(f"{BOLD}{RED}    ✗ failed: {err}{RESET}")
        else:
            print(f"{GRAY}    {kind}: {json.dumps(payload, default=str)[:120]}{RESET}")

        if kind in ("run_completed", "run_failed"):
            return kind == "run_completed"

    return False


def _poll_run(server: str, workflow_id: str, run_id: str, hdrs: dict) -> bool:
    """Poll run status until terminal — fallback when SSE stream unavailable.

    'paused' is treated as pass: the run reached a human-approval step, which
    is correct behaviour for approval-gated agents.
    """
    terminal = {"succeeded", "failed", "cancelled"}
    for _ in range(360):  # max 30 min — dependency installs can take 20-25 min
        time.sleep(5)
        try:
            run = api.req("GET", f"{server}/runs/{run_id}", hdrs)
            status = run.get("status", "")
            print(f"{GRAY}    status: {status}{RESET}", end="\r")
            if status == "paused":
                print(f"\n{GRAY}    (paused — awaiting approval){RESET}")
                return True
            if status in terminal:
                print()
                return status == "succeeded"
        except Exception:
            pass
    print(f"{RED}    timed out waiting for run{RESET}")
    return False


# ── Commands ──────────────────────────────────────────────────────────────────

def _write_claude_mcp_settings() -> bool:
    """Write conduct-mcp into ~/.claude/settings.json. Returns True if written."""
    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        existing = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        servers = existing.setdefault("mcpServers", {})
        if "conduct" in servers:
            return True  # already registered
        servers["conduct"] = {"command": "conduct-mcp", "args": []}
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(existing, indent=2))
        return True
    except Exception:
        return False


def _write_codex_mcp_config() -> bool:
    """Write conduct-mcp into ~/.codex/config.toml. Returns True if written."""
    codex_dir = Path.home() / ".codex"
    if not codex_dir.exists():
        return False
    config_path = codex_dir / "config.toml"
    try:
        content = config_path.read_text() if config_path.exists() else ""
        if "conduct-mcp" in content:
            return True
        mcp_block = '\n[mcp_servers.conduct]\ncommand = "conduct-mcp"\nargs = []\n'
        config_path.write_text(content + mcp_block)
        return True
    except Exception:
        return False


def _write_cursor_mcp_config() -> bool:
    """Write conduct-mcp into ~/.cursor/mcp.json. Returns True if written."""
    cursor_dir = Path.home() / ".cursor"
    if not cursor_dir.exists():
        return False
    config_path = cursor_dir / "mcp.json"
    try:
        existing = json.loads(config_path.read_text()) if config_path.exists() else {}
        servers = existing.setdefault("mcpServers", {})
        if "conduct" in servers:
            return True
        servers["conduct"] = {"command": "conduct-mcp", "args": []}
        config_path.write_text(json.dumps(existing, indent=2))
        return True
    except Exception:
        return False


def _write_windsurf_mcp_config() -> bool:
    """Write conduct-mcp into ~/.codeium/windsurf/mcp_config.json. Returns True if written."""
    config_path = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
    if not config_path.parent.exists():
        return False
    try:
        existing = json.loads(config_path.read_text()) if config_path.exists() else {}
        servers = existing.setdefault("mcpServers", {})
        if "conduct" in servers:
            return True
        servers["conduct"] = {"command": "conduct-mcp", "args": []}
        config_path.write_text(json.dumps(existing, indent=2))
        return True
    except Exception:
        return False


def _write_vscode_mcp_config() -> bool:
    """Write conduct-mcp into VS Code settings.json (mcp.servers). Returns True if written."""
    # Check both standard locations
    candidates = [
        Path.home() / ".vscode" / "settings.json",
        Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        Path.home() / ".config" / "Code" / "User" / "settings.json",
    ]
    settings_path = next((p for p in candidates if p.exists()), None)
    if not settings_path:
        return False
    try:
        existing = json.loads(settings_path.read_text()) if settings_path.exists() else {}
        servers = existing.setdefault("mcp", {}).setdefault("servers", {})
        if "conduct" in servers:
            return True
        servers["conduct"] = {"command": "conduct-mcp", "args": []}
        settings_path.write_text(json.dumps(existing, indent=2))
        return True
    except Exception:
        return False


def _detect_ai_tools() -> list:
    """
    Detect which AI coding tools are installed and whether Guard/conduct-mcp is registered.
    Returns list of {name, mcp_registered, hook_registered} for each detected tool.
    Only includes tools whose config directory exists on this machine.
    """
    home = Path.home()
    results = []

    def _check_json_mcp(path: Path) -> bool:
        try:
            d = json.loads(path.read_text()) if path.exists() else {}
            return "conduct" in d.get("mcpServers", {})
        except Exception:
            return False

    def _check_json_hook(path: Path, hook_key: str = "hooks") -> bool:
        try:
            d = json.loads(path.read_text()) if path.exists() else {}
            hooks = d.get(hook_key, {})
            pre = hooks.get("PreToolUse", [])
            return any("conductguard" in str(h) or "conduct" in str(h).lower() for h in pre)
        except Exception:
            return False

    def _check_toml_str(path: Path, needle: str) -> bool:
        try:
            return needle in (path.read_text() if path.exists() else "")
        except Exception:
            return False

    # Claude Code
    claude_dir = home / ".claude"
    if claude_dir.exists():
        settings = claude_dir / "settings.json"
        results.append({
            "name": "claude-code",
            "mcp_registered": _check_json_mcp(settings),
            "hook_registered": _check_json_hook(settings),
        })

    # Codex
    codex_dir = home / ".codex"
    if codex_dir.exists():
        config = codex_dir / "config.toml"
        results.append({
            "name": "codex",
            "mcp_registered": _check_toml_str(config, "conduct-mcp"),
            "hook_registered": _check_toml_str(config, "conductguard"),
        })

    # Cursor
    cursor_dir = home / ".cursor"
    if cursor_dir.exists():
        results.append({
            "name": "cursor",
            "mcp_registered": _check_json_mcp(cursor_dir / "mcp.json"),
            "hook_registered": False,  # Cursor uses MCP only, no hook
        })

    # Windsurf
    windsurf_dir = home / ".codeium" / "windsurf"
    if windsurf_dir.exists():
        results.append({
            "name": "windsurf",
            "mcp_registered": _check_json_mcp(windsurf_dir / "mcp_config.json"),
            "hook_registered": False,  # Windsurf uses MCP only
        })

    # VS Code (Copilot)
    vscode_settings_candidates = [
        home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        home / ".config" / "Code" / "User" / "settings.json",
        home / ".vscode" / "settings.json",
    ]
    vscode_settings = next((p for p in vscode_settings_candidates if p.exists()), None)
    if vscode_settings:
        try:
            d = json.loads(vscode_settings.read_text())
            mcp_reg = "conduct" in d.get("mcp", {}).get("servers", {})
        except Exception:
            mcp_reg = False
        results.append({
            "name": "vscode",
            "mcp_registered": mcp_reg,
            "hook_registered": False,  # VS Code uses MCP only
        })

    return results


def _report_tool_coverage() -> None:
    """Detect AI tools on this machine and POST coverage to Guard API. Silent on failure."""
    try:
        cfg = _load_config()
        server  = cfg.get("server", "").rstrip("/")
        api_key = cfg.get("api_key", "")
        token   = cfg.get("token", "")
        email   = cfg.get("email", "")

        # also check guard config for email/token
        guard_cfg_path = Path.home() / ".conductguard" / "config.json"
        if guard_cfg_path.exists():
            gcfg = json.loads(guard_cfg_path.read_text())
            if not email:
                email = gcfg.get("user_email", "")
            if not token:
                token = gcfg.get("member_token", "")

        if not server or not email:
            return

        tools = _detect_ai_tools()
        if not tools:
            return

        payload = json.dumps({"email": email, "tools": tools}).encode()
        headers = {"Content-Type": "application/json"}
        if api_key and api_key.startswith("cond_live_"):
            headers["X-Api-Key"] = api_key
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
    """Register conduct-mcp in Claude Code, Codex, Cursor, Windsurf, and VS Code."""
    import shutil
    import subprocess

    registered = []

    # --- Claude Code ---
    # Write directly to ~/.claude/settings.json — `claude mcp add` without --global
    # writes to the project-level .claude/settings.json which _detect_ai_tools won't find.
    if _write_claude_mcp_settings():
        registered.append("Claude Code")

    # --- Codex CLI ---
    if _write_codex_mcp_config():
        registered.append("Codex")

    # --- Cursor ---
    if _write_cursor_mcp_config():
        registered.append("Cursor")

    # --- Windsurf ---
    if _write_windsurf_mcp_config():
        registered.append("Windsurf")

    # --- VS Code (Copilot) ---
    if _write_vscode_mcp_config():
        registered.append("VS Code (Copilot)")

    if registered:
        print(f"{GREEN}✓ conduct-mcp registered in: {', '.join(registered)}{RESET}")
        print(f"{GRAY}  Restart your AI tools to pick up the new MCP server.{RESET}")
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


def cmd_login(args):
    server    = args.server
    api_key   = args.api_key
    workspace = args.workspace
    token     = args.token

    if not server and not api_key and not workspace:
        cfg = _load_config()
        if cfg:
            print(f"{BOLD}Current config ({CONFIG_PATH}):{RESET}")
            print(f"  server:    {cfg.get('server', '—')}")
            print(f"  workspace: {cfg.get('workspace', '—')}")
            print(f"  api_key:   {'set' if cfg.get('api_key') else '—'}")
        else:
            print("No config found. Run: conduct login --server <url> --api-key <key> --workspace <id>")
        return

    cfg = _load_config()
    if server:    cfg["server"]    = server.rstrip("/")
    if api_key:   cfg["api_key"]   = api_key
    if workspace: cfg["workspace"] = workspace
    if token:     cfg["token"]     = token

    s   = cfg["server"]
    ak  = cfg.get("api_key")
    tok = cfg.get("token")

    # Auto-discover workspace from API key if not provided
    if ak and ak.startswith("cond_live_") and not cfg.get("workspace"):
        try:
            hdrs = {"X-Api-Key": ak, "Content-Type": "application/json"}
            me = api.req("GET", f"{s}/me", hdrs)
            cfg["workspace"] = me["workspace_id"]
            print(f"{GREEN}✓ Workspace discovered:{RESET} {cfg['workspace']}")
        except SystemExit:
            print(f"{YELLOW}⚠ Could not auto-discover workspace. Pass --workspace <id> manually.{RESET}")

    ws  = cfg.get("workspace", "")
    if ws and (ak or tok):
        hdrs = api.headers(ws, tok, "application/json", ak)
        try:
            api.req("GET", f"{s}/workflows", hdrs)
            print(f"{GREEN}✓ Connected to {s}{RESET}")
        except SystemExit:
            print(f"{RED}Could not connect — check your server URL, workspace ID, and API key.{RESET}")
            sys.exit(1)

    _save_config(cfg)
    print(f"{GREEN}✓ Config saved to {CONFIG_PATH}{RESET}")

    # Auto-install Guard if available for this workspace
    if ak and ak.startswith("cond_live_"):
        try:
            from conduct_cli.guard import cmd_guard_install
            import types
            fake_args = types.SimpleNamespace(api_key=ak, server=s)
            cmd_guard_install(fake_args)
        except SystemExit:
            pass  # Guard not found — skip silently
        except Exception:
            pass  # Never block login on Guard errors

    # Auto-register MCP servers in Claude Code / Codex
    try:
        import types
        cmd_mcp_install(types.SimpleNamespace())
    except Exception:
        pass  # Never block login on MCP registration errors

    # Report tool coverage to Guard
    try:
        _report_tool_coverage()
    except Exception:
        pass


def cmd_agents(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    project_filter = getattr(args, "project", None)
    url = f"{server}/workflows"
    if project_filter:
        # find project by name first
        projects = api.req("GET", f"{server}/workspaces/{workspace_id}/projects", hdrs)
        match = next((p for p in projects if p["name"].lower() == project_filter.lower()), None)
        if not match:
            print(f"{RED}Project '{project_filter}' not found.{RESET}")
            sys.exit(1)
        url += f"?project_id={match['id']}"

    workflows = api.req("GET", url, hdrs)

    if not workflows:
        print("No agents found.")
        return

    # Fetch projects for name lookup
    try:
        projects = api.req("GET", f"{server}/workspaces/{workspace_id}/projects", hdrs)
        proj_map = {str(p["id"]): p["name"] for p in projects}
    except Exception:
        proj_map = {}

    print(f"\n{BOLD}{'Agent':<35} {'Project':<20} {'Playbook':<25} {'Last run':<12} {'ID'}{RESET}")
    print("─" * 110)

    for wf in workflows:
        name        = wf.get("name", "")[:34]
        project     = proj_map.get(str(wf.get("project_id", "")), "—")[:19]
        slug        = (wf.get("playbook_slug") or "—")[:24]
        last_status = wf.get("last_run_status") or "—"
        wf_id       = str(wf.get("id", ""))

        status_color = GREEN if last_status == "succeeded" else RED if last_status == "failed" else GRAY
        print(f"  {name:<35} {project:<20} {slug:<25} {status_color}{last_status:<12}{RESET} {GRAY}{wf_id}{RESET}")

    print()


def cmd_test(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    agent_names    = args.agents
    run_all        = getattr(args, "all", False)
    project_filter = getattr(args, "project", None)
    repo_override  = getattr(args, "repo", None)
    parallel       = getattr(args, "parallel", False)

    workflows = api.req("GET", f"{server}/workflows", hdrs)

    if project_filter:
        proj = _resolve_project(server, workspace_id, hdrs, project_filter)
        proj_id = str(proj["id"])
        workflows = [wf for wf in workflows if str(wf.get("project_id") or "") == proj_id]

    if run_all:
        targets = [wf for wf in workflows if wf.get("playbook_slug")]
        if not targets:
            print("No playbook-based agents found.")
            return
    else:
        targets = []
        for name in agent_names:
            match = next((wf for wf in workflows if wf["name"].lower() == name.lower()), None)
            if not match:
                print(f"{RED}Agent '{name}' not found. Run 'conduct agents' to see available agents.{RESET}")
                sys.exit(1)
            if not match.get("playbook_slug"):
                print(f"{YELLOW}⚠ '{name}' has no playbook_slug — no built-in test payload. Skipping.{RESET}")
                continue
            targets.append(match)

    if not targets:
        print("Nothing to test.")
        return

    proj_label = f" [{project_filter}]" if project_filter else ""
    mode_label = f"{GRAY} --parallel{RESET}" if parallel else ""
    print(f"\n{BOLD}▶ conduct test{proj_label} — {len(targets)} agent(s){RESET}{mode_label}\n")

    pr_override = getattr(args, "pr", None)

    def _build_payload(slug):
        payload: dict = {}
        if repo_override:
            owner, repo = (repo_override.split("/", 1) + [""])[:2]
            clone_url = f"https://github.com/{repo_override}.git"
            payload.update({
                "repo": repo_override,
                "clone_url": clone_url,
                "repo_owner": owner,
                "repo_name": repo,
                "repo_full_name": repo_override,
                "repository": {
                    "full_name": repo_override,
                    "name": repo,
                    "owner": {"login": owner},
                    "clone_url": clone_url,
                    "default_branch": "main",
                },
            })
        if pr_override:
            pr = int(pr_override)
            repo_path = repo_override or ""
            payload.update({
                "number": pr,
                "pull_request": {
                    "number": pr,
                    "html_url": f"https://github.com/{repo_path}/pull/{pr}" if repo_path else "",
                    "diff_url": f"https://github.com/{repo_path}/pull/{pr}.diff" if repo_path else "",
                    "title": f"PR #{pr}",
                    "user": {"login": ""},
                    "base": {"ref": "main"},
                    "head": {"ref": ""},
                },
            })
        return payload

    if parallel:
        _run_tests_parallel(server, workspace_id, api_key, token, hdrs, targets, _build_payload)
    else:
        _run_tests_serial(server, workspace_id, api_key, token, hdrs, targets, _build_payload)


def _run_tests_serial(server, workspace_id, api_key, token, hdrs, targets, build_payload):
    results = []
    for wf in targets:
        name  = wf["name"]
        wf_id = str(wf["id"])
        slug  = wf.get("playbook_slug", "")

        print(f"{CYAN}── {name}{RESET} {GRAY}({slug}){RESET}")
        try:
            run = api.req("POST", f"{server}/workflows/{wf_id}/trigger", hdrs, build_payload(slug))
        except SystemExit:
            results.append((name, False, None))
            print()
            continue

        run_id = run.get("run_id")
        print(f"  {GRAY}run: {run_id}{RESET}")

        try:
            ok = _stream_run(server, wf_id, run_id, workspace_id, token, api_key)
        except Exception:
            ok = _poll_run(server, wf_id, run_id, hdrs)

        results.append((name, ok, run_id))
        print()

    _print_results(results)


def _run_tests_parallel(server, workspace_id, api_key, token, hdrs, targets, build_payload):
    """Fire all triggers immediately, then poll all runs concurrently."""
    import threading

    # Phase 1: fire all triggers at once
    pending = []  # list of (name, run_id) or (name, None) on trigger failure
    for wf in targets:
        name  = wf["name"]
        wf_id = str(wf["id"])
        slug  = wf.get("playbook_slug", "")
        print(f"  {GRAY}→ triggering {name}{RESET}")
        try:
            run    = api.req("POST", f"{server}/workflows/{wf_id}/trigger", hdrs, build_payload(slug))
            run_id = run.get("run_id")
            print(f"    {GRAY}run: {run_id}{RESET}")
            pending.append((name, wf_id, run_id))
        except SystemExit:
            pending.append((name, wf_id, None))

    print(f"\n  Polling {len(pending)} runs concurrently…\n")

    results_lock = threading.Lock()
    results: list = [None] * len(pending)

    def _poll(idx, name, wf_id, run_id):
        if run_id is None:
            with results_lock:
                results[idx] = (name, False, None)
            return
        ok = _poll_run(server, wf_id, run_id, hdrs)
        with results_lock:
            results[idx] = (name, ok, run_id)
        icon = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {icon}  {name}")

    threads = [
        threading.Thread(target=_poll, args=(i, name, wf_id, run_id), daemon=True)
        for i, (name, wf_id, run_id) in enumerate(pending)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    _print_results(results)


def _print_results(results):
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}Results:{RESET}")
    for name, ok, run_id in results:
        icon = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        rid  = f"{GRAY}{run_id[:8]}…{RESET}" if run_id else ""
        print(f"  {icon}  {name:<40} {rid}")

    print()
    color = GREEN if failed == 0 else RED
    print(f"{BOLD}{color}{passed}/{len(results)} passed{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


# ── Environment helpers ───────────────────────────────────────────────────────

def _list_environments(server: str, workspace_id: str, hdrs: dict) -> list:
    return api.req("GET", f"{server}/environments", hdrs)


def _resolve_environment(server: str, workspace_id: str, hdrs: dict, name: str) -> dict:
    envs = _list_environments(server, workspace_id, hdrs)
    match = next((e for e in envs if e["name"].lower() == name.lower()), None)
    if not match:
        print(f"{RED}Environment '{name}' not found. Run 'conduct environments' to list environments.{RESET}")
        sys.exit(1)
    return match


# ── Environment commands ──────────────────────────────────────────────────────

def cmd_environments(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    envs = _list_environments(server, workspace_id, hdrs)

    if not envs:
        print("No environments found. Create one: conduct create environment <name>")
        return

    print(f"\n{BOLD}{'Environment':<30} {'ID'}{RESET}")
    print("─" * 70)
    for e in envs:
        print(f"  {e['name']:<30} {GRAY}{e['id']}{RESET}")
    print()


def cmd_credentials(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    env = _resolve_environment(server, workspace_id, hdrs, args.environment)

    rows = api.req("GET", f"{server}/credentials/env-vars/{env['id']}", hdrs)

    if not rows:
        print(f"No credentials in environment '{args.environment}'.")
        print(f"  Add one: conduct set credential --environment \"{args.environment}\" --key GITHUB_TOKEN --value <token>")
        return

    print(f"\n{BOLD}Credentials — {args.environment}{RESET}\n")
    print(f"{BOLD}{'Key':<30} {'Value'}{RESET}")
    print("─" * 55)
    for row in rows:
        key = row["key"]
        val = row["value"]
        masked = val[:4] + "***" if val and len(val) > 4 else "***"
        print(f"  {key:<30} {GRAY}{masked}{RESET}")
    print()


def _do_set_credential(server, workspace_id, api_key, token, env_name, key, value):
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    env = _resolve_environment(server, workspace_id, hdrs, env_name)

    existing = api.req("GET", f"{server}/credentials/env-vars/{env['id']}", hdrs)
    merged = [{"key": r["key"], "value": r["value"]} for r in existing if r["key"] != key]
    merged.append({"key": key, "value": value})

    api.req("PUT", f"{server}/credentials/env-vars/{env['id']}", hdrs, merged)
    masked = value[:4] + "***" if len(value) > 4 else "***"
    print(f"{GREEN}✓ {key}{RESET} set in environment '{env_name}'  {GRAY}({masked}){RESET}")


def _do_delete_credential(server, workspace_id, api_key, token, env_name, key, yes):
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    env = _resolve_environment(server, workspace_id, hdrs, env_name)

    existing = api.req("GET", f"{server}/credentials/env-vars/{env['id']}", hdrs)
    filtered = [r for r in existing if r["key"] != key]

    if len(filtered) == len(existing):
        print(f"{YELLOW}Key '{key}' not found in environment '{env_name}'.{RESET}")
        sys.exit(1)

    if not yes:
        confirm = input(f"{YELLOW}Delete '{key}' from environment '{env_name}'? Type 'yes' to confirm: {RESET}").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return

    api.req("PUT", f"{server}/credentials/env-vars/{env['id']}", hdrs, filtered)
    print(f"{GREEN}✓ {key}{RESET} removed from environment '{env_name}'")


def cmd_set(args):
    if args.set_command == "credential":
        server, workspace_id, api_key, token = _require_auth(args)
        _do_set_credential(server, workspace_id, api_key, token,
                           args.environment, args.key, args.value)
    elif args.set_command == "environment":
        server, workspace_id, api_key, token = _require_auth(args)
        hdrs = api.headers(workspace_id, token, "application/json", api_key)

        workflows = api.req("GET", f"{server}/workflows", hdrs)
        wf = next((w for w in workflows if w["name"].lower() == args.agent.lower()), None)
        if not wf:
            print(f"{RED}Agent '{args.agent}' not found. Run 'conduct agents' to list agents.{RESET}")
            sys.exit(1)

        env = _resolve_environment(server, workspace_id, hdrs, args.environment)
        api.req("PATCH", f"{server}/workflows/{wf['id']}/environment", hdrs, {"environment_id": env["id"]})
        print(f"{GREEN}✓ Environment '{args.environment}' assigned to agent '{args.agent}'{RESET}")
    else:
        print(f"Usage: conduct set [credential|environment] ...")
        sys.exit(1)


# ── Project commands ──────────────────────────────────────────────────────────

def _list_projects(server: str, workspace_id: str, hdrs: dict) -> list:
    return api.req("GET", f"{server}/workspaces/{workspace_id}/projects", hdrs)


def _resolve_project(server: str, workspace_id: str, hdrs: dict, name: str) -> dict:
    projects = _list_projects(server, workspace_id, hdrs)
    match = next((p for p in projects if p["name"].lower() == name.lower()), None)
    if not match:
        print(f"{YELLOW}Project '{name}' not found — creating it…{RESET}")
        match = api.req("POST", f"{server}/workspaces/{workspace_id}/projects", hdrs, {"name": name})
        print(f"  {GREEN}✓ Project created:{RESET} {match['name']}  {GRAY}({match['id']}){RESET}")
    return match


def cmd_projects(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs     = api.headers(workspace_id, token, "application/json", api_key)
    projects = _list_projects(server, workspace_id, hdrs)

    if not projects:
        print("No projects found. Create one: conduct create project <name>")
        return

    print(f"\n{BOLD}{'Project':<35} {'Agents':>6}  {'ID'}{RESET}")
    print("─" * 70)
    for p in projects:
        agents = p.get("agent_count", 0)
        print(f"  {p['name']:<35} {agents:>6}  {GRAY}{p['id']}{RESET}")
    print()


def cmd_create(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    parts = args.create_args

    if parts and parts[0] == "environment":
        name = " ".join(parts[1:]).strip()
        if not name:
            print(f"{RED}Usage: conduct create environment <name>{RESET}")
            sys.exit(1)
        result = api.req("POST", f"{server}/environments", hdrs, {"name": name})
        print(f"{GREEN}✓ Environment created:{RESET} {result['name']}  {GRAY}({result['id']}){RESET}")
    else:
        # conduct create [project] <name> — "project" keyword is optional
        name = " ".join(parts[1:] if parts and parts[0] == "project" else parts).strip()
        if not name:
            print(f"{RED}Usage: conduct create [environment|project] <name>{RESET}")
            sys.exit(1)
        result = api.req("POST", f"{server}/workspaces/{workspace_id}/projects", hdrs, {"name": name})
        print(f"{GREEN}✓ Project created:{RESET} {result['name']}  {GRAY}({result['id']}){RESET}")


def cmd_delete(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    parts = args.delete_args

    if parts and parts[0] == "environment":
        name = " ".join(parts[1:]).strip()
        if not name:
            print(f"{RED}Usage: conduct delete environment <name>{RESET}")
            sys.exit(1)
        env = _resolve_environment(server, workspace_id, hdrs, name)
        if not args.yes:
            confirm = input(f"{YELLOW}Delete environment '{env['name']}'? Type 'yes' to confirm: {RESET}").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return
        api.req("DELETE", f"{server}/environments/{env['id']}", hdrs)
        print(f"{GREEN}✓ Environment '{env['name']}' deleted.{RESET}")

    elif parts and parts[0] == "credential":
        env_name = getattr(args, "environment", None)
        key      = getattr(args, "key", None)
        if not env_name or not key:
            print(f"{RED}Usage: conduct delete credential --environment <name> --key <KEY>{RESET}")
            sys.exit(1)
        _do_delete_credential(server, workspace_id, api_key, token, env_name, key, args.yes)

    else:
        # conduct delete [project] <name> [--yes] [--purge]
        name = " ".join(parts[1:] if parts and parts[0] == "project" else parts).strip()
        if not name:
            print(f"{RED}Usage: conduct delete [environment|project|credential] <name>{RESET}")
            sys.exit(1)
        proj = _resolve_project(server, workspace_id, hdrs, name)
        purge = getattr(args, "purge", False)
        if purge:
            print(f"{RED}{BOLD}⚠ PURGE mode — this will permanently delete ALL data for '{proj['name']}'{RESET}")
            print(f"{RED}  · All runs, events, and workflow versions{RESET}")
            print(f"{RED}  · Analytics and audit logs{RESET}")
            print(f"{RED}  · API keys and environments{RESET}")
            print(f"{RED}  This cannot be undone.{RESET}\n")
            confirm = input(f"{YELLOW}Type the project name to confirm: {RESET}").strip()
            if confirm != proj["name"]:
                print("Cancelled — name did not match.")
                return
        elif not args.yes:
            confirm = input(f"{YELLOW}Delete project '{proj['name']}' and all its agents? Type 'yes' to confirm: {RESET}").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return
        url = f"{server}/workspaces/{workspace_id}/projects/{proj['id']}"
        if purge:
            url += "?purge=true"
        api.req("DELETE", url, hdrs)
        suffix = " (purged)" if purge else ""
        print(f"{GREEN}✓ Project '{proj['name']}' deleted{suffix}.{RESET}")


# ── Playbook commands ─────────────────────────────────────────────────────────

def cmd_playbooks(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    slug = getattr(args, "slug", None)

    if slug:
        pb = api.req("GET", f"{server}/workflows/playbooks/{slug}", hdrs)
        print(f"\n{BOLD}{pb['icon']}  {pb['name']}{RESET}")
        print(f"  {pb['description']}")
        tags = "  ".join(pb.get("tags", []))
        if tags:
            print(f"  {GRAY}{tags}{RESET}")
        if pb.get("github_webhook"):
            events = ", ".join(pb.get("github_events", []))
            print(f"  {GRAY}Trigger: GitHub webhook ({events}){RESET}")
            print(f"  {GRAY}Requires: --repo owner/repo{RESET}")
        elif pb.get("requires_repo"):
            print(f"  {GRAY}Trigger: inbound webhook — POST your payload to the webhook URL{RESET}")
            print(f"  {GRAY}Requires: --repo owner/repo (agent clones this repo at runtime){RESET}")
        inputs = pb.get("inputs", {})
        if inputs:
            print(f"\n{BOLD}  Inputs:{RESET}")
            for k, v in inputs.items():
                default = v.get("default", "")
                required = "" if default != "" else f" {RED}(required){RESET}"
                desc = v.get("description", "")
                print(f"    {CYAN}--input {k}=<value>{RESET}{required}  {GRAY}{desc}{RESET}")
        print()
    else:
        pbs = api.req("GET", f"{server}/workflows/playbooks", hdrs)
        if not pbs:
            print("No playbooks available.")
            return
        print(f"\n{BOLD}{'Playbook':<30} {'Slug':<30} {'Tags'}{RESET}")
        print("─" * 80)
        for pb in pbs:
            tags = ", ".join(pb.get("tags", []))[:25]
            icon = pb.get("icon", "")
            name = f"{icon} {pb['name']}"[:29]
            print(f"  {name:<30} {pb['slug']:<30} {GRAY}{tags}{RESET}")
        print(f"\n  Run {CYAN}conduct playbooks <slug>{RESET} for input details.\n")


# ── Install command ───────────────────────────────────────────────────────────

def cmd_install(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    slug = args.slug

    # Fetch playbook to validate slug + get declared inputs
    pb = api.req("GET", f"{server}/workflows/playbooks/{slug}", hdrs)
    declared_inputs = pb.get("inputs", {})

    # Require --repo for all playbooks
    if not args.repo and pb.get("requires_repo"):
        if pb.get("github_webhook"):
            events = ", ".join(pb.get("github_events", []))
            print(f"{RED}Error: --repo is required for this agent.{RESET}")
            print(f"  It listens for GitHub {events} events — Conduct must register a webhook on the target repo.")
        else:
            print(f"{RED}Error: --repo is required for this agent.{RESET}")
            print(f"  It clones and operates on a GitHub repository at runtime.")
        print(f"\n  Usage: conduct install {slug} --repo owner/repo\n")
        sys.exit(1)

    # Parse --input key=val pairs
    raw_inputs: dict = {}
    for pair in (args.input or []):
        if "=" not in pair:
            print(f"{RED}Bad --input format '{pair}'. Expected key=value.{RESET}")
            sys.exit(1)
        k, v = pair.split("=", 1)
        raw_inputs[k.strip()] = v.strip()

    # Check required inputs (no default and not supplied)
    missing = [
        k for k, v in declared_inputs.items()
        if v.get("default", "__MISSING__") == "__MISSING__" and k not in raw_inputs
    ]
    if missing:
        print(f"{RED}Missing required inputs: {', '.join(missing)}{RESET}")
        print(f"  Use: conduct install {slug} --input key=value ...")
        sys.exit(1)

    # Resolve project
    project_id = None
    if args.project:
        proj = _resolve_project(server, workspace_id, hdrs, args.project)
        project_id = proj["id"]

    # Agent name — explicit --name wins; otherwise auto-suffix with 4-char ID
    # e.g. "Security Autopilot Fix [A4B2]" so multiple installs are distinguishable
    import random, string
    _base = _FRIENDLY_NAMES.get(slug) or pb["name"]
    _uid  = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    agent_name = args.name or f"{_base} [{_uid}]"

    # Repo input — inject into inputs if playbook expects github_repo
    if args.repo:
        if "github_repo" in declared_inputs:
            raw_inputs.setdefault("github_repo", args.repo)
        if "repo" in declared_inputs:
            raw_inputs.setdefault("repo", args.repo)

    body: dict = {
        "name":     agent_name,
        "template": slug,
        "inputs":   raw_inputs,
        "graph":    {"nodes": [], "edges": []},
    }
    if project_id:
        body["project_id"] = project_id
    if args.repo:
        body["repo"] = args.repo

    print(f"\n{BOLD}Installing {pb['icon']} {pb['name']}…{RESET}")
    if project_id:
        print(f"  project:  {args.project}")
    print(f"  agent:    {agent_name}")
    if raw_inputs:
        for k, v in raw_inputs.items():
            masked = v if "token" not in k.lower() and "secret" not in k.lower() else "***"
            print(f"  {k}: {masked}")
    print()

    result = api.req("POST", f"{server}/workflows", hdrs, body)

    wf_id = result.get("id", "")
    print(f"{GREEN}✓ Agent installed:{RESET} {result['name']}  {GRAY}({wf_id}){RESET}")

    webhook_error = result.get("webhook_error")
    if webhook_error:
        print(f"{YELLOW}⚠ Webhook:{RESET} {webhook_error}")
    elif args.repo:
        if pb.get("github_webhook"):
            print(f"{GREEN}✓ GitHub webhook registered{RESET} on {args.repo}")
        else:
            print(f"{GREEN}✓ Target repo stored:{RESET} {args.repo}")

    print(f"\n  Run a test: {CYAN}conduct test \"{agent_name}\"{RESET}\n")


# ── Reset command ─────────────────────────────────────────────────────────────

def cmd_reset(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)
    proj = _resolve_project(server, workspace_id, hdrs, args.name)
    project_id = proj["id"]

    workflows = api.req("GET", f"{server}/workflows?project_id={project_id}", hdrs)
    if not workflows:
        print(f"{YELLOW}Project '{args.name}' has no agents — nothing to reset.{RESET}")
        return

    print(f"\n{BOLD}Reset project '{args.name}' — {len(workflows)} agent(s) will be deleted:{RESET}")
    for wf in workflows:
        print(f"  {GRAY}· {wf['name']}{RESET}")

    if not args.yes:
        confirm = input(f"\n{YELLOW}Type 'yes' to confirm: {RESET}").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            return

    deleted = failed = 0
    for wf in workflows:
        try:
            api.req("DELETE", f"{server}/workflows/{wf['id']}", hdrs)
            print(f"  {GREEN}✓ deleted:{RESET} {wf['name']}")
            deleted += 1
        except SystemExit:
            print(f"  {RED}✗ failed:{RESET} {wf['name']}")
            failed += 1

    print(f"\n{BOLD}{GREEN}{deleted} deleted{RESET}", end="")
    if failed:
        print(f"  {RED}{failed} failed{RESET}", end="")
    print()


# ── Install-all command ───────────────────────────────────────────────────────

# All known playbook slugs in install order
_ALL_SLUGS = [
    "autopilot_quick",
    "autopilot_full",
    "autopilot_approved",
    "pr_reviewer",
    "ci_notify",
    "incident_responder",
    "dependency_updater",
    "release_notes",
    "issue_triage",
    "copilot_reviewer",
    "security_scanner",
    "security_patch_updater",
    "smoke_test",
]

_FRIENDLY_NAMES = {
    "autopilot_quick":        "Autopilot Quick",
    "autopilot_full":         "Autopilot Full",
    "autopilot_approved":     "Autopilot + Approval",
    "pr_reviewer":            "PR Reviewer",
    "ci_notify":              "CI Failure Alert",
    "incident_responder":     "Incident Responder",
    "dependency_updater":     "Dependency Updater",
    "release_notes":          "Release Notes",
    "issue_triage":           "Issue Triage",
    "copilot_reviewer":       "Copilot / AI PR Reviewer",
    "security_scanner":       "Security Scanner",
    "security_patch_updater": "Security Patch Updater",
    "smoke_test":             "Smoke Test",
}


def cmd_install_all(args):
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    slugs = _ALL_SLUGS

    print(f"\n{BOLD}▶ conduct install-all — {len(slugs)} playbooks → project '{args.project}'{RESET}")
    if args.repo:
        print(f"  repo: {args.repo}")
    print()

    installed = []
    failed    = []

    for slug in slugs:
        # Build a minimal args-like namespace for cmd_install
        class _A:
            pass
        a          = _A()
        a.slug     = slug
        a.project  = args.project
        a.repo     = args.repo
        a.name     = None
        a.input    = args.input or []

        # Patch server/workspace/auth into the namespace so _require_auth works
        a.server    = server
        a.workspace = workspace_id
        a.api_key   = api_key
        a.token     = token

        try:
            cmd_install(a)
            installed.append(slug)
        except SystemExit:
            failed.append(slug)

    # Summary
    print(f"\n{BOLD}{'─' * 50}{RESET}")
    color = GREEN if not failed else RED
    print(f"{BOLD}{color}{len(installed)}/{len(slugs)} installed{RESET}\n")

    for s in installed:
        print(f"  {GREEN}✓{RESET}  {s}")
    for s in failed:
        print(f"  {RED}✗{RESET}  {s}")
    print()

    if failed:
        print(f"{RED}Some installs failed. Fix the issue, run 'conduct reset project {args.project}', then retry.{RESET}\n")
        sys.exit(1)


def _build_state(issue: dict, repo_full_name: str) -> dict:
    owner, repo = repo_full_name.split("/", 1)
    trigger = {
        "repo_owner":     owner,
        "repo_name":      repo,
        "repo_full_name": repo_full_name,
        "issue_number":   issue["number"],
        "title":          issue["title"],
        "body":           issue.get("body") or "",
        "url":            issue["url"],
        "author":         issue["author"],
        "labels":         issue["labels"],
        "label_added":    issue["labels"][0] if issue["labels"] else "",
        "default_branch": "main",
        "clone_url":      issue["clone_url"],
    }
    return {"github_issue": trigger, "_trigger": trigger}


def cmd_run(args):
    server, workspace_id, api_key, token = _require_auth(args)
    json_h = api.headers(workspace_id, token, "application/json", api_key)

    # Parse --input key=value pairs into initial_state
    initial_state: dict = {}
    for kv in (args.input or []):
        if "=" not in kv:
            print(f"{RED}Bad --input format '{kv}' — expected key=value{RESET}")
            sys.exit(1)
        k, v = kv.split("=", 1)
        initial_state[k] = v

    # Resolve agent by name
    target = args.agent
    workflows = api.req("GET", f"{server}/workflows", json_h)

    # Filter by project if given
    if args.project:
        projects = api.req("GET", f"{server}/workspaces/{workspace_id}/projects", json_h)
        proj = next((p for p in projects if p["name"].lower() == args.project.lower()), None)
        if not proj:
            print(f"{RED}Project '{args.project}' not found.{RESET}")
            sys.exit(1)
        workflows = [w for w in workflows if w.get("project_id") == proj["id"]]

    wf = next((w for w in workflows if w["name"].lower() == target.lower()), None)
    if not wf:
        print(f"{RED}Agent '{target}' not found. Run 'conduct agents' to list agents.{RESET}")
        sys.exit(1)

    workflow_id = wf["id"]
    print(f"\n{BOLD}▶ conduct run — {wf['name']}{RESET}")
    if initial_state:
        for k, v in initial_state.items():
            print(f"  {GRAY}{k}={v}{RESET}")
    print()

    run = api.req("POST", f"{server}/workflows/{workflow_id}/runs", json_h, {
        "triggered_by": "cli",
        "initial_state": {"__manual": True, "inputs": initial_state},
    })
    _stream_run(server, workflow_id, run["id"], workspace_id, token, api_key)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    _auto_update()

    parser = argparse.ArgumentParser(
        prog="conduct",
        description="Conduct AI — agent CLI",
    )
    # Global overrides (optional — config file is preferred)
    parser.add_argument("--server",    help="API URL (default: from ~/.conduct/config.json)")
    parser.add_argument("--api-key",   dest="api_key", help="CLI API key")
    parser.add_argument("--token",     help=argparse.SUPPRESS)
    parser.add_argument("--workspace", help="Workspace ID")

    sub = parser.add_subparsers(dest="command")

    # conduct login
    login_p = sub.add_parser("login", help="Save connection config (~/.conduct/config.json)")
    login_p.add_argument("--server",    help="API base URL e.g. https://api.conductai.ai")
    login_p.add_argument("--api-key",   dest="api_key", help="CLI API key (set CLI_API_KEY on server)")
    login_p.add_argument("--workspace", help="Workspace ID (auto-discovered from API key if omitted)")
    login_p.add_argument("--token",     help=argparse.SUPPRESS)

    # conduct agents
    agents_p = sub.add_parser("agents", help="List all agents")
    agents_p.add_argument("--project", help="Filter by project name")

    # conduct test
    test_p = sub.add_parser("test", help="Fire test trigger on one or more agents")
    test_p.add_argument("agents", nargs="*", metavar="agent_name", help="Agent name(s) to test")
    test_p.add_argument("--all",      action="store_true", help="Test all playbook-based agents")
    test_p.add_argument("--parallel", action="store_true", help="Fire all triggers at once, poll concurrently (faster for many agents)")
    test_p.add_argument("--project",  metavar="name",       help="Limit to agents in this project")
    test_p.add_argument("--repo",     metavar="owner/repo", help="Override repo in test payload (e.g. sseshachala/conductai-testbed-node)")
    test_p.add_argument("--pr",       metavar="number",     help="Inject a real PR number into the test payload (e.g. 246)")

    # conduct environments
    sub.add_parser("environments", help="List all environments in the workspace")

    # conduct credentials --environment <name>
    creds_p = sub.add_parser("credentials", help="List credentials in an environment")
    creds_p.add_argument("--environment", required=True, metavar="name", help="Environment name")

    # conduct set credential|environment
    set_p = sub.add_parser("set", help="Set a credential or assign an environment to an agent")
    set_sub = set_p.add_subparsers(dest="set_command")

    set_cred_p = set_sub.add_parser("credential", help="Set a credential in an environment")
    set_cred_p.add_argument("--environment", required=True, metavar="name", help="Environment name")
    set_cred_p.add_argument("--key",         required=True, metavar="KEY",  help="Env var name (e.g. GITHUB_TOKEN)")
    set_cred_p.add_argument("--value",       required=True, metavar="VALUE", help="Credential value")

    set_env_p = set_sub.add_parser("environment", help="Assign an environment to an agent")
    set_env_p.add_argument("--agent",       required=True, metavar="name", help="Agent name (e.g. 'PR Reviewer')")
    set_env_p.add_argument("--environment", required=True, metavar="name", help="Environment name")

    # conduct projects
    sub.add_parser("projects", help="List all projects in the workspace")

    # conduct create [environment|project] <name>
    create_p = sub.add_parser("create", help="Create a project or environment")
    create_p.add_argument("create_args", nargs="+", metavar="[environment|project] name",
                          help="Type (optional) and name — e.g. 'environment Production' or 'MyProject'")

    # conduct playbooks [slug]
    pb_p = sub.add_parser("playbooks", help="List available playbooks or show detail for one")
    pb_p.add_argument("slug", nargs="?", help="Playbook slug for detail view")

    # conduct install <slug>
    install_p = sub.add_parser("install", help="Install an agent from a playbook")
    install_p.add_argument("slug",             help="Playbook slug (from 'conduct playbooks')")
    install_p.add_argument("--project",        help="Project name to install into")
    install_p.add_argument("--name",           help="Override agent name")
    install_p.add_argument("--repo",           help="GitHub repo (owner/repo) for webhook-based playbooks")
    install_p.add_argument("--input", action="append", metavar="key=value",
                           help="Playbook input value (repeatable, e.g. --input github_token=xxx)")

    # conduct delete [environment|project|credential] <name>
    delete_p = sub.add_parser("delete", help="Delete a project, environment, or credential")
    delete_p.add_argument("delete_args", nargs="+", metavar="[environment|project|credential] name",
                          help="Type (optional) and name, e.g. 'environment Production' or 'MyProject'")
    delete_p.add_argument("--environment", metavar="name", help="Environment name (for 'delete credential')")
    delete_p.add_argument("--key",         metavar="KEY",  help="Credential key (for 'delete credential')")
    delete_p.add_argument("--yes",   action="store_true", help="Skip confirmation prompt")
    delete_p.add_argument("--purge", action="store_true", help="Also erase analytics, audit logs, API keys, and environments (irreversible)")

    # conduct reset <name>
    reset_p = sub.add_parser("reset", help="Delete all agents in a project (clean slate)")
    reset_p.add_argument("name",  help="Project name")
    reset_p.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    # conduct install-all
    ia_p = sub.add_parser("install-all", help="Install all playbooks into a project")
    ia_p.add_argument("--project",  help="Project name (uses default project if omitted)")
    ia_p.add_argument("--repo",     help="GitHub repo (owner/repo)")
    ia_p.add_argument("--input",    action="append", metavar="key=value",
                      help="Input value applied to all playbooks (repeatable)")

    # conduct run (existing)
    run_p = sub.add_parser("run", help="Run an installed agent by name")
    run_p.add_argument("agent",    help="Agent name (e.g. 'security_autopilot_fix')")
    run_p.add_argument("--project", metavar="name", help="Narrow to a specific project")
    run_p.add_argument("--input",   action="append", metavar="key=value", help="Runtime input (repeatable)")

    # conduct guard
    guard_p, _guard_sub = _guard.register_guard_parser(sub)

    # conduct mcp
    mcp_p = sub.add_parser("mcp", help="Manage the Conduct MCP server")
    mcp_sub = mcp_p.add_subparsers(dest="mcp_command")
    mcp_sub.add_parser("install", help="Register conduct-mcp in Claude Code and Codex")

    args = parser.parse_args()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "agents":
        cmd_agents(args)
    elif args.command == "environments":
        cmd_environments(args)
    elif args.command == "credentials":
        cmd_credentials(args)
    elif args.command == "set":
        if not args.set_command:
            set_p.print_help()
            sys.exit(1)
        cmd_set(args)
    elif args.command == "projects":
        cmd_projects(args)
    elif args.command == "create":
        create_args = getattr(args, "create_args", None)
        if create_args:
            cmd_create(args)
        else:
            create_p.print_help()
    elif args.command == "playbooks":
        cmd_playbooks(args)
    elif args.command == "install":
        cmd_install(args)
    elif args.command == "delete":
        delete_args = getattr(args, "delete_args", None)
        if delete_args:
            cmd_delete(args)
        else:
            delete_p.print_help()
    elif args.command == "reset":
        cmd_reset(args)
    elif args.command == "install-all":
        cmd_install_all(args)
    elif args.command == "test":
        if not args.agents and not args.all:
            test_p.print_help()
            sys.exit(1)
        cmd_test(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "guard":
        _guard.dispatch_guard(args, guard_p)
    elif args.command == "mcp":
        if getattr(args, "mcp_command", None) == "install":
            cmd_mcp_install(args)
        else:
            mcp_p.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
