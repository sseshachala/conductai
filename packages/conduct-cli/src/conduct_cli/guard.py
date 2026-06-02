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

_HOOK_SCRIPT = '''\
#!/usr/bin/env python3
"""ConductGuard PreToolUse hook — enforces team policies, tracks all tool calls."""
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
    try:
        cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        return False, None
    workspace_id = cfg.get("workspace_id")
    api_url      = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    if not workspace_id:
        return False, None
    url = f"{api_url}/guard/spend/budget-check?workspace_id={workspace_id}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
            data = json.loads(resp.read())
        hard_blocked = data.get("hard_blocked", False)
        reason       = data.get("reason")
        BUDGET_CACHE_PATH.write_text(json.dumps({"ts": time.time(), "hard_blocked": hard_blocked, "reason": reason}))
        return hard_blocked, reason
    except Exception:
        return False, None


def _check_policy(tool_name, tool_input):
    """Return (matched_rule, action, rule_id, message) or (None, 'allow', None, None)."""
    if not POLICY_PATH.exists():
        return None, "allow", None, None
    try:
        policy = json.loads(POLICY_PATH.read_text())
    except Exception:
        return None, "allow", None, None

    rules      = policy.get("rules", [])
    input_text = json.dumps(tool_input)
    path_text  = " ".join(str(tool_input.get(f, "")) for f in ["file_path", "path", "command"])

    for rule in rules:
        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            if tool_name not in [t.strip() for t in match_tool.split(",")]:
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
        action  = rule.get("action", "audit")
        rule_id = rule.get("rule_id", "unknown")
        message = rule.get("message") or f"Policy violation: {rule_id}"
        return rule, action, rule_id, message

    return None, "allow", None, None


def _detect_ai_tool():
    import os
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    path = os.environ.get("PATH", "")
    if "Codex.app" in path or "codex" in path.lower():
        return "codex"
    if "cursor" in path.lower():
        return "cursor"
    if "windsurf" in path.lower():
        return "windsurf"
    return "unknown"


def _post_event(tool_name, tool_input, decision, rule_id=None, message=None, session_id=None):
    try:
        cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        return
    workspace_id = cfg.get("workspace_id")
    if not workspace_id:
        return

    payload = json.dumps({
        "workspace_id":  workspace_id,
        "clerk_user_id": cfg.get("user_email"),
        "user_email":    cfg.get("user_email"),
        "ai_tool":       _detect_ai_tool(),
        "tool_call":     tool_name,
        "input_summary": json.dumps(tool_input)[:200],
        "decision":      decision,
        "rule_id":       rule_id,
        "rule_message":      message,
        "hook_session_id":   session_id,
    })
    api_url = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    script = (
        "import urllib.request\\n"
        "try:\\n"
        f"    req = urllib.request.Request(\\"{api_url}/guard/events\\","
        f" data={repr(payload.encode())}, headers={{\\\"Content-Type\\\": \\\"application/json\\\"}}, method=\\"POST\\")\\n"
        "    urllib.request.urlopen(req, timeout=5)\\n"
        "except: pass\\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _post_usage(session_id, tool_name, tokens_input, tokens_output, duration_ms):
    """Fire-and-forget POST to /guard/events/usage"""
    try:
        cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        return
    workspace_id = cfg.get("workspace_id")
    if not workspace_id or not session_id:
        return
    payload = json.dumps({
        "workspace_id":    workspace_id,
        "hook_session_id": session_id,
        "tool_name":       tool_name,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "duration_ms": duration_ms,
        "ai_tool": _detect_ai_tool(),
    })
    api_url = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    script = (
        "import urllib.request\\n"
        "try:\\n"
        f"    req = urllib.request.Request(\\"{api_url}/guard/events/usage\\","
        f" data={repr(payload.encode())}, headers={{\\\"Content-Type\\\": \\\"application/json\\\"}}, method=\\"POST\\")\\n"
        "    urllib.request.urlopen(req, timeout=5)\\n"
        "except: pass\\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _tail_lines(path, n=200):
    """Read last n lines of a file efficiently without loading the whole file."""
    size = path.stat().st_size
    if size == 0:
        return []
    chunk = min(size, n * 300)  # ~300 bytes per line estimate
    with open(path, "rb") as f:
        f.seek(max(0, size - chunk))
        raw = f.read()
    text = raw.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    # If we didn't seek to start, first line may be partial — drop it
    if size > chunk:
        lines = lines[1:]
    return lines


def _read_tokens_from_transcript(transcript_path, tool_use_id):
    """Read token counts from Claude Code transcript (matched by tool_use_id)."""
    try:
        path = Path(transcript_path)
        if not path.exists() or not tool_use_id:
            return 0, 0
        lines = _tail_lines(path)
        for line in reversed(lines):
            if not line.strip() or "tool_use" not in line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            msg = entry.get("message") or {}
            usage = msg.get("usage")
            if not usage:
                continue
            content = msg.get("content") or []
            if any(
                isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") == tool_use_id
                for b in content
            ):
                total_in = (
                    usage.get("input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                )
                return total_in, usage.get("output_tokens", 0)
    except Exception:
        pass
    return 0, 0


def _scan_codex_tokens(transcript_path):
    """Robustly scan a Codex transcript for the last token_count event.

    Reads in 512 KB chunks from the end so it handles arbitrarily large
    tool-output lines without a fixed cutoff.
    """
    try:
        path = Path(transcript_path)
        if not path.exists():
            return 0, 0
        size = path.stat().st_size
        chunk_size = 524288  # 512 KB
        buf = b""
        pos = size
        while pos >= 0:
            read_size = min(chunk_size, pos)
            pos -= read_size
            with open(path, "rb") as f:
                f.seek(pos)
                buf = f.read(read_size) + buf
            text = buf.decode("utf-8", errors="ignore")
            # Split; if we haven't reached the start the first fragment may be partial
            parts = text.split("\n")
            start = 1 if pos > 0 else 0
            for line in reversed(parts[start:]):
                if "token_count" not in line or not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "event_msg":
                        info = entry.get("payload", {}).get("info", {})
                        usage = info.get("last_token_usage", {})
                        if usage:
                            total_in  = usage.get("input_tokens", 0)
                            total_out = (usage.get("output_tokens", 0)
                                         + usage.get("reasoning_output_tokens", 0))
                            return total_in, total_out
                except Exception:
                    continue
            if pos == 0:
                break
    except Exception:
        pass
    return 0, 0


def post_codex_main():
    """Delayed Codex token reader — spawned as background by post_usage_main.

    Reads args from a pending JSON file, sleeps 2 s to let Codex flush the
    token_count event, then scans the transcript and POSTs to the API.
    """
    import time
    if len(sys.argv) < 3:
        sys.exit(0)
    pending_path = Path(sys.argv[2])
    try:
        args = json.loads(pending_path.read_text())
        pending_path.unlink(missing_ok=True)
    except Exception:
        sys.exit(0)
    time.sleep(2)
    transcript_path = args.get("transcript_path", "")
    tokens_in, tokens_out = _scan_codex_tokens(transcript_path)
    if tokens_in or tokens_out:
        _post_usage(args.get("session_id"), args.get("tool_name"),
                    tokens_in, tokens_out, None)
    sys.exit(0)


def post_usage_main():
    """PostToolUse hook entrypoint — exits immediately; heavy work is async."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    session_id      = data.get("session_id")
    tool_name       = (data.get("tool_name") or "").lower()
    tool_use_id     = data.get("tool_use_id")
    transcript_path = data.get("transcript_path")
    is_codex = (tool_use_id or "").startswith("call_")

    if is_codex and transcript_path:
        # Write pending args; spawn delayed background reader so hook exits instantly
        import uuid as _uuid
        pending = GUARD_DIR / f"codex_pending_{_uuid.uuid4().hex[:8]}.json"
        try:
            pending.write_text(json.dumps({
                "session_id": session_id,
                "tool_name": tool_name,
                "transcript_path": transcript_path,
            }))
            hook_path = Path(__file__).resolve()
            subprocess.Popen(
                [sys.executable, str(hook_path), "post-codex", str(pending)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
    elif transcript_path:
        tokens_input, tokens_output = _read_tokens_from_transcript(transcript_path, tool_use_id)
        _post_usage(session_id, tool_name, tokens_input, tokens_output, None)

    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Hard budget cap (cached 5 min)
    hard_blocked, reason = _load_budget_cache()
    if hard_blocked is None:
        hard_blocked, reason = _fetch_budget_status()
    if hard_blocked:
        print(f"[ConductGuard] {reason or 'Budget hard cap reached. Contact your manager.'}")
        sys.exit(2)

    session_id = data.get("session_id")
    tool_name  = (data.get("tool_name") or "").lower()
    tool_input = data.get("tool_input") or {}

    _, action, rule_id, message = _check_policy(tool_name, tool_input)

    # Always post an event — "allowed" for normal calls, "blocked"/"warned" for violations
    decision = {"block": "blocked", "warn": "warned", "approval": "blocked"}.get(action, "allowed")
    _post_event(tool_name, tool_input, decision, rule_id, message, session_id=session_id)

    if action == "block":
        print(f"[ConductGuard] {message}")
        sys.exit(2)
    if action in ("warn", "approval"):
        print(f"[ConductGuard] {message}")

    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "post":
        post_usage_main()
    elif len(sys.argv) > 1 and sys.argv[1] == "post-codex":
        post_codex_main()
    else:
        main()
'''

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
        print(f"{RED}Guard not connected. Run: conduct login --api-key <key>{RESET}")
        sys.exit(1)
    if not cfg.get("api_key"):
        print(f"{RED}Guard config is missing API key. Re-run: conduct login --api-key <key>{RESET}")
        sys.exit(1)
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
    """Write conductguard MCP entry into every AI tool config found on this machine."""
    entry = {
        "command": "conductguard-mcp",
        "args": ["--workspace", workspace_id, "--token", member_token, "--api-url", api_url],
    }
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
        if mcp.get("conductguard", {}).get("args") == entry["args"]:
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
    pre_cmd = f"python3 {hook_path}"
    pre = hook_section.setdefault("PreToolUse", [])
    pre_already = any(
        e.get("command") == pre_cmd
        for h in pre
        for e in h.get("hooks", [])
    )
    changed = False
    if not pre_already:
        pre.append({"matcher": ".*", "hooks": [{"type": "command", "command": pre_cmd}]})
        changed = True

    # PostToolUse — self-contained: python3 /path/hook.py post (no PATH dependency)
    post_cmd = f"python3 {hook_path} post"
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
        e.get("command") == post_cmd
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
    pre_cmd = f"python3 {hook_path}"
    pre_already = any(
        e.get("command") == pre_cmd
        for h in pre
        for e in h.get("hooks", [])
    )
    changed = False
    if not pre_already:
        pre.append({"matcher": ".*", "hooks": [{"type": "command", "command": pre_cmd}]})
        changed = True

    # PostToolUse — self-contained: python3 /path/hook.py post (no PATH dependency)
    post = hooks.setdefault("PostToolUse", [])
    post_cmd = f"python3 {hook_path} post"
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
        e.get("command") == post_cmd
        for h in post
        for e in h.get("hooks", [])
    )
    if not post_already:
        post.append({"matcher": ".*", "hooks": [{"type": "command", "command": post_cmd}]})
        changed = True
    if cleaned:
        changed = True

    if changed:
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        claude_settings.write_text(json.dumps(settings, indent=2))
        if not pre_already:
            print(f"  {GREEN}Claude Code PreToolUse hook registered{RESET}")
        if not post_already or cleaned:
            print(f"  {GREEN}Claude Code PostToolUse hook registered{RESET}")
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

    member_token = result.get("member_token") or ""
    user_email   = result.get("user_email") or ""

    # Persist guard config — include api_key so CLI commands can authenticate
    _save_guard_config({
        "workspace_id": workspace_id,
        "member_token": member_token,
        "user_email":   user_email,
        "api_key":      api_key,
        "api_url":      server,
    })

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
    hook_path.write_text(_HOOK_SCRIPT)
    hook_path.chmod(0o755)

    # Install PreToolUse hooks — Claude Code + Codex (real interception)
    _install_claude_hook(hook_path)
    _install_codex_hook(hook_path)

    # Register MCP in all found AI tools — Cursor/Windsurf (advisory)
    _register_mcp(workspace_id, member_token or "", server)


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
    hook_path.write_text(_HOOK_SCRIPT)
    hook_path.chmod(0o755)
    print(f"  {GREEN}Hook script written:{RESET} {hook_path}")

    # Install PreToolUse hook in ~/.claude/settings.json
    _install_claude_hook(hook_path)

    print(
        f"\n{BOLD}{GREEN}Guard connected.{RESET} "
        f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} active.\n"
        f"Your AI tool calls will now be checked against team policies."
    )


def cmd_guard_sync(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    api_key      = cfg.get("api_key", "")
    base_url     = _api_url(cfg)

    print(f"Syncing policy…")

    policy = _req(
        "GET",
        f"{base_url}/guard/policies/sync?workspace_id={workspace_id}",
        api_key=api_key,
    )
    _save_policy(policy)
    rule_count = len(policy.get("rules", []))
    print(f"  {GREEN}Policy refreshed:{RESET} {rule_count} rule(s)")

    # Refresh hook script + re-register in all tools
    hook_path = GUARD_DIR / "hook.py"
    hook_path.write_text(_HOOK_SCRIPT)
    hook_path.chmod(0o755)
    _install_claude_hook(hook_path)
    _install_codex_hook(hook_path)
    cfg2 = _load_guard_config()
    _register_mcp(workspace_id, cfg2.get("member_token", ""), base_url)
    print(f"  {GREEN}Hook script updated{RESET}")

    print(f"\n{BOLD}Policy refreshed ({rule_count} rule(s)).{RESET}")


def cmd_guard_status(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    user_email   = cfg.get("user_email", "")
    api_key      = cfg.get("api_key", "")
    base_url     = _api_url(cfg)

    # Auto-refresh user_email into config if it was installed before this was wired up
    if not user_email and api_key:
        try:
            installed = _req("GET", f"{base_url}/guard/config/installed", api_key=api_key)
            fetched_email = installed.get("user_email") or ""
            if fetched_email:
                cfg["user_email"] = fetched_email
                _save_guard_config(cfg)
                # Rewrite hook script so future events carry the email
                hook_path = GUARD_DIR / "hook.py"
                hook_path.write_text(_HOOK_SCRIPT)
                hook_path.chmod(0o755)
                user_email = fetched_email
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
    if guard_command == "sync":
        cmd_guard_sync(args)
    elif guard_command == "status":
        cmd_guard_status(args)
    elif guard_command == "audit":
        cmd_guard_audit(args)
    else:
        guard_p.print_help()
        sys.exit(1)
