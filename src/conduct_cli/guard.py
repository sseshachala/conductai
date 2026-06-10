"""conduct guard — team policy + MCP registration subcommand."""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
RED    = "\033[31m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"

GUARD_DIR    = Path.home() / ".conductguard"
CONFIG_PATH  = GUARD_DIR / "config.json"
POLICY_PATH  = GUARD_DIR / "policy.json"

# ── Hook templates — loaded from real .py files (no string embedding) ─────────
_TEMPLATES_DIR = Path(__file__).parent

def _read_template(name: str) -> str:
    return (_TEMPLATES_DIR / name).read_text()




# ── Policy engine (also embedded in hook_template.py for standalone use) ──────

import json as _json
import re as _re

def _check_policy(tool_name, tool_input, tokens_before=0):
    """Return (matched_rule, action, rule_id, message) or (None, 'allow', None, None)."""
    if not POLICY_PATH.exists():
        return None, "allow", None, None
    try:
        policy = _json.loads(POLICY_PATH.read_text())
    except Exception:
        return None, "allow", None, None

    rules      = policy.get("rules", [])
    input_text = _json.dumps(tool_input)
    path_fields = [str(tool_input.get(f, "")) for f in ["file_path", "path", "command"]]

    for rule in rules:
        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            if tool_name not in [t.strip() for t in match_tool.split(",")]:
                continue
        pattern = rule.get("match_pattern")
        if pattern:
            try:
                if not _re.search(pattern, input_text, _re.IGNORECASE):
                    continue
            except _re.error:
                continue
        path_pattern = rule.get("match_path_pattern")
        if path_pattern:
            try:
                if not any(_re.search(path_pattern, f, _re.IGNORECASE) for f in path_fields if f):
                    continue
            except _re.error:
                continue
        min_tokens = rule.get("match_tokens_before_gt")
        if min_tokens is not None:
            if tokens_before <= int(min_tokens):
                continue
        action  = rule.get("action", "audit")
        rule_id = rule.get("rule_id", "unknown")
        message = rule.get("message") or f"Policy violation: {rule_id}"
        return rule, action, rule_id, message

    return None, "allow", None, None


# ── Python interpreter selection ─────────────────────────────────────────────

def _best_python() -> str:
    """Return the best available Python 3 interpreter path.
    Prefers 3.11+ (Homebrew) over Apple's system Python 3.9 which has
    restrictions that cause the hook to fail silently."""
    import shutil
    for candidate in ("python3.13", "python3.12", "python3.11", "python3.10"):
        found = shutil.which(candidate)
        if found:
            return found
    return sys.executable


# ── Hook write helper ─────────────────────────────────────────────────────────

def _write_hook(path: Path) -> None:
    """Write hook_template.py to path, then py_compile-validate it.
    On syntax failure: restores previous hook (or writes a safe stub) so the
    system is never left without a working hook file."""
    import py_compile, tempfile, os
    # Stash existing hook so we can restore on failure
    backup = None
    if path.exists():
        backup = path.read_text()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_read_template("hook_template.py"))
    path.chmod(0o755)
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        if backup is not None:
            path.write_text(backup)
        else:
            path.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n")
        raise RuntimeError(
            f"hook.py failed syntax check — previous hook restored.\n{exc}"
        ) from exc


def _install_session_hooks() -> None:
    """Write PreCompact + SessionStart hook scripts and register them in ~/.claude/settings.json."""
    python = _best_python()

    precompact_path = GUARD_DIR / "guard-precompact.py"
    session_start_path = GUARD_DIR / "guard-session-start.py"

    precompact_path.write_text(_read_template("hook_precompact_template.py"))
    precompact_path.chmod(0o755)
    session_start_path.write_text(_read_template("hook_session_start_template.py"))
    session_start_path.chmod(0o755)

    claude_settings = Path.home() / ".claude" / "settings.json"
    settings: dict = {}
    if claude_settings.exists():
        try:
            settings = json.loads(claude_settings.read_text())
        except Exception:
            pass

    hooks = settings.setdefault("hooks", {})

    pre_cmd = f"{python} {precompact_path}"
    compact_hooks = hooks.setdefault("PreCompact", [])
    if not any(pre_cmd in str(e) for h in compact_hooks for e in h.get("hooks", [])):
        compact_hooks.append({"hooks": [{"type": "command", "command": pre_cmd}]})

    start_cmd = f"{python} {session_start_path}"
    start_hooks = hooks.setdefault("SessionStart", [])
    if not any(start_cmd in str(e) for h in start_hooks for e in h.get("hooks", [])):
        start_hooks.append({"hooks": [{"type": "command", "command": start_cmd}]})

    claude_settings.parent.mkdir(parents=True, exist_ok=True)
    claude_settings.write_text(json.dumps(settings, indent=2) + "\n")


# ── Guard config helpers ──────────────────────────────────────────────────────

def _load_guard_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_guard_config(data: dict):
    GUARD_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def _require_guard_config() -> dict:
    cfg = _load_guard_config()
    ws = cfg.get("workspace_id")
    if not cfg or not ws:
        print(f"{RED}Guard not connected. Run: conduct login --api-key <key>{RESET}", file=sys.stderr)
        sys.exit(0)
    if not cfg.get("api_key"):
        print(f"{RED}Guard config is missing API key. Re-run: conduct login --api-key <key>{RESET}", file=sys.stderr)
        sys.exit(0)
    return cfg


def _api_url(cfg: dict) -> str:
    return cfg.get("api_url", "https://api.conductai.ai").rstrip("/")


# ── MCP registration ──────────────────────────────────────────────────────────

# Tools that support mcpServers JSON — only write if the config file already exists
_MCP_TARGETS = [
    (Path.home() / ".claude"   / "settings.json", "Claude Code"),
    (Path.home() / ".cursor"   / "mcp.json",       "Cursor"),
    (Path.home() / ".windsurf" / "mcp.json",        "Windsurf"),
    (Path.home() / ".codex"    / "mcp.json",        "Codex"),
]


def _register_mcp(workspace_id: str, member_token: str, api_url: str) -> None:
    """Write conductguard MCP entry into every AI tool config found on this machine.

    Credentials are NOT stored in the MCP config — the server reads them from
    ~/.conductguard/config.json at startup, which is written by guard sync.
    """
    entry = {"command": "conductguard-mcp"}
    found_any = False
    for cfg_path, label in _MCP_TARGETS:
        if not cfg_path.exists():
            continue
        found_any = True
        try:
            existing = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
        mcp = existing.setdefault("mcpServers", {})
        if mcp.get("conductguard") == entry:
            print(f"  {GRAY}Guard MCP already registered in {label}{RESET}")
            continue
        mcp["conductguard"] = entry
        cfg_path.write_text(json.dumps(existing, indent=2))
        print(f"  {GREEN}Guard MCP registered in {label}{RESET}")
    if not found_any:
        print(f"  {GRAY}No AI tool configs found for MCP registration{RESET}")


def _install_codex_hook(hook_path: Path) -> None:
    """Register PreToolUse and PostToolUse hooks in ~/.codex/hooks.json."""
    codex_hooks = Path.home() / ".codex" / "hooks.json"
    if not (Path.home() / ".codex").exists():
        return  # Codex not installed

    hooks: dict = {}
    if codex_hooks.exists():
        try:
            hooks = json.loads(codex_hooks.read_text())
        except json.JSONDecodeError:
            hooks = {}

    hook_section = hooks.setdefault("hooks", {})

    # PreToolUse
    pre_cmd = f"{_best_python()} {hook_path}"
    hook_path_str = str(hook_path)
    pre = hook_section.setdefault("PreToolUse", [])
    # Match by hook path so old python3/python3.11 entries are treated as already registered
    pre_already = any(
        hook_path_str in e.get("command", "")
        for h in pre
        for e in h.get("hooks", [])
    )
    changed = False
    if not pre_already:
        pre.append({"matcher": ".*", "hooks": [{"type": "command", "command": pre_cmd}]})
        changed = True
    else:
        # Update existing entry to use current sys.executable
        for h in pre:
            for e in h.get("hooks", []):
                if hook_path_str in e.get("command", "") and e["command"] != pre_cmd:
                    e["command"] = pre_cmd
                    changed = True

    # PostToolUse
    post_cmd = f"{_best_python()} {hook_path} post"
    post = hook_section.setdefault("PostToolUse", [])
    # Remove stale conductguard-post entries registered by older CLI versions
    stale = "conductguard-post"
    cleaned = False
    for h in post:
        before = len(h.get("hooks", []))
        h["hooks"] = [e for e in h.get("hooks", []) if e.get("command") != stale]
        if len(h["hooks"]) < before:
            cleaned = True
    post[:] = [h for h in post if h.get("hooks")]
    post_already = any(
        hook_path_str in e.get("command", "")
        for h in post
        for e in h.get("hooks", [])
    )
    if not post_already:
        post.append({"matcher": ".*", "hooks": [{"type": "command", "command": post_cmd}]})
        changed = True
    if cleaned:
        changed = True

    if changed:
        codex_hooks.parent.mkdir(parents=True, exist_ok=True)
        codex_hooks.write_text(json.dumps(hooks, indent=2))
        if not pre_already:
            print(f"  {GREEN}Codex PreToolUse hook registered{RESET}")
        if not post_already or cleaned:
            print(f"  {GREEN}Codex PostToolUse hook registered{RESET}")
    else:
        print(f"  {GRAY}Codex hooks already registered{RESET}")


# ── HTTP helpers (no third-party deps — mirrors api.py style) ─────────────────

def _req(method: str, url: str, body=None, token: str = None, api_key: str = None, timeout: int = 20) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["X-Api-Key"] = api_key
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("detail", raw)
        except Exception:
            detail = raw
        print(f"{RED}HTTP {e.code}: {detail}{RESET}")
        sys.exit(1)
    except Exception:
        print(f"{RED}Could not reach ConductAI API. Check your connection.{RESET}")
        sys.exit(1)



def _save_policy(policy: dict):
    GUARD_DIR.mkdir(parents=True, exist_ok=True)
    POLICY_PATH.write_text(json.dumps(policy, indent=2))


# ── since-string parser ───────────────────────────────────────────────────────

def _parse_since(since_str: str) -> str:
    """Convert '7d', '24h', '1h', '30d' to an ISO-8601 UTC timestamp string."""
    unit  = since_str[-1].lower()
    value = int(since_str[:-1])
    delta_map = {"h": timedelta(hours=value), "d": timedelta(days=value)}
    if unit not in delta_map:
        print(f"{RED}Invalid --since value '{since_str}'. Use: 1h, 24h, 7d, 30d{RESET}")
        sys.exit(1)
    return (datetime.now(tz=timezone.utc) - delta_map[unit]).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Hook helpers ─────────────────────────────────────────────────────────────

def _install_claude_hook(hook_path: Path) -> None:
    """Register PreToolUse and PostToolUse hooks in ~/.claude/settings.json."""
    claude_settings = Path.home() / ".claude" / "settings.json"
    settings: dict = {}
    if claude_settings.exists():
        try:
            settings = json.loads(claude_settings.read_text())
        except json.JSONDecodeError:
            settings = {}

    hooks = settings.setdefault("hooks", {})

    # PreToolUse — existing hook script
    pre = hooks.setdefault("PreToolUse", [])
    pre_cmd = f"{_best_python()} {hook_path}"
    hook_path_str = str(hook_path)
    pre_already = any(
        hook_path_str in e.get("command", "")
        for h in pre
        for e in h.get("hooks", [])
    )
    changed = False
    if not pre_already:
        pre.append({"matcher": ".*", "hooks": [{"type": "command", "command": pre_cmd}]})
        changed = True
    else:
        # Update existing entry to use current sys.executable
        for h in pre:
            for e in h.get("hooks", []):
                if hook_path_str in e.get("command", "") and e["command"] != pre_cmd:
                    e["command"] = pre_cmd
                    changed = True

    # PostToolUse
    post = hooks.setdefault("PostToolUse", [])
    post_cmd = f"{_best_python()} {hook_path} post"
    # Remove stale conductguard-post entries registered by older CLI versions
    stale = "conductguard-post"
    cleaned = False
    for h in post:
        before = len(h.get("hooks", []))
        h["hooks"] = [e for e in h.get("hooks", []) if e.get("command") != stale]
        if len(h["hooks"]) < before:
            cleaned = True
    post[:] = [h for h in post if h.get("hooks")]
    post_already = any(
        hook_path_str in e.get("command", "")
        for h in post
        for e in h.get("hooks", [])
    )
    if not post_already:
        post.append({"matcher": ".*", "hooks": [{"type": "command", "command": post_cmd}]})
        changed = True
    if cleaned:
        changed = True

    # Stop — auto-sync RTK + Booster savings at end of every session
    stop = hooks.setdefault("Stop", [])
    stop_cmd = "conduct guard sync"
    stop_already = any(
        stop_cmd in e.get("command", "")
        for h in stop
        for e in h.get("hooks", [])
    )
    if not stop_already:
        stop.append({"hooks": [{"type": "command", "command": stop_cmd}]})
        changed = True

    if changed:
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        claude_settings.write_text(json.dumps(settings, indent=2))
        if not pre_already:
            print(f"  {GREEN}Claude Code PreToolUse hook registered{RESET}")
        if not post_already or cleaned:
            print(f"  {GREEN}Claude Code PostToolUse hook registered{RESET}")
        if not stop_already:
            print(f"  {GREEN}Claude Code Stop hook registered (auto-sync savings){RESET}")
    else:
        print(f"  {GRAY}Claude Code hooks already registered{RESET}")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_guard_install(args):
    """Called automatically from `conduct login`. Sets up Guard: downloads policies, installs hook + MCP."""
    api_key = getattr(args, "api_key", None)
    server  = getattr(args, "server", "https://api.conductai.ai").rstrip("/")

    # Load workspace_id from ~/.conduct/config.json
    conduct_cfg_path = Path.home() / ".conduct" / "config.json"
    conduct_cfg: dict = {}
    if conduct_cfg_path.exists():
        try:
            conduct_cfg = json.loads(conduct_cfg_path.read_text())
        except Exception:
            pass

    workspace_id = conduct_cfg.get("workspace")
    if not workspace_id or not api_key:
        return  # nothing to do

    print(f"  Setting up Guard…")

    result = _req(
        "GET",
        f"{server}/guard/config/installed?workspace_id={workspace_id}",
        api_key=api_key,
    )

    if not result.get("installed"):
        print(f"  {GRAY}Guard not installed for this workspace — skipping{RESET}")
        return

    member_token   = result.get("member_token") or ""
    user_email     = result.get("user_email") or ""
    clerk_user_id  = result.get("clerk_user_id") or ""

    # Check if Security Loop module is installed for this workspace
    security_emit = False
    try:
        sec = _req("GET", f"{server}/secure/installed?workspace_id={workspace_id}", api_key=api_key)
        if sec.get("installed"):
            security_emit = True
    except Exception:
        pass

    # Persist guard config — include api_key so CLI commands can authenticate
    _save_guard_config({
        "workspace_id":          workspace_id,
        "member_token":          member_token,
        "user_email":            user_email,
        "clerk_user_id":         clerk_user_id,
        "api_key":               api_key,
        "api_url":               server,
        "security_emit_enabled": security_emit,
    })
    if security_emit:
        print(f"  {GREEN}Security Loop:{RESET} installed — classifier active")

    # Download policies
    try:
        policy = _req(
            "GET",
            f"{server}/guard/policies/sync?workspace_id={workspace_id}",
            api_key=api_key,
        )
        _save_policy(policy)
        rule_count = len(policy.get("rules", []))
        print(f"  {GREEN}Guard policies:{RESET} {rule_count} rule(s) active")
    except SystemExit:
        rule_count = 0

    # Write hook script
    hook_path = GUARD_DIR / "hook.py"
    _write_hook(hook_path)

    # Install PreToolUse hooks — Claude Code + Codex (real interception)
    _install_claude_hook(hook_path)
    _install_codex_hook(hook_path)

    # Register MCP in all found AI tools — Cursor/Windsurf (advisory)
    _register_mcp(workspace_id, member_token or "", server)

    # Install session persistence hooks (PreCompact + SessionStart)
    try:
        _install_session_hooks()
    except Exception:
        pass


def cmd_guard_join(args):
    invite_code = args.invite_code

    # Prompt for email if not supplied
    email = getattr(args, "email", None) or input("Email address: ").strip()
    if not email:
        print(f"{RED}Email is required.{RESET}")
        sys.exit(1)

    # Use configured API URL or default
    existing_cfg = _load_guard_config()
    base_url     = existing_cfg.get("api_url", "https://api.conductai.ai").rstrip("/")

    print(f"\nJoining workspace with invite code {CYAN}{invite_code}{RESET}…")

    payload = {"invite_code": invite_code, "email": email}
    result = _req("POST", f"{base_url}/guard/join", body=payload)

    workspace_id = result["workspace_id"]
    member_token = result.get("member_token", "")
    policy       = result.get("policy", {"workspace_id": workspace_id, "version": "1", "rules": []})

    # Download and persist policy
    _save_policy(policy)
    rule_count = len(policy.get("rules", []))
    print(f"  {GREEN}Policy downloaded:{RESET} {rule_count} rule(s)")

    # Persist guard config
    cfg = {
        "workspace_id": workspace_id,
        "user_email":   email,
        "api_url":      base_url,
    }
    if member_token:
        cfg["member_token"] = member_token
    _save_guard_config(cfg)

    # Write hook script
    hook_path = GUARD_DIR / "hook.py"
    _write_hook(hook_path)
    print(f"  {GREEN}Hook script written:{RESET} {hook_path}")

    # Install PreToolUse hook in ~/.claude/settings.json
    _install_claude_hook(hook_path)

    print(
        f"\n{BOLD}{GREEN}Guard connected.{RESET} "
        f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} active.\n"
        f"Your AI tool calls will now be checked against team policies."
    )


def _report_tools_to_server() -> None:
    """Detect AI coding tools on this machine and POST coverage to Guard API. Silent on failure."""
    home = Path.home()

    def _check_json_key(path: Path, *keys) -> bool:
        try:
            d = json.loads(path.read_text()) if path.exists() else {}
            for k in keys:
                d = d.get(k, {}) if isinstance(d, dict) else {}
            return bool(d) and isinstance(d, dict) and len(d) > 0
        except Exception:
            return False

    def _check_json_mcp(path: Path) -> bool:
        try:
            d = json.loads(path.read_text()) if path.exists() else {}
            return "conduct" in d.get("mcpServers", {})
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

    tools = []

    claude_dir = home / ".claude"
    if claude_dir.exists():
        settings = claude_dir / "settings.json"
        tools.append({
            "name": "claude-code",
            "mcp_registered": _check_json_mcp(settings),
            "hook_registered": _check_json_hook(settings),
        })

    codex_dir = home / ".codex"
    if codex_dir.exists():
        config = codex_dir / "config.toml"
        tools.append({
            "name": "codex",
            "mcp_registered": _check_toml_str(config, "conduct-mcp"),
            "hook_registered": _check_toml_str(config, "conductguard"),
        })

    cursor_dir = home / ".cursor"
    if cursor_dir.exists():
        tools.append({
            "name": "cursor",
            "mcp_registered": _check_json_mcp(cursor_dir / "mcp.json"),
            "hook_registered": False,
        })

    windsurf_dir = home / ".codeium" / "windsurf"
    if windsurf_dir.exists():
        tools.append({
            "name": "windsurf",
            "mcp_registered": _check_json_mcp(windsurf_dir / "mcp_config.json"),
            "hook_registered": False,
        })

    vscode_candidates = [
        home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
        home / ".config" / "Code" / "User" / "settings.json",
        home / ".vscode" / "settings.json",
    ]
    vscode_settings = next((p for p in vscode_candidates if p.exists()), None)
    if vscode_settings:
        try:
            d = json.loads(vscode_settings.read_text())
            mcp_reg = "conduct" in d.get("mcp", {}).get("servers", {})
        except Exception:
            mcp_reg = False
        tools.append({
            "name": "vscode",
            "mcp_registered": mcp_reg,
            "hook_registered": False,
        })

    if not tools:
        return

    try:
        cfg = _load_guard_config()
        base_url = _api_url(cfg)
        email = cfg.get("user_email", "")
        token = cfg.get("member_token", "")
        api_key = cfg.get("api_key", "")

        if not email:
            return

        # Also pull conduct API key for X-Api-Key auth (member_token is not accepted by this endpoint)
        conduct_cfg_path = Path.home() / ".conduct" / "config.json"
        conduct_api_key = ""
        if conduct_cfg_path.exists():
            try:
                conduct_api_key = json.loads(conduct_cfg_path.read_text()).get("api_key", "")
            except Exception:
                pass

        payload = json.dumps({"email": email, "tools": tools}).encode()
        headers = {"Content-Type": "application/json"}
        if conduct_api_key and conduct_api_key.startswith("cond_live_"):
            headers["X-Api-Key"] = conduct_api_key
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
        pass  # Never surface errors — this is background telemetry


def cmd_guard_sync(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    api_key      = cfg.get("api_key", "")
    base_url     = _api_url(cfg)

    print(f"Syncing policy…")

    try:
        policy = _req(
            "GET",
            f"{base_url}/guard/policies/sync?workspace_id={workspace_id}",
            api_key=api_key,
        )
    except Exception as e:
        print(f"Guard sync skipped: {e}", file=sys.stderr)
        sys.exit(0)
    _save_policy(policy)
    rule_count = len(policy.get("rules", []))
    print(f"  {GREEN}Policy refreshed:{RESET} {rule_count} rule(s)")

    # Re-check Security Loop install status
    try:
        sec = _req("GET", f"{base_url}/secure/installed?workspace_id={workspace_id}", api_key=api_key)
        cfg["security_emit_enabled"] = bool(sec.get("installed"))
        _save_guard_config(cfg)
        if sec.get("installed"):
            print(f"  {GREEN}Security Loop:{RESET} installed — classifier active")
            try:
                policies = _req("GET", f"{base_url}/secure/policies?workspace_id={workspace_id}", api_key=api_key)
                policy_count = len(policies) if isinstance(policies, list) else 0
                print(f"  {GREEN}Security Loop policies:{RESET} {policy_count} rule(s) synced")
            except Exception:
                pass
    except Exception:
        pass

    # Refresh hook script + re-register in all tools
    hook_path = GUARD_DIR / "hook.py"
    _write_hook(hook_path)
    _install_claude_hook(hook_path)
    _install_codex_hook(hook_path)
    cfg2 = _load_guard_config()
    _register_mcp(workspace_id, cfg2.get("member_token", ""), base_url)
    try:
        _install_session_hooks()
    except Exception:
        pass
    print(f"  {GREEN}Hook script updated{RESET}")

    # Auto-init Agent Booster if installed but not yet set up in this project
    _ensure_booster(Path.cwd())

    # Capture savings from RTK and Agent Booster
    _report_savings(cfg, base_url, api_key)

    # Report AI tool coverage
    try:
        _report_tools_to_server()
    except Exception:
        pass

    print(f"\n{BOLD}Policy refreshed ({rule_count} rule(s)).{RESET}")


def _ensure_booster(root: Path) -> None:
    """Auto-init and background-index booster if installed but not yet set up."""
    import shutil
    import subprocess
    import sys

    if not shutil.which("booster"):
        if sys.version_info < (3, 10):
            print(
                f"  {GRAY}Agent Booster:{RESET} requires Python 3.10+ "
                f"(you have {sys.version_info.major}.{sys.version_info.minor}). "
                f"Upgrade Python then: pip install 'conduct-cli[booster]'"
            )
            return
        print(f"  {GRAY}Agent Booster:{RESET} installing…")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "conduct-cli[booster]"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            print(f"  {RED}Agent Booster:{RESET} install failed — {r.stderr.strip()[:120]}")
            return
        print(f"  {GREEN}Agent Booster:{RESET} installed")
        if not shutil.which("booster"):
            print(f"  {YELLOW}Agent Booster:{RESET} 'booster' not on PATH yet — restart shell or re-run sync")
            return

    # Upgrade booster to latest in background (non-blocking)
    # Use [booster] extra only on Python 3.10+ — agent-booster requires 3.10+
    _pkg = "conduct-cli[booster]" if sys.version_info >= (3, 10) else "conduct-cli"
    try:
        subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", _pkg],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    db_path = root / ".booster" / "symbols.db"
    hooks_path = root / ".claude" / "hooks" / "booster-gate.py"

    # Init (writes hook scripts + wires settings.json) — fast, idempotent
    if not hooks_path.exists():
        try:
            r = subprocess.run(
                ["booster", "init", "claude", "--yes"],
                capture_output=True, timeout=15, cwd=str(root),
            )
            if r.returncode == 0:
                print(f"  {GREEN}Agent Booster:{RESET} hooks installed")
            else:
                print(f"  {GRAY}Agent Booster:{RESET} init failed — {r.stderr.strip()[:120]}")
                return
        except Exception:
            return

    # Index in background — may take 10-60s on large repos, never blocks sync
    if not db_path.exists():
        try:
            subprocess.Popen(
                ["booster", "index", "--embed"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=str(root),
            )
            print(f"  {GREEN}Agent Booster:{RESET} indexing in background (Read/Grep intercept active shortly)")
        except Exception:
            pass
    else:
        symbols_count = 0
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            symbols_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            conn.close()
        except Exception:
            pass
        print(f"  {GREEN}Agent Booster:{RESET} {symbols_count} symbols indexed — Read/Grep intercept active")


def _report_savings(cfg: dict, base_url: str, api_key: str) -> None:
    import subprocess

    rtk_data = {}
    booster_data = {}

    # Read RTK savings — rtk gain -f json nests under "summary" key
    try:
        r = subprocess.run(["rtk", "gain", "-f", "json"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            raw = json.loads(r.stdout)
            summary = raw.get("summary", raw)
            rtk_data = {
                "saved_tokens": summary.get("total_saved", 0),
                "savings_pct": summary.get("avg_savings_pct", 0.0),
                "total_commands": summary.get("total_commands", 0),
            }
    except Exception:
        pass

    # Read Agent Booster savings
    try:
        r = subprocess.run(["booster", "gain", "-f", "json"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            raw = json.loads(r.stdout)
            booster_data = {
                "saved_tokens": raw.get("saved_tokens", 0),
                "savings_pct": raw.get("savings_pct", 0.0),
                "total_reads": raw.get("total_reads", 0),
            }
    except Exception:
        pass

    # If neither tool returned data, skip silently
    if not rtk_data and not booster_data:
        return

    # Load baseline to compute period_start
    baseline_path = GUARD_DIR / "savings_baseline.json"
    period_start = None
    try:
        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_text())
            period_start = baseline.get("recorded_at")
    except Exception:
        pass

    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "workspace_id": cfg.get("workspace_id", ""),
        "member_email": cfg.get("user_email", ""),
        "rtk": rtk_data,
        "booster": booster_data,
        "period_start": period_start,
        "period_end": now_iso,
    }

    try:
        member_token = cfg.get("member_token", "")
        headers = {"Content-Type": "application/json"}
        if member_token:
            headers["Authorization"] = f"Bearer {member_token}"
        elif api_key:
            headers["X-Api-Key"] = api_key
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{base_url}/guard/savings",
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        # Save baseline for next diff
        baseline_path.write_text(json.dumps({"recorded_at": now_iso, "rtk": rtk_data, "booster": booster_data}))
        print(f"  {GREEN}Savings reported{RESET}")
    except Exception:
        pass  # Never fail sync because savings POST failed


def cmd_guard_status(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    user_email   = cfg.get("user_email", "")
    api_key      = cfg.get("api_key", "")
    base_url     = _api_url(cfg)

    # Auto-refresh user_email + clerk_user_id into config if missing
    if (not user_email or not cfg.get("clerk_user_id")) and api_key:
        try:
            installed = _req("GET", f"{base_url}/guard/config/installed", api_key=api_key)
            fetched_email = installed.get("user_email") or ""
            fetched_clerk = installed.get("clerk_user_id") or ""
            if fetched_email:
                cfg["user_email"] = fetched_email
                user_email = fetched_email
            if fetched_clerk:
                cfg["clerk_user_id"] = fetched_clerk
            _save_guard_config(cfg)
            # Rewrite hook script so future events carry the email
            hook_path = GUARD_DIR / "hook.py"
            _write_hook(hook_path)
        except Exception:
            pass

    # Load local policy for rule count
    rule_count = 0
    if POLICY_PATH.exists():
        try:
            policy     = json.loads(POLICY_PATH.read_text())
            rule_count = len(policy.get("rules", []))
        except Exception:
            pass

    # Fetch today's spend
    spend = {}
    try:
        spend = _req(
            "GET",
            f"{base_url}/guard/spend?workspace_id={workspace_id}",
            api_key=api_key,
        )
    except SystemExit:
        pass

    # Fetch recent violations (today)
    today_iso = datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    events: list = []
    try:
        events = _req(
            "GET",
            (
                f"{base_url}/guard/events"
                f"?workspace_id={workspace_id}"
                f"&user_email={user_email}"
                f"&since={today_iso}"
                f"&limit=20"
            ),
            api_key=api_key,
        )
        if not isinstance(events, list):
            events = events.get("events", [])
    except SystemExit:
        pass

    violations = [e for e in events if e.get("decision") == "blocked"]

    # Format spend figures
    sessions        = spend.get("sessions", 0)
    tokens_used     = spend.get("tokens_used", 0)
    token_saved_pct = spend.get("token_saved_pct", 0)
    cost            = spend.get("cost_usd", 0.0)
    cost_saved      = spend.get("cost_saved_usd", 0.0)

    viol_summary = ""
    if violations:
        rule_names = ", ".join(v.get("rule", "unknown") for v in violations[:3])
        viol_summary = f"  ({rule_names} — blocked)"

    print(f"\n{BOLD}Guard status{RESET} — {user_email}")
    print(f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} active")
    print()
    print(f"Today:")
    print(f"  Sessions: {sessions}")
    print(f"  Tokens used: {tokens_used:,}  (saved {token_saved_pct}% via optimization)")
    print(f"  Cost: ${cost:.2f}  (saved ${cost_saved:.2f})")
    print(f"  Violations: {len(violations)}{viol_summary}")
    print()


def cmd_guard_savings(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    api_key      = cfg.get("api_key", "")
    base_url     = _api_url(cfg)

    try:
        data = _req(
            "GET",
            f"{base_url}/guard/savings/team-summary?workspace_id={workspace_id}",
            api_key=api_key,
        )
    except Exception:
        print(f"{RED}Failed to fetch team savings.{RESET}")
        return
    if not isinstance(data, dict):
        print(f"{RED}Failed to fetch team savings.{RESET}")
        return

    dev_count   = data.get("developer_count", 0)
    total_tok   = data.get("total_tokens_saved", 0)
    per_day     = data.get("per_day_usd", 0.0)
    per_month   = data.get("per_month_usd", 0.0)
    per_year    = data.get("per_year_usd", 0.0)
    tools       = data.get("tools_installed", [])
    avg_tok     = total_tok // dev_count if dev_count else 0
    avg_day_usd = round(per_day / dev_count, 2) if dev_count else 0.0

    print()
    print(f"{BOLD}Team Token Savings{RESET}  ({dev_count} developer{'s' if dev_count != 1 else ''})")
    print("─" * 52)
    print(f"  Total tokens saved:    {total_tok:>14,}")
    print(f"  Estimated savings:     ${per_day:>8.2f}/day  ·  ${per_month:,.0f}/month  ·  ${per_year:,.0f}/year")
    if dev_count:
        print(f"  Avg per developer:     {avg_tok:>14,} tokens  ·  ${avg_day_usd:.2f}/day")
    if tools:
        print(f"  Tools contributing:    {', '.join(tools)}")
    print()


def cmd_guard_audit(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    user_email   = cfg.get("user_email", "")
    api_key      = cfg.get("api_key", "")
    base_url     = _api_url(cfg)

    since_str = getattr(args, "since", None) or "24h"
    since_iso = _parse_since(since_str)

    events_resp = _req(
        "GET",
        (
            f"{base_url}/guard/events"
            f"?workspace_id={workspace_id}"
            f"&user_email={user_email}"
            f"&since={since_iso}"
            f"&limit=50"
        ),
        api_key=api_key,
    )
    events = events_resp if isinstance(events_resp, list) else events_resp.get("events", [])

    if not events:
        print(f"{GRAY}No events in the last {since_str}.{RESET}")
        return

    # Table header
    ts_w     = 22
    tool_w   = 14
    action_w = 28
    dec_w    = 10
    print()
    print(
        f"{BOLD}"
        f"{'Timestamp':<{ts_w}} "
        f"{'Tool':<{tool_w}} "
        f"{'Action':<{action_w}} "
        f"{'Decision':<{dec_w}} "
        f"{'Rule'}"
        f"{RESET}"
    )
    print("─" * (ts_w + tool_w + action_w + dec_w + 20))

    for ev in events:
        ts_raw   = ev.get("timestamp", ev.get("created_at", ""))
        ts       = ts_raw[:19].replace("T", " ") if ts_raw else "—"
        tool     = (ev.get("ai_tool") or "—")[:tool_w - 1]
        action   = (ev.get("tool_call") or "—")[:action_w - 1]
        decision = ev.get("decision", "—")
        rule     = (ev.get("rule_id") or ev.get("rule_message") or "—")

        dec_color = RED if decision == "blocked" else GREEN if decision == "allowed" else GRAY
        print(
            f"  {GRAY}{ts:<{ts_w}}{RESET} "
            f"{tool:<{tool_w}} "
            f"{action:<{action_w}} "
            f"{dec_color}{decision:<{dec_w}}{RESET} "
            f"{GRAY}{rule}{RESET}"
        )

    print()


# ── Subparser registration (called from main.py) ──────────────────────────────

def register_guard_parser(sub):
    """Attach the `guard` subparser tree to an existing argparse subparsers object."""
    guard_p = sub.add_parser("guard", help="Guard — team policies and MCP registration")
    guard_sub = guard_p.add_subparsers(dest="guard_command")

    # conduct guard sync
    guard_sub.add_parser("sync", help="Refresh policy and re-scan for AI tools")

    # conduct guard status
    guard_sub.add_parser("status", help="Show today's spend and violations")

    # conduct guard savings --team
    guard_sub.add_parser("savings", help="Show org-level token savings across all developers")

    # conduct guard audit [--since 7d]
    audit_p = guard_sub.add_parser("audit", help="Show recent guard events")
    audit_p.add_argument(
        "--since",
        default="24h",
        metavar="PERIOD",
        help="Time window: 1h, 24h, 7d, 30d (default: 24h)",
    )

    # conduct guard booster-status
    guard_sub.add_parser("booster-status", help="Verify Agent Booster intercept is active for this project")

    return guard_p, guard_sub


def cmd_guard_booster_status(args):
    """Show whether booster is intercepting Read/Grep in this project."""
    import shutil, sqlite3, subprocess

    root = Path.cwd()
    db_path    = root / ".booster" / "symbols.db"
    hooks_path = root / ".claude" / "hooks" / "booster-gate.py"
    settings_p = root / ".claude" / "settings.json"

    booster_bin = shutil.which("booster")
    print(f"\n{BOLD}Agent Booster intercept status — {root.name}{RESET}\n")

    # 1. Binary
    if booster_bin:
        print(f"  {GREEN}✓{RESET} booster installed  ({booster_bin})")
    else:
        print(f"  {RED}✗{RESET} booster not found on PATH — run: pip install agent-booster")
        return

    # 2. Hook scripts written
    if hooks_path.exists():
        print(f"  {GREEN}✓{RESET} hook scripts present  (.claude/hooks/booster-gate.py)")
    else:
        print(f"  {RED}✗{RESET} hook scripts missing — run: conduct guard sync")

    # 3. Wired in settings.json
    wired = False
    if settings_p.exists():
        import json as _json
        s = _json.loads(settings_p.read_text())
        for h in s.get("hooks", {}).get("PreToolUse", []):
            if h.get("matcher") == "Read":
                wired = True
                break
    if wired:
        print(f"  {GREEN}✓{RESET} Read hook wired in .claude/settings.json")
    else:
        print(f"  {RED}✗{RESET} Read hook NOT in .claude/settings.json — run: conduct guard sync")

    # 4. Index
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            files = conn.execute("SELECT COUNT(DISTINCT file) FROM symbols").fetchone()[0]
            conn.close()
            print(f"  {GREEN}✓{RESET} symbols.db  — {count} symbols across {files} files")
        except Exception:
            print(f"  {YELLOW}?{RESET} symbols.db exists but could not be read")
    else:
        print(f"  {RED}✗{RESET} symbols.db missing — Read calls fall through unintercepted")
        print(f"       run: booster index --embed  (or: conduct guard sync to trigger it)")
        return

    # 5. Live intercept test — try reading a known file and check if smart-read fires
    print(f"\n  {BOLD}Live intercept test:{RESET}")
    if not hooks_path.exists():
        print(f"  {YELLOW}~{RESET} Skipped — hook script not present")
        print()
        return
    try:
        import tempfile, json as _json
        # Pick the first indexed file
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT file FROM symbols LIMIT 1").fetchone()
        conn.close()
        if row:
            # Prefer a .py/.ts file — more likely to have symbols and trigger smart-read
            conn = sqlite3.connect(str(db_path))
            src = conn.execute(
                "SELECT file FROM symbols WHERE file LIKE '%.py' OR file LIKE '%.ts' LIMIT 1"
            ).fetchone() or row
            conn.close()
            test_file = str(root / src[0])
            payload = _json.dumps({"tool_name": "Read", "tool_input": {"file_path": test_file}})
            r = subprocess.run(
                ["python3", str(hooks_path)],
                input=payload, capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 2:
                lines = r.stdout.strip().splitlines()
                print(f"  {GREEN}✓{RESET} Read intercepted → smart-read fired ({len(lines)} lines returned)")
                print(f"    tested on: {row[0]}")
            elif r.returncode == 0:
                print(f"  {YELLOW}~{RESET} Hook ran but passed through (file may not have symbols)")
            else:
                print(f"  {RED}✗{RESET} Hook errored (exit {r.returncode})")
    except Exception as e:
        print(f"  {YELLOW}?{RESET} Could not run live test: {e}")

    print()


def dispatch_guard(args, guard_p):
    """Dispatch to the correct guard handler. Called from main()."""
    guard_command = getattr(args, "guard_command", None)
    if guard_command == "sync":
        cmd_guard_sync(args)
    elif guard_command == "status":
        cmd_guard_status(args)
    elif guard_command == "savings":
        cmd_guard_savings(args)
    elif guard_command == "audit":
        cmd_guard_audit(args)
    elif guard_command == "booster-status":
        cmd_guard_booster_status(args)
    else:
        guard_p.print_help()
        sys.exit(1)
