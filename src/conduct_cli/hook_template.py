#!/usr/bin/env python3
"""ConductGuard PreToolUse hook — enforces team policies, tracks all tool calls."""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_FLUSH_INTERVAL = 8 * 3600
_FLUSH_STAMP = Path.home() / ".conduct" / "last_memory_flush"


def _should_periodic_flush() -> bool:
    try:
        if not _FLUSH_STAMP.exists():
            return True
        return time.time() - float(_FLUSH_STAMP.read_text().strip()) >= _FLUSH_INTERVAL
    except Exception:
        return True


def _mark_flushed() -> None:
    try:
        _FLUSH_STAMP.parent.mkdir(parents=True, exist_ok=True)
        _FLUSH_STAMP.write_text(str(time.time()))
    except Exception:
        pass


GUARD_DIR           = Path.home() / ".conductguard"
POLICY_PATH         = GUARD_DIR / "policy.json"
CONFIG_PATH         = GUARD_DIR / "config.json"
BUDGET_CACHE_PATH   = GUARD_DIR / "budget_cache.json"
BUDGET_CACHE_TTL    = 300  # 5 minutes
VERSION_CACHE_PATH  = GUARD_DIR / "version_cache.json"
VERSION_CACHE_TTL   = 60   # 1 minute — matches server poll window
WARNED_RULES_PATH   = GUARD_DIR / "warned_rules.json"


def _maybe_sync_policy():
    """Check server policy version once per minute; re-download if stale. Never raises."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
        workspace_id = cfg.get("workspace_id")
        api_key      = cfg.get("api_key", "")
        api_url      = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
        if not workspace_id:
            return
        # Check cache TTL
        if VERSION_CACHE_PATH.exists():
            cache = json.loads(VERSION_CACHE_PATH.read_text())
            if time.time() - cache.get("ts", 0) < VERSION_CACHE_TTL:
                return
        # Fetch current version from server
        url = f"{api_url}/guard/policies/sync?workspace_id={workspace_id}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"} if api_key else {})
        with urllib.request.urlopen(req, timeout=2) as resp:
            remote = json.loads(resp.read())
        remote_version = remote.get("version", "")
        # Compare to local
        local_version = ""
        if POLICY_PATH.exists():
            local_version = json.loads(POLICY_PATH.read_text()).get("version", "")
        if remote_version != local_version:
            POLICY_PATH.write_text(json.dumps(remote, indent=2))
        VERSION_CACHE_PATH.write_text(json.dumps({"ts": time.time(), "version": remote_version}))
    except Exception:
        pass  # Never block a tool call due to sync failure


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
    workspace_id  = cfg.get("workspace_id")
    clerk_user_id = cfg.get("clerk_user_id") or ""
    api_url       = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    if not workspace_id:
        return False, None
    url = f"{api_url}/guard/spend/budget-check?workspace_id={workspace_id}"
    if clerk_user_id:
        url += f"&clerk_user_id={clerk_user_id}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
            data = json.loads(resp.read())
        hard_blocked = data.get("hard_blocked", False)
        reason       = data.get("reason")
        BUDGET_CACHE_PATH.write_text(json.dumps({"ts": time.time(), "hard_blocked": hard_blocked, "reason": reason}))
        return hard_blocked, reason
    except Exception:
        return False, None


try:
    from conduct_cli.guard import _check_policy
except Exception:
    def _check_policy(tool_name, tool_input, tokens_before=0):
        """Return (matched_rule, action, rule_id, message) or (None, 'allow', None, None)."""
        if not POLICY_PATH.exists():
            return None, "allow", None, None
        try:
            policy = json.loads(POLICY_PATH.read_text())
        except Exception:
            return None, "allow", None, None

        rules      = policy.get("rules", [])
        input_text = json.dumps(tool_input)
        path_fields = [str(tool_input.get(f, "")) for f in ["file_path", "path", "command"]]

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
                    if not any(re.search(path_pattern, f, re.IGNORECASE) for f in path_fields if f):
                        continue
                except re.error:
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


def _detect_repo() -> str | None:
    try:
        import subprocess
        out = subprocess.check_output(["git", "remote", "get-url", "origin"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
        # github.com/owner/repo or git@github.com:owner/repo
        if "github.com" in out:
            parts = out.split("github.com")[-1].lstrip("/:").rstrip(".git")
            return parts  # owner/repo
    except Exception:
        pass
    return None


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


def _already_warned_this_session(session_id: str, rule_id: str) -> bool:
    """Return True if this rule already fired a warning in the current session."""
    try:
        data = json.loads(WARNED_RULES_PATH.read_text()) if WARNED_RULES_PATH.exists() else {}
    except Exception:
        data = {}
    return rule_id in data.get(session_id, [])


def _record_session_warn(session_id: str, rule_id: str) -> None:
    try:
        data = json.loads(WARNED_RULES_PATH.read_text()) if WARNED_RULES_PATH.exists() else {}
    except Exception:
        data = {}
    data.setdefault(session_id, [])
    if rule_id not in data[session_id]:
        data[session_id].append(rule_id)
    # Trim to last 50 sessions to prevent unbounded growth
    if len(data) > 50:
        oldest = list(data.keys())[:-50]
        for k in oldest:
            del data[k]
    try:
        GUARD_DIR.mkdir(parents=True, exist_ok=True)
        WARNED_RULES_PATH.write_text(json.dumps(data))
    except Exception:
        pass


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
        "import urllib.request\n"
        "try:\n"
        f"    req = urllib.request.Request(\"{api_url}/guard/events\","
        f" data={repr(payload.encode())}, headers={{\"Content-Type\": \"application/json\"}}, method=\"POST\")\n"
        "    urllib.request.urlopen(req, timeout=5)\n"
        "except: pass\n"
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
        "import urllib.request\n"
        "try:\n"
        f"    req = urllib.request.Request(\"{api_url}/guard/events/usage\","
        f" data={repr(payload.encode())}, headers={{\"Content-Type\": \"application/json\"}}, method=\"POST\")\n"
        "    urllib.request.urlopen(req, timeout=5)\n"
        "except: pass\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{20,}",          "secret-leak",    "high",     "Potential OpenAI/Anthropic API key"),
    (r"ghp_[A-Za-z0-9]{36}",           "secret-leak",    "high",     "GitHub Personal Access Token"),
    (r"AKIA[0-9A-Z]{16}",              "secret-leak",    "critical", "AWS Access Key ID"),
    (r"Bearer\s+[A-Za-z0-9+/=]{20,}",  "secret-leak",    "high",     "Bearer token in output"),
    (r"""password\s*=\s*['"][^'"]{4,}""","secret-leak",  "high",     "Hardcoded password"),
    (r"""api[_-]?key\s*=\s*['"][^'"]{4,}""","secret-leak","high",    "Hardcoded API key"),
    (r"\.\./\.\./\.\./",               "path-traversal", "medium",   "Path traversal sequence"),
    (r"file://",                        "path-traversal", "medium",   "File URI scheme in output"),
    (r"eval\s*\(",                    "injection",      "high",     "eval() in output"),
    (r"exec\s*\(",                    "injection",      "high",     "exec() in output"),
    (r"__import__\s*\(",              "injection",      "high",     "__import__() in output"),
    (r"ssl\.CERT_NONE",                 "crypto",         "high",     "SSL verification disabled"),
    (r"verify\s*=\s*False",             "crypto",         "medium",   "TLS verification bypassed"),
]
OWASP_KEYWORDS = [
    ("sql injection",    "injection",   "high",   "SQL injection mentioned in AI output"),
    ("cross-site scripting","injection","high",   "XSS mentioned in AI output"),
    (" xss ",            "injection",   "high",   "XSS mentioned in AI output"),
    ("idor",             "injection",   "medium", "IDOR mentioned in AI output"),
    ("ssrf",             "injection",   "high",   "SSRF mentioned in AI output"),
    ("command injection","injection",   "high",   "Command injection mentioned in AI output"),
    ("auth bypass",      "auth-bypass", "high",   "Auth bypass mentioned in AI output"),
]


def _classify_text(text):
    """Return (finding_type, severity, description, matched_pattern) or (None,...) if clean."""
    import re as _re
    for pattern, ftype, sev, desc in SECRET_PATTERNS:
        if _re.search(pattern, text, _re.IGNORECASE):
            return ftype, sev, desc, pattern
    lower = text.lower()
    for kw, ftype, sev, desc in OWASP_KEYWORDS:
        if kw in lower:
            return ftype, sev, desc, kw
    return None, None, None, None


def _line_number_from_text(text, matched_pattern):
    """Extract line number where pattern matched.
    Uses splitlines() and chr(10) — no backslash-n literals (safe inside _HOOK_SCRIPT).
    """
    import re as _re
    if not matched_pattern:
        return None
    try:
        # Try cat-n format first (Read tool outputs '   N<TAB>code line')
        for raw_line in text.splitlines():
            m = _re.match(r"^\s*(\d+)	(.*)$", raw_line)
            if m:
                lineno, content = int(m.group(1)), m.group(2)
                try:
                    if _re.search(matched_pattern, content, _re.IGNORECASE):
                        return lineno
                except Exception:
                    if matched_pattern.lower() in content.lower():
                        return lineno
        # Fallback: count lines before the first match offset
        m = _re.search(matched_pattern, text, _re.IGNORECASE)
        if m:
            return text[:m.start()].count(chr(10)) + 1
    except Exception:
        pass
    return None


def _maybe_emit_security_finding(tool_response, session_id, tool_name, tool_input=None):
    """Classify tool output + input for security findings; POST if flag ON. Never raises."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        return
    if not cfg.get("security_emit_enabled", False):
        return
    workspace_id = cfg.get("workspace_id")
    api_key = cfg.get("api_key", "")
    api_url = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    if not workspace_id:
        return

    ti = tool_input or {}

    # Build scan candidates: (text_to_scan, source_label)
    # Priority: tool_response first (Read), then written content (Edit/Write), then command (Bash)
    candidates = [("response", str(tool_response))]
    if tool_name in ("edit", "multiedit"):
        candidates.append(("input", ti.get("new_string", "")))
    elif tool_name == "write":
        candidates.append(("input", ti.get("content", "")))
    elif tool_name in ("bash", "terminal"):
        candidates.append(("input", ti.get("command", "")))

    finding_type = severity = description = matched_pattern = scan_text = None
    for _src, text in candidates:
        ft, sv, desc, pat = _classify_text(text)
        if ft:
            finding_type, severity, description, matched_pattern, scan_text = ft, sv, desc, pat, text
            break

    if not finding_type:
        return

    # File path
    file_path = (
        ti.get("file_path") or ti.get("path") or
        (ti.get("command", "")[:120] if tool_name in ("bash", "terminal") else None)
    ) or None

    # Line number
    line_no = _line_number_from_text(scan_text, matched_pattern) if scan_text else None

    payload = json.dumps({
        "tool": _detect_ai_tool(),
        "severity": severity,
        "type": finding_type,
        "description": description,
        "source_run_id": session_id,
        "reporter_email": cfg.get("user_email") or "",
        "file": file_path,
        "line": line_no,
    })
    script = (
        "import urllib.request\n"
        "try:\n"
        f"    req = urllib.request.Request(\"{api_url}/security-findings?workspace_id={workspace_id}\","
        f" data={repr(payload.encode())}, headers={{\"Content-Type\": \"application/json\","
        f" \"X-Api-Key\": \"{api_key}\"}}, method=\"POST\")\n"
        "    urllib.request.urlopen(req, timeout=5)\n"
        "except: pass\n"
    )
    try:
        subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


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
        # Token-threshold policy check (PostToolUse only — tokens not known at PreToolUse)
        _, action, rule_id, message = _check_policy(tool_name, {}, tokens_before=tokens_input)
        if action in ("warn", "block"):
            decision = "warned" if action == "warn" else "blocked"
            if action == "warn" and session_id and rule_id and _already_warned_this_session(session_id, rule_id):
                pass  # already warned once this session — skip
            else:
                if action == "warn" and session_id and rule_id:
                    _record_session_warn(session_id, rule_id)
                _post_event(tool_name, {}, decision, rule_id, message, session_id=session_id)

    # Security classifier runs regardless of transcript_path — scan every tool response
    tool_response = data.get("tool_response") or data.get("output") or ""
    tool_input    = data.get("tool_input") or {}
    _maybe_emit_security_finding(str(tool_response), session_id, tool_name, tool_input)

    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Stop hook — session ended, capture for team memory
    if data.get("hook_event_name") == "Stop" or data.get("stop_hook_active"):
        session_id = data.get("session_id", "")
        transcript_path = data.get("transcript_path")
        repo = _detect_repo()
        from conduct_cli.memory import post_session_to_api
        post_session_to_api(session_id, transcript_path, repo)
        _mark_flushed()
        sys.exit(0)

    # Periodic flush — fire at most once every 8 hours mid-session
    if _should_periodic_flush():
        session_id = data.get("session_id", "")
        transcript_path = data.get("transcript_path")
        repo = _detect_repo()
        from conduct_cli.memory import post_session_to_api
        post_session_to_api(session_id, transcript_path, repo)
        _mark_flushed()

    # Policy version check (cached 60s) — auto-syncs if server version differs
    _maybe_sync_policy()

    # Hard budget cap (cached 5 min)
    hard_blocked, reason = _load_budget_cache()
    if hard_blocked is None:
        hard_blocked, reason = _fetch_budget_status()
    if hard_blocked:
        msg = f"[ConductGuard] {reason or 'Budget hard cap reached. Contact your manager.'}"
        print(msg)
        print(msg, file=sys.stderr)
        tool_name  = (data.get("tool_name") or "").lower()
        tool_input = data.get("tool_input") or {}
        session_id = data.get("session_id")
        _post_event(tool_name, tool_input, "blocked", "budget-hard-cap", reason or "Monthly budget hard cap reached.", session_id=session_id)
        sys.exit(2)

    session_id = data.get("session_id")
    tool_name  = (data.get("tool_name") or "").lower()
    tool_input = data.get("tool_input") or {}

    _, action, rule_id, message = _check_policy(tool_name, tool_input)

    # Always post an event — "allowed" for normal calls, "blocked"/"warned" for violations
    decision = {"block": "blocked", "warn": "warned", "approval": "blocked"}.get(action, "allowed")
    if action == "warn" and session_id and rule_id and _already_warned_this_session(session_id, rule_id):
        sys.exit(0)  # already warned once this session — skip silently
    if action == "warn" and session_id and rule_id:
        _record_session_warn(session_id, rule_id)
    _post_event(tool_name, tool_input, decision, rule_id, message, session_id=session_id)

    if action == "block":
        msg = f"[ConductGuard] {message}"
        print(msg)
        print(msg, file=sys.stderr)
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
