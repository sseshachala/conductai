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

GUARD_DIR      = Path.home() / ".conductguard"
CONFIG_PATH    = GUARD_DIR / "config.json"
POLICY_PATH    = GUARD_DIR / "policy.json"
CONDUCT_CONFIG = Path.home() / ".conduct" / "config.json"

_HOOK_SCRIPT = '''\
#!/usr/bin/env python3
"""ConductGuard PreToolUse hook — enforces team policies locally."""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

GUARD_DIR         = Path.home() / ".conductguard"
POLICY_PATH       = GUARD_DIR / "policy.json"
CONFIG_PATH       = GUARD_DIR / "config.json"
BUDGET_CACHE_PATH = GUARD_DIR / "budget_cache.json"
BUDGET_CACHE_TTL  = 300  # 5 minutes


def _load_budget_cache():
    """Return (hard_blocked, reason) if cache is fresh, else (None, None)."""
    if not BUDGET_CACHE_PATH.exists():
        return None, None
    try:
        data = json.loads(BUDGET_CACHE_PATH.read_text())
        if time.time() - data.get("ts", 0) < BUDGET_CACHE_TTL:
            return data.get("hard_blocked", False), data.get("reason")
    except Exception:
        pass
    return None, None


def _fetch_budget_status():
    """Call /guard/spend/budget-check and cache result for BUDGET_CACHE_TTL seconds."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        return False, None
    team_id  = cfg.get("team_id")
    email    = cfg.get("user_email", "")
    api_url  = cfg.get("api_url", "https://api.conduct.ai").rstrip("/")
    if not team_id:
        return False, None
    url = f"{api_url}/guard/spend/budget-check?team_id={team_id}"
    if email:
        import urllib.parse
        url += f"&email={urllib.parse.quote(email)}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        hard_blocked = data.get("hard_blocked", False)
        reason       = data.get("reason")
        BUDGET_CACHE_PATH.write_text(json.dumps({
            "ts": time.time(), "hard_blocked": hard_blocked, "reason": reason,
        }))
        return hard_blocked, reason
    except Exception:
        return False, None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Check hard budget cap (cached for 5 min to avoid per-call latency)
    hard_blocked, reason = _load_budget_cache()
    if hard_blocked is None:
        hard_blocked, reason = _fetch_budget_status()
    if hard_blocked:
        print(f"[ConductGuard] {reason or 'Budget hard cap reached. Contact your manager.'}")
        sys.exit(2)

    tool_name = (data.get("tool_name") or "").lower()
    tool_input = data.get("tool_input") or {}

    if not POLICY_PATH.exists():
        sys.exit(0)
    try:
        policy = json.loads(POLICY_PATH.read_text())
    except Exception:
        sys.exit(0)

    rules = policy.get("rules", [])
    if not rules:
        sys.exit(0)

    input_text = json.dumps(tool_input)
    path_fields = ["file_path", "path", "command"]
    path_text = " ".join(str(tool_input.get(f, "")) for f in path_fields)

    for rule in rules:
        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            allowed = [t.strip() for t in match_tool.split(",")]
            if tool_name not in allowed:
                continue

        pattern = rule.get("match_pattern")
        if pattern:
            try:
                if not re.search(pattern, input_text, re.IGNORECASE):
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

        action = rule.get("action", "audit")
        message = rule.get("message") or f"Policy violation: {rule.get(\'rule_id\', \'unknown\')}"
        rule_id = rule.get("rule_id", "unknown")

        _post_event(tool_name, tool_input, rule_id, action, message)

        if action == "block":
            print(f"[ConductGuard] {message}")
            sys.exit(2)
        elif action in ("warn", "approval"):
            print(f"[ConductGuard] {message}")
            sys.exit(0)
        # audit: silent, fall through

    sys.exit(0)


def _post_event(tool_name, tool_input, rule_id, action, message):
    try:
        cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        return

    team_id = cfg.get("team_id")
    if not team_id:
        return

    input_text = json.dumps(tool_input)
    decision = {"block": "blocked", "warn": "warned", "approval": "blocked"}.get(action, "audited")
    payload = json.dumps({
        "team_id": team_id,
        "member_id": cfg.get("member_id"),
        "user_email": cfg.get("user_email"),
        "ai_tool": "claude-code",
        "tool_call": tool_name,
        "input_summary": input_text[:200],
        "decision": decision,
        "rule_id": rule_id,
        "rule_message": message,
    })

    api_url = cfg.get("api_url", "https://api.conduct.ai").rstrip("/")
    api_key = cfg.get("api_key", "")
    member_token = cfg.get("member_token", "")
    auth_header = f'"X-Api-Key": "{api_key}"' if api_key else f'"Authorization": "Bearer {member_token}"'
    script = (
        "import urllib.request\\n"
        "try:\\n"
        f"    req = urllib.request.Request(\\"{api_url}/guard/events\\","
        f" data={repr(payload.encode())}, headers={{\\\"Content-Type\\\": \\\"application/json\\\", {auth_header}}}, method=\\"POST\\")\\n"
        "    urllib.request.urlopen(req, timeout=5)\\n"
        "except: pass\\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


if __name__ == "__main__":
    main()
'''

# AI tool config files and the label to show the user
_MCP_TARGETS = [
    (Path.home() / ".claude"    / "settings.json", "Claude Code"),
    (Path.home() / ".cursor"    / "mcp.json",      "Cursor"),
    (Path.home() / ".windsurf"  / "mcp.json",      "Windsurf"),
    (Path.home() / ".codex"     / "mcp.json",      "Codex"),
]


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
    if not cfg or not cfg.get("team_id"):
        print(f"{RED}Not connected. Run: conduct guard install{RESET}")
        sys.exit(1)
    return cfg


def _auth_kwargs(cfg: dict) -> dict:
    """Return kwargs for _req: prefer api_key over member_token."""
    if cfg.get("api_key"):
        return {"api_key": cfg["api_key"]}
    return {"token": cfg.get("member_token", "")}


def _api_url(cfg: dict) -> str:
    return cfg.get("api_url", "https://api.conduct.ai").rstrip("/")


# ── HTTP helpers (no third-party deps — mirrors api.py style) ─────────────────

def _req(method: str, url: str, body=None, token: str = None, api_key: str = None, timeout: int = 20) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    elif token:
        headers["Authorization"] = f"Bearer {token}"
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


# ── MCP registration helpers ──────────────────────────────────────────────────

def _mcp_entry(team_id: str, member_token: str) -> dict:
    return {
        "command": "conductguard-mcp",
        "args": ["--team", team_id, "--token", member_token],
    }


def _register_mcp(team_id: str, member_token: str) -> list[tuple[str, bool]]:
    """Write MCP entry into every found AI tool config. Returns list of (label, registered_now)."""
    entry   = _mcp_entry(team_id, member_token)
    results = []

    for cfg_path, label in _MCP_TARGETS:
        if not cfg_path.exists():
            continue

        try:
            existing = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

        mcp_servers = existing.get("mcpServers", {})
        current     = mcp_servers.get("conductguard", {})

        # Idempotent: only write if missing or token changed
        if (current.get("command") == entry["command"]
                and current.get("args") == entry["args"]):
            results.append((label, False))
            continue

        mcp_servers["conductguard"] = entry
        existing["mcpServers"]      = mcp_servers

        try:
            cfg_path.write_text(json.dumps(existing, indent=2))
            results.append((label, True))
        except OSError:
            print(f"{YELLOW}Warning: could not write to {cfg_path} — skipping.{RESET}")
            results.append((label, False))

    return results


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
    return (datetime.now(tz=timezone.utc) - delta_map[unit]).isoformat()


# ── Hook helpers ─────────────────────────────────────────────────────────────

def _install_claude_hook(hook_path: Path) -> None:
    """Register hook_path as a PreToolUse hook in ~/.claude/settings.json."""
    claude_settings = Path.home() / ".claude" / "settings.json"
    settings: dict = {}
    if claude_settings.exists():
        try:
            settings = json.loads(claude_settings.read_text())
        except json.JSONDecodeError:
            settings = {}

    hooks = settings.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    cmd = f"python3 {hook_path}"

    already = any(
        e.get("command") == cmd
        for h in pre
        for e in h.get("hooks", [])
    )
    if not already:
        pre.append({"matcher": ".*", "hooks": [{"type": "command", "command": cmd}]})
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        claude_settings.write_text(json.dumps(settings, indent=2))
        print(f"  {GREEN}Claude Code hook registered{RESET}")
    else:
        print(f"  {GRAY}Claude Code hook already registered{RESET}")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_guard_install(args):
    """conduct guard install — wire up Guard using the logged-in API key."""
    # Read API key + server from conduct login config
    conduct_cfg: dict = {}
    if CONDUCT_CONFIG.exists():
        try:
            conduct_cfg = json.loads(CONDUCT_CONFIG.read_text())
        except Exception:
            pass

    api_key  = getattr(args, "api_key", None) or conduct_cfg.get("api_key") or ""
    base_url = getattr(args, "server", None) or conduct_cfg.get("server", "https://api.conduct.ai")
    base_url = base_url.rstrip("/")

    if not api_key:
        print(f"{RED}No API key found. Run: conduct login --api-key <key>{RESET}")
        sys.exit(1)

    print(f"\nConnecting to Guard at {CYAN}{base_url}{RESET}…")

    # Resolve Guard team for this workspace
    status = _req("GET", f"{base_url}/guard/teams/installed", api_key=api_key)
    if not status.get("installed"):
        print(f"{RED}Guard is not installed for this workspace. Ask your admin to enable it.{RESET}")
        sys.exit(1)

    team_id   = status["team_id"]
    team_name = status.get("team_name", team_id)
    print(f"  {GREEN}Guard team:{RESET} {team_name} ({team_id})")

    # Pull active policies
    policy = _req("GET", f"{base_url}/guard/policies/sync?team_id={team_id}", api_key=api_key)
    _save_policy(policy)
    rule_count = len(policy.get("rules", []))
    print(f"  {GREEN}Policies downloaded:{RESET} {rule_count} rule(s)")

    # Fetch user email from /me for spend tracking
    user_email = ""
    try:
        me = _req("GET", f"{base_url}/me", api_key=api_key)
        user_email = me.get("email") or ""
    except SystemExit:
        pass

    # Persist guard config (api_key-based, no member_token needed)
    cfg = {
        "team_id":    team_id,
        "team_name":  team_name,
        "user_email": user_email,
        "api_key":    api_key,
        "api_url":    base_url,
    }
    _save_guard_config(cfg)

    # Write hook script and install
    hook_path = GUARD_DIR / "hook.py"
    hook_path.write_text(_HOOK_SCRIPT)
    hook_path.chmod(0o755)
    _install_claude_hook(hook_path)

    print(
        f"\n{BOLD}{GREEN}Guard active on {team_name}.{RESET} "
        f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} enforced. "
        f"Every Claude Code tool call is now checked."
    )


def cmd_guard_join(args):
    invite_code = args.invite_code

    # Prompt for email if not supplied
    email = getattr(args, "email", None) or input("Email address: ").strip()
    if not email:
        print(f"{RED}Email is required.{RESET}")
        sys.exit(1)

    # Use configured API URL or default
    existing_cfg = _load_guard_config()
    base_url     = existing_cfg.get("api_url", "https://api.conduct.ai").rstrip("/")

    print(f"\nJoining team with invite code {CYAN}{invite_code}{RESET}…")

    payload = {
        "invite_code": invite_code,
        "email":       email,
    }
    result = _req("POST", f"{base_url}/guard/teams/join", body=payload)

    team_id      = result["team_id"]
    team_name    = result.get("team_name", team_id)
    member_id    = result["member_id"]
    member_token = result.get("member_token", "")
    policy       = result.get("policy", {"team_id": team_id, "version": "", "rules": []})

    # Download and persist policy
    _save_policy(policy)
    rule_count = len(policy.get("rules", []))
    print(f"  {GREEN}Policy downloaded:{RESET} {rule_count} rule(s)")

    # Register MCP in all found tool configs
    registered = _register_mcp(team_id, member_token)
    new_tools   = [label for label, is_new in registered if is_new]
    all_tools   = [label for label, _ in registered]

    for label, is_new in registered:
        icon = f"{GREEN}registered{RESET}" if is_new else f"{GRAY}already registered{RESET}"
        print(f"  {label} -> {icon}")

    # Persist guard config
    cfg = {
        "team_id":    team_id,
        "team_name":  team_name,
        "member_id":  member_id,
        "user_email": email,
        "api_url":    base_url,
    }
    if member_token:
        cfg["member_token"] = member_token
    _save_guard_config(cfg)

    # Write hook script
    hook_path = GUARD_DIR / "hook.py"
    hook_path.write_text(_HOOK_SCRIPT)
    hook_path.chmod(0o755)
    print(f"  {GREEN}Hook script written:{RESET} {hook_path}")

    # Install PreToolUse hook in ~/.claude/settings.json
    _install_claude_hook(hook_path)

    print(
        f"\n{BOLD}{GREEN}Connected to {team_name}.{RESET} "
        f"{len(all_tools)} AI tool(s) registered. "
        f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} active."
    )


def cmd_guard_sync(args):
    cfg      = _require_guard_config()
    team_id  = cfg["team_id"]
    base_url = _api_url(cfg)
    auth     = _auth_kwargs(cfg)

    print(f"Syncing policy for team {CYAN}{cfg.get('team_name', team_id)}{RESET}…")

    policy = _req("GET", f"{base_url}/guard/policies/sync?team_id={team_id}", **auth)
    _save_policy(policy)
    rule_count = len(policy.get("rules", []))
    print(f"  {GREEN}Policy refreshed:{RESET} {rule_count} rule(s)")

    # Refresh hook script (picks up budget check and any other updates)
    hook_path = GUARD_DIR / "hook.py"
    hook_path.write_text(_HOOK_SCRIPT)
    hook_path.chmod(0o755)
    print(f"  {GREEN}Hook script updated{RESET}")

    print(f"\n{BOLD}Policy refreshed ({rule_count} rule(s)).{RESET}")


def cmd_guard_status(args):
    cfg        = _require_guard_config()
    team_id    = cfg["team_id"]
    user_email = cfg.get("user_email", "")
    team_name  = cfg.get("team_name", team_id)
    base_url   = _api_url(cfg)
    auth       = _auth_kwargs(cfg)

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
        spend = _req("GET", f"{base_url}/guard/spend?team_id={team_id}", **auth)
    except SystemExit:
        pass

    # Fetch recent violations (today)
    today_iso = datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    events: list = []
    try:
        events = _req(
            "GET",
            f"{base_url}/guard/events?team_id={team_id}&user_email={user_email}&since={today_iso}&limit=20",
            **auth,
        )
        if not isinstance(events, list):
            events = events.get("events", [])
    except SystemExit:
        pass

    violations = [e for e in events if e.get("decision") == "blocked"]

    # Format spend figures
    sessions     = spend.get("sessions", 0)
    tokens_used  = spend.get("tokens_used", 0)
    token_saved_pct = spend.get("token_saved_pct", 0)
    cost         = spend.get("cost_usd", 0.0)
    cost_saved   = spend.get("cost_saved_usd", 0.0)

    viol_summary = ""
    if violations:
        rule_names = ", ".join(
            v.get("rule", "unknown") for v in violations[:3]
        )
        viol_summary = f"  ({rule_names} — blocked)"

    print(f"\n{BOLD}Guard status{RESET} — {user_email}")
    print(f"Team: {team_name} · {rule_count} polic{'y' if rule_count == 1 else 'ies'} active")
    print()
    print(f"Today:")
    print(f"  Sessions: {sessions}")
    print(f"  Tokens used: {tokens_used:,}  (saved {token_saved_pct}% via optimization)")
    print(f"  Cost: ${cost:.2f}  (saved ${cost_saved:.2f})")
    print(f"  Violations: {len(violations)}{viol_summary}")
    print()


def cmd_guard_audit(args):
    cfg        = _require_guard_config()
    team_id    = cfg["team_id"]
    user_email = cfg.get("user_email", "")
    base_url   = _api_url(cfg)
    auth       = _auth_kwargs(cfg)

    since_str = getattr(args, "since", None) or "24h"
    since_iso = _parse_since(since_str)

    events_resp = _req(
        "GET",
        f"{base_url}/guard/events?team_id={team_id}&user_email={user_email}&since={since_iso}&limit=50",
        **auth,
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
        tool     = (ev.get("tool") or "—")[:tool_w - 1]
        action   = (ev.get("action") or "—")[:action_w - 1]
        decision = ev.get("decision", "—")
        rule     = ev.get("rule", "—")

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

    # conduct guard install
    install_p = guard_sub.add_parser("install", help="Install Guard using your API key (conduct login first)")
    install_p.add_argument("--api-key", dest="api_key", help="Override API key (default: from conduct login)")
    install_p.add_argument("--server",  help="Override API server URL")

    # conduct guard join <invite-code>
    join_p = guard_sub.add_parser("join", help="Join a second workspace via invite token (on-demand)")
    join_p.add_argument("invite_code", help="Team invite code")
    join_p.add_argument("--email", help="Your email address (prompted if omitted)")

    # conduct guard sync
    guard_sub.add_parser("sync", help="Refresh policy and re-scan for AI tools")

    # conduct guard status
    guard_sub.add_parser("status", help="Show today's spend and violations")

    # conduct guard audit [--since 7d]
    audit_p = guard_sub.add_parser("audit", help="Show recent guard events")
    audit_p.add_argument(
        "--since",
        default="24h",
        metavar="PERIOD",
        help="Time window: 1h, 24h, 7d, 30d (default: 24h)",
    )

    return guard_p, guard_sub


def dispatch_guard(args, guard_p):
    """Dispatch to the correct guard handler. Called from main()."""
    guard_command = getattr(args, "guard_command", None)
    if guard_command == "install":
        cmd_guard_install(args)
    elif guard_command == "join":
        cmd_guard_join(args)
    elif guard_command == "sync":
        cmd_guard_sync(args)
    elif guard_command == "status":
        cmd_guard_status(args)
    elif guard_command == "audit":
        cmd_guard_audit(args)
    else:
        guard_p.print_help()
        sys.exit(1)
