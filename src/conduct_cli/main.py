from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import urllib.error
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
    _atomic_write(CONFIG_PATH, data)


def _resolve(args, key: str, config_key=None):
    """Return value from CLI args first, then config file."""
    val = getattr(args, key.replace("-", "_"), None)
    if val:
        return val
    cfg = _load_config()
    return cfg.get(config_key or key)


def _require_auth(args):
    """Return (server, workspace_id, api_key, token) — exit if not configured."""
    cfg        = _load_config()
    server     = _resolve(args, "server") or cfg.get("api_url", "")
    workspace  = _resolve(args, "workspace") or cfg.get("workspace_id") or cfg.get("workspace")
    api_key    = _resolve(args, "api_key", "api_key")
    # agent_token (new) takes precedence over legacy token
    token      = _resolve(args, "token") or cfg.get("agent_token")

    if not server:
        print(f"{RED}No server set. Run: conduct login{RESET}")
        sys.exit(1)
    if not workspace:
        print(f"{RED}No workspace set. Run: conduct login{RESET}")
        sys.exit(1)
    if not api_key and not token:
        print(f"{RED}Not authenticated. Run: conduct login{RESET}")
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
            summary = payload.get("summary") or json.dumps(payload, default=str, ensure_ascii=False)[:120]
            print(f"{GREEN}    ✓ {prefix}{summary}{RESET}")
        elif kind == "block_failed":
            err = payload.get("error", json.dumps(payload, default=str, ensure_ascii=False)[:200])
            print(f"{RED}    ✗ {prefix}{err}{RESET}")
        elif kind == "brain_tool_call":
            summary = payload.get("summary", payload.get("tool", ""))
            print(f"      · {summary}{RESET}")
        elif kind == "run_completed":
            print(f"{BOLD}{GREEN}    ✓ done{RESET}")
        elif kind == "run_failed":
            err = payload.get("error", "")
            print(f"{BOLD}{RED}    ✗ failed: {err}{RESET}")
        else:
            print(f"{GRAY}    {kind}: {json.dumps(payload, default=str, ensure_ascii=False)[:120]}{RESET}")

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

def _write_mcp_config(path: Path, *, keys: tuple = ("mcpServers",), create: bool = False) -> bool:
    """Write conduct-mcp entry into a JSON config file. Returns True if written or already present."""
    if not create and not path.parent.exists():
        return False
    try:
        existing = json.loads(path.read_text()) if path.exists() else {}
        node = existing
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        servers = node.setdefault(keys[-1], {})
        if "conduct" in servers:
            return True
        servers["conduct"] = {"command": "conduct-mcp", "args": []}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(existing, indent=2))
        return True
    except Exception:
        return False


def _write_codex_mcp_config() -> bool:
    """Write conduct-mcp into ~/.codex/config.toml (TOML — different format)."""
    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.parent.exists():
        return False
    try:
        content = config_path.read_text() if config_path.exists() else ""
        if "conduct-mcp" in content:
            return True
        config_path.write_text(content + '\n[mcp_servers.conduct]\ncommand = "conduct-mcp"\nargs = []\n')
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

    # VS Code (Copilot) — only report if Copilot extension is actually installed
    vscode_ext_dir = home / ".vscode" / "extensions"
    copilot_installed = vscode_ext_dir.exists() and any(
        p.name.startswith("github.copilot") for p in vscode_ext_dir.iterdir()
        if p.is_dir()
    )
    if copilot_installed:
        vscode_settings_candidates = [
            home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
            home / ".config" / "Code" / "User" / "settings.json",
            home / ".vscode" / "settings.json",
        ]
        vscode_settings = next((p for p in vscode_settings_candidates if p.exists()), None)
        try:
            d = json.loads(vscode_settings.read_text()) if vscode_settings else {}
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
        if path and _write_mcp_config(path, keys=keys, create=create):
            registered.append(label)
    if _write_codex_mcp_config():
        registered.append("Codex")

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

    # Push updated coverage to Guard so the dashboard reflects the new state immediately
    try:
        _report_tool_coverage()
    except Exception:
        pass


_DEFAULT_API_URL = "https://api.conductai.ai"
_DEFAULT_WEB_URL = "https://app.conductai.ai"


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _exchange_clerk_token(api_url: str, clerk_token: str, workspace_id: str) -> dict:
    """POST /token (RFC 8693) to exchange a Clerk JWT for cond_agt_* + cond_ref_*."""
    _GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
    _TYPE  = "urn:ietf:params:oauth:token-type:jwt"
    body = urllib.parse.urlencode({
        "grant_type":         _GRANT,
        "subject_token":      clerk_token,
        "subject_token_type": _TYPE,
        "resource":           workspace_id,
    }).encode()
    req = urllib.request.Request(
        f"{api_url}/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return {
            "agent_token":   data["access_token"],
            "refresh_token": data.get("refresh_token", ""),
            "workspace_id":  data.get("workspace_id", workspace_id),
        }
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        print(f"{RED}Token exchange failed ({e.code}): {body_text[:120]}{RESET}")
        sys.exit(1)


def _web_login_flow(api_url: str, web_url: str) -> dict:
    """Open browser → localhost callback → return {agent_token, refresh_token, workspace_id}."""
    import http.server
    import secrets
    import threading
    import webbrowser

    state = secrets.token_urlsafe(16)
    port  = _find_free_port()
    result: dict = {}
    event = threading.Event()

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(parsed.query))

            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            # Respond immediately so browser shows success
            body = b"<html><body><h2>Login successful. You can close this tab.</h2></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            if params.get("state") == state:
                result.update(params)
            event.set()

        def log_message(self, *_):
            pass  # silence server logs

    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    auth_url = f"{web_url}/cli-auth?port={port}&state={state}&api={urllib.parse.quote(api_url, safe='')}"
    print(f"\n{BOLD}Opening browser for authentication…{RESET}")
    print(f"{GRAY}If the browser didn't open, visit:{RESET}")
    print(f"  {CYAN}{auth_url}{RESET}\n")
    webbrowser.open(auth_url)

    if not event.wait(timeout=300):
        server.shutdown()
        print(f"{RED}Login timed out (5 min). Try again.{RESET}")
        sys.exit(1)

    server.shutdown()

    if not result.get("workspace_id"):
        print(f"{RED}Login failed — missing workspace in callback. Try again.{RESET}")
        sys.exit(1)

    # RFC 8693: web page relays Clerk JWT; CLI exchanges it at POST /token
    if result.get("clerk_token") and not result.get("agent_token"):
        result = _exchange_clerk_token(api_url, result["clerk_token"], result["workspace_id"])

    if not result.get("agent_token"):
        print(f"{RED}Login failed — token exchange failed. Try again.{RESET}")
        sys.exit(1)

    return result


def _token_login_flow(agent_token: str, api_url: str) -> dict:
    """Manual --token flow: validate token against API and return workspace info."""
    hdrs = {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"}
    try:
        me = api.req("GET", f"{api_url}/me", hdrs)
        return {"agent_token": agent_token, "workspace_id": me.get("workspace_id", "")}
    except SystemExit:
        print(f"{RED}Token rejected by server. Check your token and try again.{RESET}")
        sys.exit(1)


def cmd_login(args):
    api_url = (getattr(args, "server", None) or _load_config().get("api_url", _DEFAULT_API_URL)).rstrip("/")
    web_url = _DEFAULT_WEB_URL

    # --token escape hatch: paste agent_token directly (no browser)
    manual_token = getattr(args, "token", None)
    if manual_token:
        if not manual_token.startswith("cond_agt_"):
            print(f"{RED}Invalid token format. Expected cond_agt_... token from the dashboard.{RESET}")
            sys.exit(1)
        result = _token_login_flow(manual_token, api_url)
    else:
        result = _web_login_flow(api_url, web_url)

    # Write config
    import datetime as _dt
    cfg = _load_config()
    cfg["api_url"]          = api_url
    cfg["agent_token"]      = result["agent_token"]
    cfg["workspace"]        = result["workspace_id"]
    cfg["workspace_id"]     = result["workspace_id"]
    cfg["token_expires_at"] = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=8)).isoformat()
    if result.get("refresh_token"):
        cfg["refresh_token"] = result["refresh_token"]
    # Clear legacy api_key — agent_token is the credential now
    cfg.pop("api_key", None)
    _atomic_write(CONFIG_PATH, cfg)

    print(f"{GREEN}✓ Logged in{RESET} — workspace {GRAY}{result['workspace_id']}{RESET}")

    # Auto-sync: register hooks + pull policy
    try:
        import conduct_cli.guard as _g
        import types
        _g.cmd_guard_sync(types.SimpleNamespace())
    except SystemExit:
        pass
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

    _run_tests(server, workspace_id, api_key, token, hdrs, targets, _build_payload, parallel=parallel)


def _run_tests(server, workspace_id, api_key, token, hdrs, targets, build_payload, *, parallel: bool = False):
    import threading

    if not parallel:
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
        return

    # parallel: fire all triggers, then poll concurrently
    pending = []
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
    "flaky_test_detective",
    "release_readiness",
    "postmortem_drafter",
    "docs_drift_detector",
    "terraform_reviewer",
    "thirdparty_autopilot_fix",
    "factory",
]

_FRIENDLY_NAMES = {
    "autopilot_quick":          "Autopilot Quick",
    "autopilot_full":           "Autopilot Full",
    "autopilot_approved":       "Autopilot + Approval",
    "pr_reviewer":              "PR Reviewer",
    "ci_notify":                "CI Failure Alert",
    "incident_responder":       "Incident Responder",
    "dependency_updater":       "Dependency Updater",
    "release_notes":            "Release Notes",
    "issue_triage":             "Issue Triage",
    "copilot_reviewer":         "Copilot / AI PR Reviewer",
    "security_scanner":         "Security Scanner",
    "security_patch_updater":   "Security Patch Updater",
    "smoke_test":               "Smoke Test",
    "flaky_test_detective":     "Flaky Test Detective",
    "release_readiness":        "Release Readiness Reviewer",
    "postmortem_drafter":       "Postmortem Drafter",
    "docs_drift_detector":      "Docs Drift Detector",
    "terraform_reviewer":       "Terraform Plan Reviewer",
    "thirdparty_autopilot_fix": "Third-Party Autopilot Fix",
    "factory":                  "Factory",
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


def _atomic_write(path: Path, data: dict) -> None:
    """Write data to path atomically via a .tmp sibling. Merges into existing config."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            pass
    existing.update(data)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2))
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def cmd_switch(args):
    cfg = _load_config()
    server  = cfg.get("server", "").rstrip("/")
    api_key = cfg.get("api_key", "")
    token   = cfg.get("token", "")

    if not server or (not api_key and not token):
        print(f"{RED}Not logged in. Run: conduct login --server <url> --api-key <key>{RESET}")
        sys.exit(1)

    hdrs = {"Content-Type": "application/json"}
    if api_key:
        hdrs["X-Api-Key"] = api_key
    elif token:
        hdrs["Authorization"] = f"Bearer {token}"

    workspaces = api.req("GET", f"{server}/projects", hdrs)

    current_id = cfg.get("workspace", "")
    target = getattr(args, "workspace", None)

    if not target:
        # List mode — print numbered list with current marked
        if not workspaces:
            print("No workspaces found.")
            return
        print(f"\n{BOLD}Workspaces:{RESET}")
        for i, ws in enumerate(workspaces, 1):
            marker = f"{GREEN}*{RESET}" if str(ws.get("id", "")) == str(current_id) else " "
            wid = str(ws.get("id", ""))
            print(f"  {marker} {i}. {ws['name']:<35} {GRAY}{wid}{RESET}")
        print()
        return

    # Match workspace: exact name (case-insensitive) first
    target_lower = target.lower()

    exact = [ws for ws in workspaces if ws["name"].lower() == target_lower]
    if not exact:
        # Partial name match
        partial = [ws for ws in workspaces if target_lower in ws["name"].lower()]
        if not partial:
            # UUID prefix match
            partial = [ws for ws in workspaces if str(ws.get("id", "")).startswith(target)]
        candidates = partial
    else:
        candidates = exact

    if len(candidates) > 1:
        print(f"{YELLOW}Ambiguous — multiple matches for '{target}':{RESET}")
        for ws in candidates:
            print(f"  {ws['name']}  {GRAY}({ws['id']}){RESET}")
        print("Be more specific.")
        sys.exit(1)

    if not candidates:
        print(f"{RED}No workspace matching '{target}' found. Available:{RESET}")
        for ws in workspaces:
            print(f"  {ws['name']}  {GRAY}({ws['id']}){RESET}")
        sys.exit(1)

    chosen = candidates[0]
    new_id   = str(chosen["id"])
    new_name = chosen["name"]

    # Update ~/.conduct/config.json atomically
    cfg["workspace"] = new_id; cfg["workspace_id"] = new_id
    _atomic_write(CONFIG_PATH, cfg)


    # Re-sync Guard policies for the new workspace
    try:
        policy = _guard._req(
            "GET",
            f"{server}/guard/policies/sync?workspace_id={new_id}",
            api_key=api_key,
        )
        _guard._save_policy(policy)
        rule_count = len(policy.get("rules", []))
        print(f"  {GRAY}Guard policies synced: {rule_count} rule(s){RESET}")
    except SystemExit:
        print(f"  {GRAY}Guard not configured for this workspace — policies not synced{RESET}")
    except Exception as e:
        print(f"  {YELLOW}⚠ Guard policy sync failed: {e}{RESET}")

    print(f"{GREEN}✓ Switched to \"{new_name}\" ({new_id[:8]}){RESET}")


def cmd_whoami(args):
    cfg = _load_config()

    workspace_id   = cfg.get("workspace", "")
    server         = cfg.get("server", "—")
    api_key        = cfg.get("api_key", "")

    # Try to resolve workspace name from /projects
    workspace_name = ""
    if workspace_id and server != "—" and api_key:
        try:
            hdrs = {"Content-Type": "application/json", "X-Api-Key": api_key}
            projects = api.req("GET", f"{server.rstrip('/')}/projects", hdrs)
            match = next((p for p in projects if str(p.get("id", "")) == str(workspace_id)), None)
            if match:
                workspace_name = match["name"]
        except Exception:
            pass

    ws_display = workspace_name if workspace_name else workspace_id
    ws_id_hint = f"  ({workspace_id[:8]})" if workspace_id else ""
    api_key_display = (api_key[:12] + "…  (set)") if api_key else "not set"

    print(f"\n{BOLD}Workspace:{RESET}  {ws_display}{ws_id_hint}")
    print(f"{BOLD}Server:{RESET}     {server}")
    print(f"{BOLD}API key:{RESET}    {api_key_display}")

    # Guard section — all under ~/.conduct/
    policy_path = Path.home() / ".conduct" / "policy.json"
    hook_path   = Path.home() / ".conduct" / "hook.py"
    guard_email = cfg.get("user_email", "")
    agent_token = cfg.get("agent_token", "")
    if agent_token or hook_path.exists():
        rule_count  = 0
        if policy_path.exists():
            try:
                rule_count = len(json.loads(policy_path.read_text()).get("rules", []))
            except Exception:
                pass
        hook_status = "hook installed" if hook_path.exists() else "hook missing"
        email_part  = f"  |  member: {guard_email}" if guard_email else ""
        print(f"{BOLD}Guard:{RESET}      {GREEN}✓ {hook_status}{RESET}  |  policy: {rule_count} rules{email_part}")
    else:
        print(f"{BOLD}Guard:{RESET}      not configured")

    # Booster section
    booster_paths = [
        Path.home() / ".booster" / "config.json",
        Path.home() / ".agent-booster" / "config.json",
    ]
    booster_found = any(p.exists() for p in booster_paths)
    if booster_found:
        print(f"{BOLD}Booster:{RESET}    {GREEN}✓ configured{RESET}")
    else:
        print(f"{BOLD}Booster:{RESET}    not configured")

    print()


_CLAUDE_SESSIONS = Path.home() / ".claude" / "sessions"
_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
_CODEX_SESSIONS  = Path.home() / ".codex" / "sessions"

# Context window limits by model prefix (tokens)
_CTX_LIMITS = {
    "claude-opus-4":    200_000,
    "claude-sonnet-4":  200_000,
    "claude-haiku-4":   200_000,
    "claude-opus-3":    200_000,
    "claude-sonnet-3":  200_000,
    "claude-haiku-3":   200_000,
}

def _ctx_limit(model: str) -> int:
    for prefix, limit in _CTX_LIMITS.items():
        if model.startswith(prefix):
            return limit
    return 200_000


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _session_stats(session_id: str, project_dir: Path) -> dict:
    """Parse the tail of a session JSONL for model, token counts, and turn count."""
    jsonl = project_dir / f"{session_id}.jsonl"
    if not jsonl.exists():
        return {}

    model = ""
    total_input = 0
    total_output = 0
    turns = 0
    last_usage: dict = {}

    try:
        lines = jsonl.read_bytes().splitlines()
        # Scan last 300 lines for efficiency
        for raw in lines[-300:]:
            try:
                entry = json.loads(raw)
            except Exception:
                continue
            msg = entry.get("message", {})
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "assistant":
                turns += 1
                if msg.get("model"):
                    model = msg["model"]
                usage = msg.get("usage", {})
                if usage:
                    last_usage = usage
            if msg.get("role") == "assistant" and "usage" in msg:
                u = msg["usage"]
                total_input  += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                total_output += u.get("output_tokens", 0)
    except Exception:
        pass

    cache_read = last_usage.get("cache_read_input_tokens", 0)
    fresh_in   = last_usage.get("input_tokens", 0)
    ctx_tokens = cache_read + fresh_in
    limit      = _ctx_limit(model)
    ctx_pct    = round(ctx_tokens / limit * 100) if limit else 0

    return {
        "model":      model,
        "turns":      turns,
        "ctx_tokens": ctx_tokens,
        "ctx_pct":    ctx_pct,
        "total_in":   total_input,
        "total_out":  total_output,
    }


def _codex_running_cwds() -> set[str]:
    """Return cwds of any running codex processes via /proc or ps."""
    cwds: set[str] = set()
    try:
        import subprocess as _sp
        out = _sp.run(["ps", "aux"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "codex" in line and "grep" not in line:
                # Extract cwd from lsof for each codex PID
                parts = line.split()
                if parts:
                    pid = parts[1]
                    try:
                        r = _sp.run(["lsof", "-p", pid, "-a", "-d", "cwd", "-Fn"],
                                    capture_output=True, text=True, timeout=1)
                        for l in r.stdout.splitlines():
                            if l.startswith("n"):
                                cwds.add(l[1:])
                    except Exception:
                        pass
    except Exception:
        pass
    return cwds


def _codex_session_stats(jsonl_path: Path) -> dict:
    """Parse a Codex JSONL session file for model, ctx window, and turn count."""
    model = ""
    ctx_limit = 0
    turns = 0
    cwd = ""
    try:
        for raw in jsonl_path.read_bytes().splitlines():
            try:
                entry = json.loads(raw)
            except Exception:
                continue
            t = entry.get("type", "")
            p = entry.get("payload", {})
            if t == "session_meta":
                cwd = p.get("cwd", "")
            if t == "turn_context":
                model = p.get("model", model)
                turns += 1
            if t == "event_msg" and not ctx_limit:
                ctx_limit = p.get("model_context_window", 0)
    except Exception:
        pass

    return {"model": model, "ctx_limit": ctx_limit, "turns": turns, "cwd": cwd}


def _load_codex_sessions(active_cwds: set[str]) -> list[dict]:
    """Find recent Codex sessions from ~/.codex/sessions/YYYY/MM/DD/."""
    if not _CODEX_SESSIONS.exists():
        return []

    guard_on  = (Path.home() / ".conduct" / "config.json").exists()

    rows = []
    # Walk the last 2 days of session dirs
    from datetime import datetime, timedelta
    today = datetime.now()
    date_dirs = []
    for delta in (0, 1):
        d = today - timedelta(days=delta)
        date_dirs.append(_CODEX_SESSIONS / str(d.year) / f"{d.month:02d}" / f"{d.day:02d}")

    seen: set[str] = set()
    for date_dir in date_dirs:
        if not date_dir.exists():
            continue
        for f in sorted(date_dir.iterdir(), reverse=True):
            if not f.suffix == ".jsonl":
                continue
            session_id = f.stem.split("-", 1)[-1] if "-" in f.stem else f.stem
            if session_id in seen:
                continue
            seen.add(session_id)

            stats = _codex_session_stats(f)
            cwd   = stats.get("cwd", "")
            alive = cwd in active_cwds

            ctx_limit  = stats.get("ctx_limit", 0) or 200_000
            # Codex doesn't expose per-turn token counts in JSONL — show turns only
            ctx_pct    = 0

            rows.append({
                "pid":        "—",
                "session_id": session_id[:8],
                "project":    Path(cwd).name if cwd else "—",
                "cwd":        cwd,
                "model":      stats.get("model", "—"),
                "turns":      stats.get("turns", 0),
                "ctx_pct":    ctx_pct,
                "ctx_tokens": 0,
                "total_in":   0,
                "total_out":  0,
                "guard":      guard_on,
                "alive":      alive,
                "kind":       "codex",
                "started_at": int(f.stat().st_mtime * 1000),
                "ai":         "CD",
            })

    return rows


def _load_sessions() -> list[dict]:
    """Read ~/.claude/sessions/*.json and join with JSONL stats."""
    if not _CLAUDE_SESSIONS.exists():
        return []

    guard_on  = (Path.home() / ".conduct" / "config.json").exists()

    rows = []
    seen_sessions: set[str] = set()
    for f in sorted(_CLAUDE_SESSIONS.iterdir()):
        if not f.suffix == ".json":
            continue
        try:
            s = json.loads(f.read_text())
        except Exception:
            continue

        pid        = s.get("pid", 0)
        session_id = s.get("sessionId", "")
        cwd        = s.get("cwd", "")
        started_at = s.get("startedAt", 0)
        kind       = s.get("kind", "")

        if session_id in seen_sessions:
            continue
        seen_sessions.add(session_id)

        alive = _is_alive(pid)

        # Claude names project dirs by replacing / with - (keeping leading -)
        project_key = cwd.replace("/", "-").replace("\\", "-")
        project_dir = _CLAUDE_PROJECTS / project_key

        stats = _session_stats(session_id, project_dir) if project_dir.exists() else {}

        rows.append({
            "pid":        pid,
            "session_id": session_id[:8],
            "project":    Path(cwd).name if cwd else "—",
            "cwd":        cwd,
            "model":      stats.get("model", "—"),
            "turns":      stats.get("turns", 0),
            "ctx_pct":    stats.get("ctx_pct", 0),
            "ctx_tokens": stats.get("ctx_tokens", 0),
            "total_in":   stats.get("total_in", 0),
            "total_out":  stats.get("total_out", 0),
            "guard":      guard_on,
            "alive":      alive,
            "kind":       kind,
            "started_at": started_at,
            "ai":         "CC",
        })

    # Merge Codex sessions
    active_cwds = _codex_running_cwds()
    rows += _load_codex_sessions(active_cwds)

    return sorted(rows, key=lambda r: r["started_at"], reverse=True)


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def _ctx_bar(pct: int, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    bar    = "█" * filled + "░" * (width - filled)
    color  = RED if pct >= 80 else YELLOW if pct >= 60 else GREEN
    return f"{color}{bar}{RESET} {pct}%"


def _render_table(rows: list[dict]) -> str:
    if not rows:
        return f"\n{GRAY}  No Claude Code sessions found.{RESET}\n"

    lines = []
    header = (
        f"  {BOLD}{'AI':<4} {'PROJECT':<18} {'SESSION':<10} {'MODEL':<18} "
        f"{'CTX':>14}   {'TOKENS IN':>10} {'TURNS':>6} {'GUARD':>6} {'STATUS':>8}{RESET}"
    )
    lines.append(header)
    lines.append("  " + "─" * 100)

    for r in rows:
        status_str  = f"{GREEN}active{RESET}" if r["alive"] else f"{GRAY}idle{RESET}"
        guard_str   = f"{GREEN}✓{RESET}" if r["guard"] else f"{GRAY}—{RESET}"
        model_short = r["model"].replace("claude-", "").replace("-20", " 20") if r["model"] not in ("—", "") else "—"
        ctx_display = _ctx_bar(r["ctx_pct"]) if r["ctx_pct"] else f"{GRAY}{'—':>14}{RESET}"
        tokens_str  = _fmt_tokens(r["ctx_tokens"]) if r["ctx_tokens"] else "—"
        ai_label    = r.get("ai", "CC")
        ai_color    = CYAN if ai_label == "CD" else BLUE

        lines.append(
            f"  {ai_color}{ai_label:<4}{RESET} {r['project']:<18} {r['session_id']:<10} {model_short:<18} "
            f"{ctx_display}   {tokens_str:>10} {r['turns']:>6} {guard_str:>6}   {status_str}"
        )

    lines.append("")
    return "\n".join(lines)


def _fetch_runs(cfg: dict) -> list[dict]:
    """Fetch recent runs from GET /runs."""
    server  = cfg.get("server", "").rstrip("/")
    api_key = cfg.get("api_key", "")
    ws_id   = cfg.get("workspace", "")
    if not all([server, api_key, ws_id]):
        return []
    try:
        hdrs = {"Content-Type": "application/json", "X-Api-Key": api_key}
        data = api.req("GET", f"{server}/runs?limit=15&workspace_id={ws_id}", hdrs)
        runs = data if isinstance(data, list) else data.get("runs", data.get("items", []))
        return runs[:15]
    except Exception:
        return []


def _fetch_guard_activity(cfg: dict, guard_cfg: dict) -> list[dict]:
    """Fetch recent Guard events grouped by developer."""
    server  = cfg.get("server", "").rstrip("/")
    api_key = cfg.get("api_key", "")
    ws_id   = cfg.get("workspace", "")
    if not all([server, api_key, ws_id]):
        return []
    try:
        hdrs = {"Content-Type": "application/json", "X-Api-Key": api_key}
        data = api.req("GET", f"{server}/guard/events?workspace_id={ws_id}&limit=200", hdrs)
        events = data if isinstance(data, list) else data.get("events", [])
        # Group by user_email
        devs: dict[str, dict] = {}
        for e in events:
            email   = e.get("user_email") or e.get("email") or "unknown"
            blocked = e.get("decision") == "block"
            tokens  = e.get("tokens_used") or e.get("tokens", 0) or 0
            if email not in devs:
                devs[email] = {"email": email, "calls": 0, "blocked": 0, "tokens": 0}
            devs[email]["calls"]   += 1
            devs[email]["blocked"] += int(blocked)
            devs[email]["tokens"]  += tokens
        return sorted(devs.values(), key=lambda d: d["calls"], reverse=True)
    except Exception:
        return []


def _render_tui(rows: list[dict]) -> None:
    """Full-screen TUI with live refresh. Uses rich.live if available, else ANSI loop."""

    cfg       = _load_config()
    def _build_rich_display(rows):
        from rich.table import Table
        from rich.panel import Panel
        from rich.columns import Columns
        from rich import box
        from rich.text import Text

        active   = sum(1 for r in rows if r["alive"])
        guard_on = sum(1 for r in rows if r["guard"])
        high_ctx = [r for r in rows if r["ctx_pct"] >= 60 and r["alive"]]

        # Main sessions table
        tbl = Table(box=box.ROUNDED, expand=True, show_header=True, header_style="bold white")
        tbl.add_column("AI",      width=4,  style="bold")
        tbl.add_column("Project", min_width=14)
        tbl.add_column("Session", width=10, style="dim")
        tbl.add_column("Model",   min_width=14)
        tbl.add_column("CTX",     width=16)
        tbl.add_column("Tokens",  width=10, justify="right")
        tbl.add_column("Turns",   width=6,  justify="right")
        tbl.add_column("Guard",   width=6,  justify="center")
        tbl.add_column("Status",  width=8)

        for r in rows:
            ai_text     = Text(r.get("ai", "CC"), style="bold cyan" if r.get("ai") == "CD" else "bold blue")
            status_text = Text("active", style="green") if r["alive"] else Text("idle", style="dim")
            guard_text  = Text("✓", style="green") if r["guard"] else Text("—", style="dim")
            model_short = r["model"].replace("claude-", "").replace("-20", " 20") if r["model"] not in ("—", "") else "—"

            pct = r["ctx_pct"]
            if pct:
                filled = round(pct / 100 * 10)
                bar    = "█" * filled + "░" * (10 - filled)
                color  = "red" if pct >= 80 else "yellow" if pct >= 60 else "green"
                ctx_text = Text(f"{bar} {pct}%", style=color)
            else:
                ctx_text = Text("—", style="dim")

            tbl.add_row(
                ai_text,
                r["project"],
                r["session_id"],
                model_short,
                ctx_text,
                _fmt_tokens(r["ctx_tokens"]) if r["ctx_tokens"] else "—",
                str(r["turns"]),
                guard_text,
                status_text,
            )

        # Summary header
        summary = f"[bold]{active}[/] active  ·  [bold]{guard_on}[/] with Guard  ·  [dim]refreshing every 5s — Ctrl+C to quit[/]"

        panels = [Panel(tbl, title="[bold blue]● My Sessions[/]", subtitle=summary, expand=True)]

        # Context pressure panel
        if high_ctx:
            warnings = "\n".join(
                f"[{'red' if r['ctx_pct'] >= 80 else 'yellow'}]{r['project']}[/]  "
                f"[dim]{r['session_id']}[/]  {r['ctx_pct']}% — consider /compact"
                for r in high_ctx
            )
            panels.append(Panel(warnings, title="[yellow bold]⚠ Context pressure[/]", expand=True))

        # Agent Runs panel
        run_data = _fetch_runs(cfg)
        runs_tbl = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold white")
        runs_tbl.add_column("Agent",      min_width=22)
        runs_tbl.add_column("Status",     width=12)
        runs_tbl.add_column("Duration",   width=10, justify="right")
        runs_tbl.add_column("Project",    min_width=14)
        runs_tbl.add_column("Triggered",  width=12)

        if run_data:
            for r in run_data:
                status  = r.get("status", "")
                scolor  = {"running": "green", "succeeded": "dim green", "failed": "red",
                           "paused": "yellow", "pending": "cyan", "cancelled": "dim"}.get(status, "white")
                sicon   = {"running": "●", "succeeded": "✓", "failed": "✗",
                           "paused": "⏸", "pending": "○", "cancelled": "—"}.get(status, "?")
                # Duration — timestamps may be ISO strings or unix floats
                import datetime as _dt
                def _to_ts(val):
                    if not val:
                        return None
                    if isinstance(val, (int, float)):
                        return float(val)
                    try:
                        return _dt.datetime.fromisoformat(str(val).replace("Z", "+00:00")).timestamp()
                    except Exception:
                        return None
                created_ts = _to_ts(r.get("created_at") or r.get("started_at"))
                ended_ts   = _to_ts(r.get("completed_at") or r.get("finished_at"))
                if created_ts and ended_ts:
                    secs = int(ended_ts - created_ts)
                    dur  = f"{secs//60}:{secs%60:02d}"
                elif created_ts and status == "running":
                    secs = int(time.time() - created_ts)
                    dur  = f"{secs//60}:{secs%60:02d}"
                else:
                    dur = "—"
                agent_name   = r.get("workflow_name") or r.get("name") or "—"
                project_name = r.get("project_name") or r.get("project") or "—"
                trigger      = r.get("trigger_type") or r.get("triggered_by") or "manual"
                runs_tbl.add_row(
                    agent_name[:28],
                    Text(f"{sicon} {status}", style=scolor),
                    dur,
                    project_name[:18],
                    trigger[:12],
                )
        else:
            runs_tbl.add_row("[dim]No runs yet or not connected[/]", "", "", "", "")

        panels.append(Panel(runs_tbl, title="[bold green]▶ Agent Runs[/]", expand=True))

        # Team Activity panel (Guard)
        team_data = _fetch_guard_activity(cfg, guard_cfg)
        team_tbl  = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold white")
        team_tbl.add_column("Developer",  min_width=28)
        team_tbl.add_column("Calls",      width=8,  justify="right")
        team_tbl.add_column("Blocked",    width=8,  justify="right")
        team_tbl.add_column("Tokens",     width=10, justify="right")
        team_tbl.add_column("Guard",      width=7,  justify="center")

        if team_data:
            for d in team_data:
                blocked_text = Text(str(d["blocked"]), style="red bold" if d["blocked"] else "dim")
                guard_text   = Text("✓", style="green")
                team_tbl.add_row(
                    d["email"][:32],
                    str(d["calls"]),
                    blocked_text,
                    _fmt_tokens(d["tokens"]),
                    guard_text,
                )
        else:
            team_tbl.add_row("[dim]No team activity or not connected[/]", "", "", "", "")

        panels.append(Panel(team_tbl, title="[bold magenta]👥 Team Activity (Guard)[/]", expand=True))

        from rich.console import Group
        return Group(*panels)

    # Try rich.live first (works without raw TTY)
    try:
        from rich.live import Live
        from rich.console import Console
        console = Console()
        with Live(console=console, refresh_per_second=0.2, screen=True) as live:
            while True:
                live.update(_build_rich_display(_load_sessions()))
                time.sleep(5)
        return
    except KeyboardInterrupt:
        return
    except ImportError:
        pass  # fall through to ANSI loop

    # ANSI fallback — requires real TTY
    if not sys.stdin.isatty():
        print(f"{YELLOW}TUI requires a real terminal. Run directly in your shell, not via a subprocess.{RESET}")
        print(_render_table(rows))
        return

    import shutil, signal, select, tty, termios
    stop = False
    def _sig(s, f): nonlocal stop; stop = True
    signal.signal(signal.SIGINT, _sig)

    def _frame(rows):
        cols, _ = shutil.get_terminal_size((120, 40))
        title = " conduct sessions  (Ctrl+C or q to quit) "
        pad   = max(0, cols - len(title))
        active   = sum(1 for r in rows if r["alive"])
        guard_on = sum(1 for r in rows if r["guard"])
        out = [
            f"{BOLD}\033[44m{title}{' ' * pad}\033[0m",
            f"\n  {BOLD}{active}{RESET} active  ·  {BOLD}{guard_on}{RESET} with Guard  ·  refreshing every 5s\n",
            _render_table(rows),
        ]
        high = [r for r in rows if r["ctx_pct"] >= 60 and r["alive"]]
        if high:
            out.append(f"  {YELLOW}{BOLD}⚠ Context pressure{RESET}")
            for r in high:
                c = RED if r["ctx_pct"] >= 80 else YELLOW
                out.append(f"    {c}{r['project']}{RESET} ({r['session_id']}) {r['ctx_pct']}% — consider /compact")
        sys.stdout.write("\033[2J\033[H" + "\n".join(out))
        sys.stdout.flush()

    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while not stop:
            _frame(_load_sessions())
            for _ in range(50):
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    if sys.stdin.read(1) in ("q", "Q"):
                        stop = True
                        break
                if stop:
                    break
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        sys.stdout.write("\033[2J\033[H")
        print("conduct sessions exited.")


def cmd_sessions(args):
    tui   = getattr(args, "tui", False)
    watch = getattr(args, "watch", False)

    if tui:
        _render_tui(_load_sessions())
        return

    if watch:
        try:
            import signal
            stop = False
            def _sig(s, f): nonlocal stop; stop = True
            signal.signal(signal.SIGINT, _sig)
            while not stop:
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()
                rows = _load_sessions()
                print(f"\n{BOLD}conduct sessions{RESET}  {GRAY}(Ctrl+C to stop · refreshing every 5s){RESET}")
                print(_render_table(rows))
                for _ in range(50):
                    time.sleep(0.1)
                    if stop: break
        except KeyboardInterrupt:
            pass
        return

    rows = _load_sessions()
    print(f"\n{BOLD}conduct sessions{RESET}")
    print(_render_table(rows))


# ── Security finding classifier ───────────────────────────────────────────────

import re as _re

_SEVERITY_KEYWORDS = {
    "critical": ["rce", "remote code execution", "sql injection", "sqli", "command injection"],
    "high": ["xss", "cross-site", "path traversal", "directory traversal", "auth bypass",
             "authentication bypass", "idor", "privilege escalation", "ssrf"],
    "medium": ["csrf", "open redirect", "clickjacking", "insecure deserialization", "xxe"],
    "low": ["information disclosure", "verbose error", "stack trace exposed", "version disclosure"],
    "info": ["todo security", "fixme security", "hardcoded", "weak cipher"],
}

_SECRET_PATTERNS = [
    r'(?i)(api[_-]?key|secret|password|token|private[_-]?key)\s*[:=]\s*["\']?[\w\-]{8,}',
    r'(?i)sk-[a-zA-Z0-9]{20,}',   # OpenAI key pattern
    r'(?i)ghp_[a-zA-Z0-9]{36}',   # GitHub PAT
]

_VULN_TYPES = {
    "injection": ["sql injection", "sqli", "command injection", "code injection", "ldap injection"],
    "path-traversal": ["path traversal", "directory traversal", "../"],
    "secret-leak": ["hardcoded", "secret", "api key", "password", "token", "private key"],
    "auth-bypass": ["auth bypass", "authentication bypass", "idor", "privilege escalation"],
    "crypto": ["weak cipher", "md5", "sha1", "tls 1.0", "ssl 2.0", "cert_none"],
}


def classify_finding(text: str) -> "dict | None":
    """
    Fast-path classifier. Returns structured finding dict or None if not a security issue.
    Checks secret patterns first (regex), then keyword severity matching.
    """
    text_lower = text.lower()

    # Secret detection (regex fast path)
    for pattern in _SECRET_PATTERNS:
        if _re.search(pattern, text):
            return {
                "severity": "high",
                "type": "secret-leak",
                "description": text[:500],
            }

    # Severity + type matching
    for severity, keywords in _SEVERITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                vuln_type = "other"
                for vtype, vkws in _VULN_TYPES.items():
                    if any(vk in text_lower for vk in vkws):
                        vuln_type = vtype
                        break
                return {
                    "severity": severity,
                    "type": vuln_type,
                    "description": text[:500],
                }
    return None


def cmd_session_report(args):
    """Run paxel analysis and open an HTML report in the local browser."""
    import json as _json
    import shutil
    import subprocess
    import tempfile
    import webbrowser
    import getpass

    # ── 1. Use bundled paxel ─────────────────────────────────────────────────
    bundled = Path(__file__).parent / "paxel.py"
    tmpdir = tempfile.mkdtemp(prefix="conduct-paxel-")
    paxel_script = Path(tmpdir) / "paxel.py"
    shutil.copy(bundled, paxel_script)

    # ── 2. Run paxel ─────────────────────────────────────────────────────────
    print("Analysing sessions…")
    try:
        result = subprocess.run(
            [sys.executable, str(paxel_script), "--no-open"],
            cwd=tmpdir, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("ERROR: analysis timed out after 120 s.")
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(1)

    stats_path = Path(tmpdir) / "stats.json"
    report_path = Path(tmpdir) / "report.md"

    if not stats_path.exists():
        print("ERROR: no transcripts found.")
        if result.stderr:
            print(result.stderr[:500])
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(1)

    with open(stats_path) as f:
        stats = _json.load(f)
    report_md = report_path.read_text() if report_path.exists() else ""

    # ── 3. Extract stats ─────────────────────────────────────────────────────
    developer    = getattr(args, "developer", None) or getpass.getuser()
    volume       = stats.get("volume", {})
    behavior     = stats.get("behavior", {})
    autonomy     = stats.get("autonomy", {})
    tools        = stats.get("tools", {})
    velocity     = stats.get("velocity", {})
    sessions     = volume.get("total_sessions", "?")
    prompts      = volume.get("total_prompts", "?")
    autonomy_score = autonomy.get("autonomy_score_0_100", "?")
    top_tools    = [t[0] for t in (tools.get("top_tools") or [])[:8]]
    commits      = velocity.get("git_commits_real", "?") if isinstance(velocity, dict) else "?"
    planning_ratio = behavior.get("planning_ratio_explore_to_doing", 0)

    if autonomy_score != "?" and float(autonomy_score) >= 70:
        archetype = "Autonomous Builder"
    elif planning_ratio != 0 and float(planning_ratio) > 1.0:
        archetype = "Strategic Planner"
    else:
        archetype = "Execution-Focused Builder"

    tools_str = "  ".join(f"<span class='tag'>{t}</span>" for t in top_tools)
    md_html = report_md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

    # ── 4. Generate HTML ─────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Session Report — {developer}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f0f11; color: #e2e2e8; min-height: 100vh; padding: 40px 24px; }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -.02em; margin-bottom: 4px; }}
  .sub {{ font-size: 14px; color: #888; margin-bottom: 32px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 14px; margin-bottom: 32px; }}
  .card {{ background: #1a1a1f; border: 1px solid #2a2a33; border-radius: 10px; padding: 18px 20px; }}
  .card .label {{ font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #666; margin-bottom: 8px; }}
  .card .value {{ font-size: 28px; font-weight: 700; color: #fff; letter-spacing: -.02em; }}
  .card .unit {{ font-size: 13px; color: #888; margin-top: 2px; }}
  .archetype {{ background: #1a1a1f; border: 1px solid #2a2a33; border-radius: 10px; padding: 20px 24px; margin-bottom: 32px; display: flex; align-items: center; gap: 16px; }}
  .archetype .badge {{ font-size: 13px; font-weight: 700; background: #7c3aed22; color: #a78bfa; border: 1px solid #7c3aed44; border-radius: 8px; padding: 6px 14px; white-space: nowrap; }}
  .archetype .desc {{ font-size: 13px; color: #aaa; }}
  .section {{ margin-bottom: 32px; }}
  .section h2 {{ font-size: 12px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #666; margin-bottom: 12px; }}
  .tag {{ display: inline-block; font-size: 12px; font-weight: 600; background: #1e1e28; border: 1px solid #2a2a3a; border-radius: 6px; padding: 4px 10px; margin: 3px; color: #a0aec0; }}
  .report {{ background: #1a1a1f; border: 1px solid #2a2a33; border-radius: 10px; padding: 20px 24px; font-size: 13px; color: #ccc; line-height: 1.7; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Session Report</h1>
  <div class="sub">{developer} · generated just now</div>

  <div class="archetype">
    <span class="badge">{archetype}</span>
    <span class="desc">Autonomy score {autonomy_score}/100 &nbsp;·&nbsp; Planning ratio {planning_ratio}</span>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Sessions</div><div class="value">{sessions}</div></div>
    <div class="card"><div class="label">Prompts</div><div class="value">{prompts}</div></div>
    <div class="card"><div class="label">Commits</div><div class="value">{commits}</div></div>
    <div class="card"><div class="label">Autonomy</div><div class="value">{autonomy_score}</div><div class="unit">/ 100</div></div>
  </div>

  <div class="section">
    <h2>Top Tools</h2>
    {tools_str if tools_str else "<span class='tag'>—</span>"}
  </div>

  <div class="section">
    <h2>Report</h2>
    <div class="report">{md_html or "No report generated."}</div>
  </div>
</div>
</body>
</html>"""

    html_path = Path(tmpdir) / "report.html"
    html_path.write_text(html)

    print(f"  Archetype  : {archetype}")
    print(f"  Autonomy   : {autonomy_score}/100   Sessions: {sessions}   Commits: {commits}")
    webbrowser.open(f"file://{html_path}")
    print("Opening report in browser…")

    # ── 5. Push report to Guard dashboard ────────────────────────────────────
    try:
        server, workspace_id, api_key, token = _require_auth(args)
        hdrs = api.headers(workspace_id, token, "application/json", api_key)
        import getpass as _getpass
        email = getattr(args, "developer", None) or _getpass.getuser()
        payload = _json.dumps({
            "developer_email": email,
            "archetype": archetype,
            "autonomy_score": float(autonomy_score) if autonomy_score != "?" else None,
            "planning_ratio": float(planning_ratio) if planning_ratio else None,
            "sessions": int(sessions) if sessions != "?" else 0,
            "prompts": int(prompts) if prompts != "?" else 0,
            "commits": int(commits) if commits != "?" else 0,
            "lines_per_hour": float(velocity.get("git_lines_per_active_hour", 0) or 0) if isinstance(velocity, dict) else None,
            "active_days": int(volume.get("active_days", 0) or 0),
            "tools_json": dict(tools.get("top_tools") or []),
            "report_md": report_md[:50000] if report_md else None,
        }).encode()
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            f"{server}/guard/session-reports",
            data=payload, headers=hdrs, method="POST",
        )
        __import__("urllib.request", fromlist=["urlopen"]).urlopen(req, timeout=10)
        print("✓ Report saved to Guard dashboard.")
    except Exception as _push_err:
        msg = str(_push_err)
        if "conduct login" in msg or "No server" in msg or "No workspace" in msg or "No credentials" in msg:
            print("  (Could not push to dashboard — run 'conduct login' to enable)")
        else:
            print(f"  (Dashboard push failed: {_push_err})")


def cmd_emit_finding(args):
    """POST a security finding to /security-findings."""
    server, workspace_id, api_key, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json", api_key)

    from_stdin = getattr(args, "from_stdin", False)

    if from_stdin:
        raw = sys.stdin.read()
        result = classify_finding(raw)
        if result is None:
            print("No security finding detected")
            sys.exit(0)
        severity    = result["severity"]
        vuln_type   = result["type"]
        description = result["description"]
    else:
        severity    = args.severity
        vuln_type   = args.type
        description = args.description

    payload: dict = {
        "severity":    severity,
        "type":        vuln_type,
        "description": description,
    }
    if getattr(args, "file", None):
        payload["file"] = args.file
    if getattr(args, "line", None) is not None:
        payload["line"] = args.line
    if getattr(args, "repo", None):
        payload["repo"] = args.repo

    result = api.req("POST", f"{server}/security-findings", hdrs, payload)
    finding_id = result.get("id", result.get("finding_id", ""))
    print(f"[FINDING] {severity} · {vuln_type} · {finding_id}")
    if finding_id:
        print(finding_id)


def _gh_api_get(url: str, token: str):
    import urllib.request, urllib.error
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _fetch_github_issue(repo: str, issue_number: int, token: str) -> dict:
    return _gh_api_get(f"https://api.github.com/repos/{repo}/issues/{issue_number}", token)


def _fetch_issues_by_label(repo: str, label: str, token: str) -> list:
    return _gh_api_get(
        f"https://api.github.com/repos/{repo}/issues?labels={label}&state=open&per_page=20",
        token,
    )


def _build_issue_trigger_payload(issue: dict, repo: str) -> dict:
    owner, repo_name = (repo.split("/", 1) + [""])[:2]
    return {
        "action": "labeled",
        "issue": {
            "number": issue["number"],
            "title": issue["title"],
            "body": issue.get("body") or "",
            "html_url": issue.get("html_url", ""),
            "user": issue.get("user") or {},
            "labels": issue.get("labels") or [],
        },
        "repository": {
            "full_name": repo,
            "name": repo_name,
            "owner": {"login": owner},
            "clone_url": f"https://github.com/{repo}.git",
            "default_branch": "main",
        },
    }


def _prompt_issue_choice(issues: list) -> dict:
    print(f"\n{BOLD}Multiple open issues found — choose one:{RESET}\n")
    for i, iss in enumerate(issues):
        print(f"  {BOLD}{i + 1}.{RESET} #{iss['number']} — {iss['title']}")
    print()
    while True:
        raw = input(f"Enter number [1–{len(issues)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(issues):
            return issues[int(raw) - 1]
        print(f"{RED}Invalid choice.{RESET}")


def cmd_run(args):
    server, workspace_id, api_key, token = _require_auth(args)
    json_h = api.headers(workspace_id, token, "application/json", api_key)

    # Fix 1: --input values go into state["inputs"], not top-level state.
    # {{inputs.key}} refs in YAML only resolve when the executor finds state["inputs"].
    run_inputs: dict = {}
    for kv in (args.input or []):
        if "=" not in kv:
            print(f"{RED}Bad --input format '{kv}' — expected key=value{RESET}")
            sys.exit(1)
        k, v = kv.split("=", 1)
        run_inputs[k] = v

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

    # Fix 4: determine trigger type from workflow metadata.
    is_github_webhook = bool(wf.get("github_webhook"))
    slug = wf.get("playbook_slug") or ""
    is_issue_trigger = is_github_webhook and "issue" in slug

    print(f"\n{BOLD}▶ conduct run — {wf['name']}{RESET}")
    if run_inputs:
        for k, v in run_inputs.items():
            print(f"  {GRAY}{k}={v}{RESET}")
    print()

    # Fix 2: preflight receives run_inputs so turn estimates use real input context.
    try:
        pf = api.req("POST", f"{server}/workflows/{workflow_id}/preflight", json_h, {
            "run_inputs": run_inputs,
        })
        suggested = pf.get("suggested_max_turns", 20)
        files = pf.get("total_files", [])
        print(f"  {BOLD}Estimated turns:{RESET} {suggested}")
        if files:
            print(f"  {BOLD}Files likely to be modified:{RESET} {', '.join(files)}")
        print()
    except Exception:
        suggested = 20

    # Fix 4: extract github_token before building body so it never lands in state["inputs"].
    import os as _os
    gh_token = run_inputs.pop("github_token", None) or _os.environ.get("GITHUB_TOKEN")

    # Build the trigger body.
    # Fix 1: send inputs under "inputs" key so server puts them in state["inputs"].
    body: dict = {}
    if run_inputs:
        body["inputs"] = run_inputs

    # Fix 4: non-webhook triggers (manual/schedule) — flag so server skips trigger validation.
    if not is_github_webhook:
        body["__manual"] = True

    # Fix 4: github_issue_labeled — fire against a real issue when possible.
    if is_issue_trigger:
        repo = wf.get("github_hook_repo") or run_inputs.get("repo")
        label = wf.get("github_hook_label") or ""
        issue_number_raw = run_inputs.get("issue_number")
        if gh_token and repo:
            try:
                if issue_number_raw:
                    issue = _fetch_github_issue(repo, int(issue_number_raw), gh_token)
                    body.update(_build_issue_trigger_payload(issue, repo))
                    print(f"  {GRAY}issue: #{issue['number']} — {issue['title']}{RESET}\n")
                elif label:
                    issues = _fetch_issues_by_label(repo, label, gh_token)
                    if not issues:
                        print(f"{YELLOW}⚠ No open issues with label '{label}' in {repo}. Using test payload.{RESET}\n")
                    elif len(issues) == 1:
                        body.update(_build_issue_trigger_payload(issues[0], repo))
                        print(f"  {GRAY}issue: #{issues[0]['number']} — {issues[0]['title']}{RESET}\n")
                    else:
                        chosen = _prompt_issue_choice(issues)
                        body.update(_build_issue_trigger_payload(chosen, repo))
                        print(f"  {GRAY}issue: #{chosen['number']} — {chosen['title']}{RESET}\n")
            except Exception as _gh_err:
                print(f"{YELLOW}⚠ GitHub fetch failed ({_gh_err}). Using test payload.{RESET}\n")
        else:
            hint = "export GITHUB_TOKEN=<token>" if not gh_token else "workflow has no github_hook_repo"
            print(f"  {GRAY}No GitHub token — using test payload. ({hint}){RESET}\n")

    # #734: validate required inputs locally before POST — fail fast with clear error.
    try:
        vres = api.req("POST", f"{server}/workflows/{workflow_id}/validate-inputs", json_h,
                       {"inputs": body.get("inputs") or {}, "phase": "run"})
        missing = (vres or {}).get("missing") or []
        if missing:
            print(f"{RED}✗ Missing required inputs:{RESET}")
            for m in missing:
                print(f"  - {m['label']} ({m['key']})")
            print(f"\n{GRAY}Provide with --input {missing[0]['key']}=<value>{RESET}")
            sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        pass  # validate endpoint is best-effort; backend will re-check on /trigger

    # Full preflight validation — credentials, auth chain, proxy, block config.
    # Blocks on errors so bad runs never start.
    try:
        vr = api.req("POST", f"{server}/workflows/{workflow_id}/validate", json_h, {})
        v_errors = (vr or {}).get("errors") or []
        if v_errors:
            print(f"{RED}✗ Cannot start run — preflight validation failed:{RESET}\n")
            for e in v_errors:
                lbl = e.get("label") or e.get("block_id") or "?"
                print(f"  {YELLOW}⚠  [{lbl}]{RESET} {e.get('message', '')}")
            print()
            sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        pass  # best-effort — don't block run if validate endpoint itself errors

    # Fix 3: /trigger returns run_id, not id.
    if getattr(args, "max_turns", None):
        body["__max_turns"] = args.max_turns
    elif suggested > 20:
        body["__max_turns"] = suggested
    run = api.req("POST", f"{server}/workflows/{workflow_id}/trigger", json_h, body)
    run_id = run.get("run_id") or run.get("id")
    _stream_run(server, workflow_id, run_id, workspace_id, token, api_key)


# ── conduct sync / test-guard / test-security ────────────────────────────────

def _refresh_agent_token() -> bool:
    """Silently rotate agent_token using refresh_token. Returns True if refreshed."""
    cfg = _load_config()
    refresh_token = cfg.get("refresh_token", "")
    if not refresh_token:
        return False
    api_url = cfg.get("api_url", _DEFAULT_API_URL).rstrip("/")
    try:
        import json as _json
        req = urllib.request.Request(
            f"{api_url}/auth/refresh",
            data=_json.dumps({"refresh_token": refresh_token}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        import datetime as _dt
        cfg["agent_token"]      = data["agent_token"]
        cfg["refresh_token"]    = data["refresh_token"]
        cfg["workspace"]        = data["workspace_id"]
        cfg["workspace_id"]     = data["workspace_id"]
        cfg["token_expires_at"] = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=8)).isoformat()
        _atomic_write(CONFIG_PATH, cfg)
        return True
    except Exception:
        return False


def cmd_sync(args):
    """Sync Guard policies (and Security Loop policies if installed)."""
    import conduct_cli.guard as _g
    # Proactive refresh if token expires within 5 min
    cfg = _load_config()
    if cfg.get("refresh_token"):
        import datetime as _dt
        exp = cfg.get("token_expires_at", "")
        try:
            if not exp or _dt.datetime.fromisoformat(exp) < _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=5):
                _refresh_agent_token()
        except ValueError:
            pass
    print(f"\n{BOLD}▶ conduct sync{RESET}\n")
    _g.cmd_guard_sync(args)
    print(f"\n{GREEN}Sync complete.{RESET}\n")


_SECURITY_TEST_CASES = [
    # (name, type, severity, description, file, line)
    ("AWS Access Key",       "secret-leak",     "critical", "AKIA1234567890ABCDEF found in output",                    "test_vuln.py",  7),
    ("OpenAI API Key",       "secret-leak",     "high",     "sk-abcdefghijklmnopqrstuvwx1234567890 in response",       "test_vuln.py",  8),
    ("GitHub PAT",           "secret-leak",     "high",     "ghp_" + "A" * 36 + " token present",                     "test_vuln.py",  8),
    ("Bearer Token",         "secret-leak",     "high",     "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test.sig",     "test_vuln.py",  None),
    ("Hardcoded Password",   "secret-leak",     "high",     "password = 'hardcoded_secret_here'",                      "test_vuln.py",  11),
    ("Hardcoded API Key",    "secret-leak",     "high",     "api_key = 'abc123def456ghi789'",                          "test_vuln.py",  12),
    ("Path Traversal",       "path-traversal",  "medium",   "../../etc/passwd accessed",                               "test_vuln.py",  32),
    ("File URI",             "path-traversal",  "medium",   "file:///etc/passwd read",                                 "test_vuln.py",  None),
    ("eval() Injection",     "injection",       "high",     "eval(user_input) called in output",                       "test_vuln.py",  16),
    ("exec() Injection",     "injection",       "high",     "exec(command) called in output",                          "test_vuln.py",  20),
    ("SSL Disabled",         "crypto",          "high",     "ssl.CERT_NONE used — verification disabled",              "test_vuln.py",  28),
    ("TLS Bypass",           "crypto",          "medium",   "verify=False passed to requests",                         "test_vuln.py",  23),
    ("SQL Injection",        "injection",       "high",     "sql injection vulnerability in query",                    "test_vuln.py",  None),
    ("XSS",                  "injection",       "high",     "cross-site scripting detected in output",                 "test_vuln.py",  None),
    ("Auth Bypass",          "auth-bypass",     "high",     "auth bypass possible via missing check",                  "test_vuln.py",  None),
]


def cmd_test_security(args):
    """Fire synthetic security findings for every classifier pattern."""
    from conduct_cli.guard import CONFIG_PATH
    try:
        import json as _json
        cfg = _json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        cfg = {}

    workspace_id = cfg.get("workspace_id")
    api_key      = cfg.get("api_key", "")
    user_email   = cfg.get("user_email", "")
    api_url      = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")

    if not workspace_id:
        print(f"{RED}Not configured. Run: conduct guard setup{RESET}")
        sys.exit(1)

    import urllib.request
    import json as _json

    print(f"\n{BOLD}▶ conduct test-security — {len(_SECURITY_TEST_CASES)} patterns{RESET}\n")

    # Clean up previous test run findings before inserting fresh ones
    try:
        req = urllib.request.Request(
            f"{api_url}/security-findings?workspace_id={workspace_id}&source_run_id=conduct-test-security",
            headers={"X-Api-Key": api_key},
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            r = _json.loads(resp.read())
            n = r.get("deleted", 0)
            if n:
                print(f"  {GRAY}↺ Cleaned {n} previous test finding{'s' if n != 1 else ''}{RESET}\n")
    except Exception:
        pass  # cleanup is best-effort

    passed = 0
    failed = 0
    for name, vtype, severity, description, test_file, test_line in _SECURITY_TEST_CASES:
        body: dict = {
            "tool": "claude-code",
            "severity": severity,
            "type": vtype,
            "description": f"[TEST] {description}",
            "reporter_email": user_email,
            "source_run_id": "conduct-test-security",
        }
        if test_file:
            body["file"] = test_file
        if test_line is not None:
            body["line"] = test_line
        payload = _json.dumps(body).encode()
        try:
            req = urllib.request.Request(
                f"{api_url}/security-findings?workspace_id={workspace_id}",
                data=payload,
                headers={"Content-Type": "application/json", "X-Api-Key": api_key},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                r = _json.loads(resp.read())
                fid = r.get("id", "")[:8]
                sev_color = RED if severity == "critical" else (YELLOW if severity == "high" else CYAN)
                print(f"  {GREEN}✓{RESET}  {name:<22} {sev_color}{severity:<8}{RESET}  {GRAY}{fid}{RESET}")
                passed += 1
        except Exception as e:
            print(f"  {RED}✕{RESET}  {name:<22} {RED}FAILED — {e}{RESET}")
            failed += 1

    print(f"\n  {passed} posted · {failed} failed")
    print(f"\n  {CYAN}→ View findings: {api_url.replace('api.', 'app.')}/secure/activity{RESET}\n")


def cmd_test_security_verify(args):
    """Post test findings and verify the full triage pipeline end-to-end."""
    from conduct_cli.guard import CONFIG_PATH
    import json as _json
    import time as _time

    try:
        cfg = _json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        cfg = {}

    workspace_id = cfg.get("workspace_id")
    api_key      = cfg.get("api_key", "")
    user_email   = cfg.get("user_email", "")
    api_url      = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")

    if not workspace_id:
        print(f"{RED}Not configured. Run: conduct guard setup{RESET}")
        sys.exit(1)

    import urllib.request

    TIMEOUT   = 300  # 15 runs × ~28s / 4 workers ≈ 105s; 300s gives headroom for queue variance
    POLL_SECS = 5

    # ── Step 0: fresh Security Automation project ─────────────────────────
    print(f"\n{BOLD}▶ conduct test-security-verify{RESET}")
    print(f"  {GRAY}Step 0/3 — refreshing Security Automation project…{RESET}")
    try:
        req = urllib.request.Request(
            f"{api_url}/secure/refresh-automation?workspace_id={workspace_id}",
            data=b"{}",
            headers={"Content-Type": "application/json", "X-Api-Key": api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            _json.loads(resp.read())
            print(f"  {GREEN}✓{RESET}  Fresh project created with latest YAML\n")
    except Exception as e:
        print(f"  {YELLOW}⚠ refresh failed ({e}) — using existing project{RESET}\n")

    # ── Step 1: post test findings ────────────────────────────────────────
    print(f"  {GRAY}Step 1/3 — posting {len(_SECURITY_TEST_CASES)} test findings…{RESET}\n")

    # Clean previous run
    try:
        req = urllib.request.Request(
            f"{api_url}/security-findings?workspace_id={workspace_id}&source_run_id=conduct-test-security",
            headers={"X-Api-Key": api_key},
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            r = _json.loads(resp.read())
            n = r.get("deleted", 0)
            if n:
                print(f"  {GRAY}↺ Cleaned {n} previous test finding{'s' if n != 1 else ''}{RESET}\n")
    except Exception:
        pass

    finding_ids: list[str] = []
    for name, vtype, severity, description, test_file, test_line in _SECURITY_TEST_CASES:
        body: dict = {
            "tool": "claude-code",
            "severity": severity,
            "type": vtype,
            "description": f"[TEST] {description}",
            "reporter_email": user_email,
            "source_run_id": "conduct-test-security",
        }
        if test_file:
            body["file"] = test_file
        if test_line is not None:
            body["line"] = test_line
        payload = _json.dumps(body).encode()
        try:
            req = urllib.request.Request(
                f"{api_url}/security-findings?workspace_id={workspace_id}",
                data=payload,
                headers={"Content-Type": "application/json", "X-Api-Key": api_key},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                r = _json.loads(resp.read())
                fid = r.get("id", "")
                finding_ids.append(fid)
                sev_color = RED if severity == "critical" else (YELLOW if severity == "high" else CYAN)
                print(f"  {GREEN}✓{RESET}  {name:<22} {sev_color}{severity:<8}{RESET}  {GRAY}{fid[:8]}{RESET}")
        except Exception as e:
            print(f"  {RED}✕{RESET}  {name:<22} {RED}FAILED — {e}{RESET}")

    if not finding_ids:
        print(f"\n{RED}✗ No findings posted — aborting.{RESET}\n")
        sys.exit(1)

    # ── Step 2: poll until all findings move off "open" ───────────────────
    print(f"\n  {GRAY}Step 2/3 — waiting for triage pipeline (timeout {TIMEOUT}s)…{RESET}\n")

    deadline = _time.time() + TIMEOUT
    final_statuses: dict[str, str] = {}

    while _time.time() < deadline:
        try:
            req = urllib.request.Request(
                f"{api_url}/security-findings?workspace_id={workspace_id}&source_run_id=conduct-test-security&limit=100",
                headers={"X-Api-Key": api_key},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                findings = _json.loads(resp.read())
        except Exception as e:
            print(f"  {YELLOW}⚠ poll error: {e}{RESET}")
            _time.sleep(POLL_SECS)
            continue

        for f in findings:
            if f["id"] in finding_ids:
                final_statuses[f["id"]] = f["status"]

        still_open = [fid for fid in finding_ids if final_statuses.get(fid) == "open"]
        done_count = len(finding_ids) - len(still_open)
        elapsed = int(_time.time() - (deadline - TIMEOUT))
        print(f"  {GRAY}[{elapsed:>3}s] {done_count}/{len(finding_ids)} processed…{RESET}", end="\r")

        if not still_open:
            print()  # newline after \r
            break
        _time.sleep(POLL_SECS)
    else:
        print(f"\n\n  {RED}✗ Timeout — {len(still_open)} finding(s) still 'open' after {TIMEOUT}s{RESET}\n")

    # ── Step 3: report per-finding results ────────────────────────────────
    print(f"\n  {GRAY}Step 3/3 — results{RESET}\n")


    all_pass = True
    name_by_id = {}
    for i, (name, *_) in enumerate(_SECURITY_TEST_CASES):
        if i < len(finding_ids):
            name_by_id[finding_ids[i]] = name

    for fid in finding_ids:
        status = final_statuses.get(fid, "open")
        name   = name_by_id.get(fid, fid[:8])
        if status == "open":
            icon = f"{RED}✗{RESET}"
            note = f"{RED}still open — triage did not run{RESET}"
            all_pass = False
        elif status == "dismissed":
            icon = f"{CYAN}○{RESET}"
            note = f"{CYAN}dismissed (false positive){RESET}"
        elif status == "triaging":
            icon = f"{YELLOW}◑{RESET}"
            note = f"{YELLOW}triaging (real finding, no autopilot fix){RESET}"
        elif status == "fixed":
            icon = f"{GREEN}✓{RESET}"
            note = f"{GREEN}fixed{RESET}"
        else:
            icon = f"{GRAY}?{RESET}"
            note = f"{GRAY}{status}{RESET}"
        print(f"  {icon}  {name:<22} → {note}")

    print()
    if all_pass:
        print(f"  {GREEN}{BOLD}✓ All findings processed — triage pipeline OK{RESET}\n")
    else:
        print(f"  {RED}{BOLD}✗ Some findings were not processed — check Security Automation project runs{RESET}")
        app_url = api_url.replace("api.", "app.")
        print(f"  {CYAN}→ {app_url}/projects{RESET}\n")
        sys.exit(1)


def cmd_test_guard(args):
    """Test each guard policy rule with a matching synthetic tool call."""
    import json as _json
    import re as _re
    from conduct_cli.guard import _load_guard_config, _load_policy, active_policy_path

    cfg = _load_guard_config()
    pol_path = active_policy_path()  # workspace-scoped

    if not pol_path.exists():
        print(f"{RED}No policy file found. Run: conduct guard sync{RESET}")
        sys.exit(1)

    try:
        policy = _load_policy()
    except Exception as e:
        print(f"{RED}Could not load policy: {e}{RESET}")
        sys.exit(1)

    rules = policy.get("rules", [])
    if not rules:
        print(f"{YELLOW}No rules in local policy. Run: conduct guard sync{RESET}")
        sys.exit(0)

    workspace_id = cfg.get("workspace_id")
    api_key      = cfg.get("api_key", "")
    api_url      = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")

    print(f"\n{BOLD}▶ conduct test-guard — {len(rules)} rule(s){RESET}\n")

    import urllib.request

    blocked = 0
    allowed = 0
    errors  = 0
    for rule in rules:
        rule_id  = rule.get("rule_id", "unknown")
        action   = rule.get("action", "audit")
        message  = rule.get("message") or rule_id
        tool     = (rule.get("match_tool") or "bash").split(",")[0].strip()
        pattern  = rule.get("match_pattern") or rule.get("match_path_pattern") or ""

        # Build a synthetic input that satisfies the rule's pattern
        if pattern:
            try:
                # Use the pattern itself as a test input fragment where possible
                test_input = _re.sub(r"[\\^$.*+?()\[\]{}|]", "", pattern)[:80] or rule_id
            except Exception:
                test_input = rule_id
        else:
            test_input = rule_id

        payload = _json.dumps({
            "ai_tool": "claude-code",
            "tool_call": tool,
            "input_summary": f"[TEST] {test_input}",
            "decision": action if action in ("blocked", "warn") else "blocked",
            "rule_id": rule_id,
            "rule_message": f"[TEST] {message}",
        }).encode()

        action_color = RED if action == "blocked" else (YELLOW if action == "warn" else CYAN)
        action_label = action.upper()

        if workspace_id:
            try:
                req = urllib.request.Request(
                    f"{api_url}/guard/events/test?workspace_id={workspace_id}",
                    data=payload,
                    headers={"Content-Type": "application/json", "X-Api-Key": api_key},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5):
                    pass
                posted = f"{GRAY}posted{RESET}"
            except Exception:
                posted = f"{GRAY}local only{RESET}"
        else:
            posted = f"{GRAY}no workspace{RESET}"

        print(f"  {action_color}{action_label:<8}{RESET}  {rule_id:<35}  {GRAY}{message[:50]}{RESET}  {posted}")
        if action == "blocked":
            blocked += 1
        else:
            allowed += 1

    print(f"\n  {blocked} would block · {allowed} audit/allow")
    print(f"\n  {CYAN}→ View events: {api_url.replace('api.', 'app.')}/guard/activity{RESET}\n")


def cmd_memory(args):
    from conduct_cli.memory import search_team_memory
    memory_command = getattr(args, "memory_command", None)
    if memory_command == "search":
        query = " ".join(args.query)
        results = search_team_memory(query, repo=getattr(args, "repo", None), limit=args.limit)
        if not results:
            print("No team memories found.")
            return
        for r in results:
            dev = r.get("developer_id") or "unknown"
            repo = r.get("repo_full_name") or ""
            summary = r.get("summary", "")
            tags = ", ".join(r.get("topic_tags") or [])
            created = r.get("created_at", "")[:10]
            heading = f"{dev}  {GRAY}{repo}{RESET}" if repo else dev
            print(f"\n{BOLD}{heading}{RESET}  {GRAY}{created}{RESET}")
            if tags:
                print(f"  Tags: {tags}")
            print(f"  {summary}")
    else:
        print("Usage: conduct memory search <query>")


# ── Entry point ───────────────────────────────────────────────────────────────

_GUARD_CONFIG = Path.home() / ".conduct" / "config.json"
_GUARD_SKIP   = Path.home() / ".conduct" / ".setup_skip"

GREEN  = "\033[32m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def _check_guard_setup(command: str) -> None:
    """On first run after install, prompt user to run conduct guard sync."""
    # Skip if: already set up, user said skip, or running guard sync/login itself
    if command in ("guard", "login", "whoami", "version"):
        return
    if _GUARD_CONFIG.exists() or _GUARD_SKIP.exists():
        return
    print(
        f"\n{YELLOW}{BOLD}⚡ Conduct Guard is not set up on this machine.{RESET}\n"
        f"   Run {BOLD}conduct guard sync{RESET} to register policy hooks and MCP servers.\n"
        f"   (This takes ~5 seconds and only needs to happen once per machine.)\n"
        f"   To skip this reminder: {BOLD}conduct guard skip-setup{RESET}\n"
    )



def cmd_skill(args):
    """conduct skill list | install <slug> | uninstall <slug>"""
    skill_command = getattr(args, "skill_command", None)
    server, workspace, api_key, token = _require_auth(args)

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    elif token:
        headers["Authorization"] = f"Bearer {token}"

    def _req(method, path, expect=None):
        url = f"{server}{path}"
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            return data
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get("detail", body)
            except Exception:
                msg = body
            print(f"{RED}Error {e.code}: {msg}{RESET}")
            sys.exit(1)

    if skill_command == "list":
        data = _req("GET", f"/compliance/packs/available?workspace_id={workspace}")
        installed_data = _req("GET", f"/compliance/packs/installed?workspace_id={workspace}")
        installed = set(installed_data.get("installed", []))

        packs = data.get("packs", [])
        if not packs:
            print("No skill packs available.")
            return

        print(f"\n{'Slug':<20} {'Name':<22} {'Tier':<8} {'Rules':<7} Status")
        print("─" * 70)
        for p in packs:
            slug   = p.get("slug", "")
            name   = p.get("name", "")
            tier   = p.get("tier", "")
            rules  = len(p.get("rules", []))
            status = f"{GREEN}installed{RESET}" if slug in installed else f"{GRAY}available{RESET}"
            print(f"{slug:<20} {name:<22} {tier:<8} {rules:<7} {status}")
        print()

    elif skill_command == "install":
        slug = getattr(args, "slug", None)
        if not slug:
            print(f"{RED}Usage: conduct skill install <slug>{RESET}")
            sys.exit(1)
        _req("POST", f"/compliance/packs/{slug}/install?workspace_id={workspace}")
        print(f"{GREEN}✓{RESET} Installed {BOLD}{slug}{RESET}")
        print(f"  Run {BOLD}conduct guard sync{RESET} to push the updated policy to your hook.")

    elif skill_command == "uninstall":
        slug = getattr(args, "slug", None)
        if not slug:
            print(f"{RED}Usage: conduct skill uninstall <slug>{RESET}")
            sys.exit(1)
        _req("DELETE", f"/compliance/packs/{slug}/uninstall?workspace_id={workspace}")
        print(f"{GREEN}✓{RESET} Uninstalled {BOLD}{slug}{RESET}")
        print(f"  Run {BOLD}conduct guard sync{RESET} to push the updated policy to your hook.")

    else:
        print("Usage: conduct skill <list|install|uninstall> [slug]")


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
    login_p = sub.add_parser("login", help="Authenticate with Conduct (opens browser)")
    login_p.add_argument("--server", help="API base URL (default: https://api.conductai.ai)")
    login_p.add_argument("--token",  help="Paste an agent token directly instead of opening a browser")

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

    # conduct emit finding
    emit_p = sub.add_parser("emit", help="Emit events to Conduct (e.g. security findings)")
    emit_sub = emit_p.add_subparsers(dest="emit_command")

    finding_p = emit_sub.add_parser("finding", help="Emit a security finding to POST /security-findings")
    finding_p.add_argument("--severity",    choices=["critical", "high", "medium", "low", "info"],
                           help="Finding severity")
    finding_p.add_argument("--type",        dest="type",        metavar="TYPE",
                           help="Vulnerability type (e.g. secret-leak, injection, path-traversal)")
    finding_p.add_argument("--file",        metavar="PATH",     help="Source file path where finding was detected")
    finding_p.add_argument("--line",        type=int,           metavar="N",    help="Line number of finding")
    finding_p.add_argument("--description", metavar="TEXT",     help="Human-readable description of the finding")
    finding_p.add_argument("--repo",        metavar="owner/repo", help="Repository where finding was detected")
    finding_p.add_argument("--from-stdin",  dest="from_stdin",  action="store_true",
                           help="Read raw tool output from stdin and auto-classify the finding")

    # conduct run (existing)
    run_p = sub.add_parser("run", help="Run an installed agent by name")
    run_p.add_argument("agent",       help="Agent name (e.g. 'security_autopilot_fix')")
    run_p.add_argument("--project",   metavar="name",  help="Narrow to a specific project")
    run_p.add_argument("--input",     action="append", metavar="key=value", help="Runtime input (repeatable)")
    run_p.add_argument("--max-turns", dest="max_turns", type=int, metavar="N", help="Max agentic turns (default: auto)")

    # conduct switch [workspace]
    switch_p = sub.add_parser("switch", help="Switch active workspace (or list workspaces)")
    switch_p.add_argument("workspace", nargs="?", metavar="name_or_id",
                          help="Workspace name or UUID prefix to switch to (omit to list)")

    # conduct token show
    sub.add_parser("token", help="Show your agent token (masked by default)")

    # conduct whoami
    sub.add_parser("whoami", help="Show current workspace, server, API key, and Guard/Booster status")

    # conduct guard
    guard_p, _guard_sub = _guard.register_guard_parser(sub)

    # conduct mcp
    sessions_p = sub.add_parser("sessions", help="Show active Claude Code / Codex sessions")
    sessions_p.add_argument("--watch", action="store_true", help="Refresh every 5s (table view)")
    sessions_p.add_argument("--tui",   action="store_true", help="Full-screen TUI with live panels")

    mcp_p = sub.add_parser("mcp", help="Manage the Conduct MCP server")
    mcp_sub = mcp_p.add_subparsers(dest="mcp_command")
    mcp_sub.add_parser("install", help="Register conduct-mcp in Claude Code and Codex")

    # conduct skill
    skill_p = sub.add_parser("skill", help="Manage Guard skill packs")
    skill_sub = skill_p.add_subparsers(dest="skill_command")
    skill_sub.add_parser("list", help="List available and installed skill packs")
    skill_install_p = skill_sub.add_parser("install", help="Install a skill pack")
    skill_install_p.add_argument("slug", help="Pack slug, e.g. conduct-owasp")
    skill_uninstall_p = skill_sub.add_parser("uninstall", help="Uninstall a skill pack")
    skill_uninstall_p.add_argument("slug", help="Pack slug, e.g. conduct-owasp")

    # conduct sync
    sub.add_parser("sync", help="Sync Guard policies (and Security Loop policies if installed)")

    # conduct test-guard / test-security / test-security-verify
    verify_p = sub.add_parser("verify", help="OWASP Agentic Top 10 coverage + governance grade")
    verify_p.add_argument("--evidence",  metavar="FILE", default=None, help="Write evidence artifact to FILE.")
    verify_p.add_argument("--badge",     action="store_true",          help="Print markdown badge and exit.")
    verify_p.add_argument("--min-grade", metavar="GRADE", default=None,help="Exit 1 if governance grade is below this (A–F).")
    verify_p.add_argument("--strict",    action="store_true",          help="Exit 1 if any blocked events in last 24h (CI mode).")
    verify_p.add_argument("--format",    choices=["text", "json"],     default="text", help="Output format (default: text)")
    verify_p.add_argument("--since",     default="24h",                help="Time window for blocked event check (e.g. 7d, 24h)")
    sub.add_parser("test-guard",            help="Fire a synthetic event per guard policy rule and show decisions")
    sub.add_parser("test-security",         help="Post a synthetic finding per security classifier pattern")
    sub.add_parser("test-security-verify",  help="Post test findings and verify full triage pipeline end-to-end")
    sr_p = sub.add_parser("session-report", help="Analyse local AI coding sessions with paxel and send report to admin")
    sr_p.add_argument("--developer", default=None, help="Developer name (defaults to OS username)")

    # conduct memory
    memory_p = sub.add_parser("memory", help="Search team session memories")
    memory_sub = memory_p.add_subparsers(dest="memory_command")
    mem_search_p = memory_sub.add_parser("search", help="Search team memories")
    mem_search_p.add_argument("query", nargs="+", help="Search query")
    mem_search_p.add_argument("--repo", help="Filter by repo (owner/repo)")
    mem_search_p.add_argument("--limit", type=int, default=5, help="Max results")

    args = parser.parse_args()

    _check_guard_setup(args.command or "")

    if args.command == "guard" and getattr(args, "guard_command", None) == "skip-setup":
        _GUARD_SKIP.parent.mkdir(parents=True, exist_ok=True)
        _GUARD_SKIP.touch()
        print(f"{GREEN}✓ Setup reminder suppressed.{RESET} Run `conduct guard sync` anytime to enable Guard.")
        return

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
    elif args.command == "switch":
        cmd_switch(args)
    elif args.command == "token":
        cfg = _load_config()
        token = cfg.get("agent_token", "")
        if not token:
            print(f"{RED}No agent token found. Run: conduct login{RESET}")
            sys.exit(1)
        print(f"\n{BOLD}Agent token{RESET} (paste as Bearer value in MCP server auth):\n")
        print(f"  {CYAN}Bearer {token}{RESET}\n")
        print(f"{GRAY}Token expires: {cfg.get('token_expires_at', 'unknown')}{RESET}")
        print(f"{GRAY}Workspace:     {cfg.get('workspace_id', '')}{RESET}\n")
    elif args.command == "whoami":
        cmd_whoami(args)
    elif args.command == "sessions":
        cmd_sessions(args)
    elif args.command == "guard":
        _guard.dispatch_guard(args, guard_p)
    elif args.command == "emit":
        emit_command = getattr(args, "emit_command", None)
        if emit_command == "finding":
            from_stdin = getattr(args, "from_stdin", False)
            if not from_stdin and not (args.severity and args.type and args.description):
                finding_p.print_help()
                sys.exit(1)
            cmd_emit_finding(args)
        else:
            emit_p.print_help()
    elif args.command == "mcp":
        if getattr(args, "mcp_command", None) == "install":
            cmd_mcp_install(args)
        else:
            mcp_p.print_help()
    elif args.command == "skill":
        cmd_skill(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "verify":
        _guard.cmd_verify(args)
    elif args.command == "test-guard":
        cmd_test_guard(args)
    elif args.command == "test-security":
        cmd_test_security(args)
    elif args.command == "test-security-verify":
        cmd_test_security_verify(args)
    elif args.command == "session-report":
        cmd_session_report(args)
    elif args.command == "memory":
        cmd_memory(args)
    else:
        parser.print_help()


# ponytail: telemetry error interceptor (#718)
from .log_util import install_error_interceptor as _ei
main = _ei(main)

if __name__ == "__main__":
    main()
