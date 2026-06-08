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

GUARD_DIR           = Path.home() / ".conductguard"
POLICY_PATH         = GUARD_DIR / "policy.json"
CONFIG_PATH         = GUARD_DIR / "config.json"
BUDGET_CACHE_PATH   = GUARD_DIR / "budget_cache.json"
BUDGET_CACHE_TTL    = 300  # 5 minutes
VERSION_CACHE_PATH  = GUARD_DIR / "version_cache.json"
VERSION_CACHE_TTL   = 60   # 1 minute — matches server poll window


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


SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{20,}",          "secret-leak",    "high",     "Potential OpenAI/Anthropic API key"),
    (r"ghp_[A-Za-z0-9]{36}",           "secret-leak",    "high",     "GitHub Personal Access Token"),
    (r"AKIA[0-9A-Z]{16}",              "secret-leak",    "critical", "AWS Access Key ID"),
    (r"Bearer\s+[A-Za-z0-9+/=]{20,}",  "secret-leak",    "high",     "Bearer token in output"),
    (r"""password\s*=\s*['"][^'"]{4,}""","secret-leak",  "high",     "Hardcoded password"),
    (r"""api[_-]?key\s*=\s*['"][^'"]{4,}""","secret-leak","high",    "Hardcoded API key"),
    (r"\.\./\.\./\.\./",               "path-traversal", "medium",   "Path traversal sequence"),
    (r"file://",                        "path-traversal", "medium",   "File URI scheme in output"),
    (r"\beval\s*\(",                    "injection",      "high",     "eval() in output"),
    (r"\bexec\s*\(",                    "injection",      "high",     "exec() in output"),
    (r"\b__import__\s*\(",              "injection",      "high",     "__import__() in output"),
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

    Handles two formats:
    - Read tool output: '     N\\tcode line'  (cat -n style)
    - Plain text: count newlines before match offset
    """
    import re as _re
    if not matched_pattern:
        return None
    try:
        # Try cat-n format first (Read tool)
        for raw_line in text.split("\n"):
            m = _re.match(r"^\s*(\d+)\t(.*)$", raw_line)
            if m:
                lineno, content = int(m.group(1)), m.group(2)
                try:
                    if _re.search(matched_pattern, content, _re.IGNORECASE):
                        return lineno
                except Exception:
                    if matched_pattern.lower() in content.lower():
                        return lineno
        # Fallback: count newlines before the first match
        m = _re.search(matched_pattern, text, _re.IGNORECASE)
        if m:
            return text[:m.start()].count("\n") + 1
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
        "import urllib.request\\n"
        "try:\\n"
        f"    req = urllib.request.Request(\\"{api_url}/security-findings?workspace_id={workspace_id}\\","
        f" data={repr(payload.encode())}, headers={{\\\"Content-Type\\\": \\\"application/json\\\","
        f" \\\"X-Api-Key\\\": \\\"{api_key}\\\"}}, method=\\"POST\\")\\n"
        "    urllib.request.urlopen(req, timeout=5)\\n"
        "except: pass\\n"
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
            parts = text.split("\\n")
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
'''

_PRECOMPACT_HOOK_SCRIPT = '''\
#!/usr/bin/env python3
"""ConductGuard PreCompact hook — persists session context before compaction."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

GUARD_DIR = Path.home() / ".conductguard"
SNAPSHOT_PATH = GUARD_DIR / "session_snapshot.json"


def _git(cmd):
    try:
        return subprocess.check_output(
            ["git"] + cmd, stderr=subprocess.DEVNULL, text=True, timeout=3
        ).strip()
    except Exception:
        return ""


def _guard_status():
    try:
        out = subprocess.check_output(
            ["conductguard", "status", "--json"],
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        )
        return json.loads(out.strip())
    except Exception:
        return None


def _memory_headline():
    try:
        root = Path.cwd()
        mem_key = str(root).replace("/", "-").lstrip("-")
        mem_path = Path.home() / ".claude" / "projects" / mem_key / "memory" / "MEMORY.md"
        if mem_path.exists():
            return "\\n".join(mem_path.read_text().splitlines()[:10])
    except Exception:
        pass
    return ""


def main():
    try:
        sys.stdin.read()
    except Exception:
        pass

    try:
        GUARD_DIR.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "compacted_at": datetime.now(timezone.utc).isoformat(),
            "tier1": {
                "git_branch": _git(["branch", "--show-current"]),
                "recent_commits": _git(["log", "--oneline", "-3"]),
                "memory_headline": _memory_headline(),
            },
            "tier2": {"guard_status": _guard_status()},
            "tier3": {"cwd": str(Path.cwd()), "python": sys.version.split()[0]},
        }
        tmp = GUARD_DIR / "session_snapshot.tmp"
        tmp.write_text(json.dumps(snapshot, indent=2))
        tmp.rename(SNAPSHOT_PATH)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
'''

_SESSION_START_HOOK_SCRIPT = '''\
#!/usr/bin/env python3
"""ConductGuard SessionStart hook — prints context after compaction."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_PATH = Path.home() / ".conductguard" / "session_snapshot.json"
MAX_AGE_HOURS = 2


def main():
    try:
        sys.stdin.read()
    except Exception:
        pass

    if not SNAPSHOT_PATH.exists():
        sys.exit(0)

    try:
        snapshot = json.loads(SNAPSHOT_PATH.read_text())
        compacted_at = datetime.fromisoformat(snapshot.get("compacted_at", ""))
        age_hours = (datetime.now(timezone.utc) - compacted_at).total_seconds() / 3600
        if age_hours > MAX_AGE_HOURS:
            sys.exit(0)

        t1 = snapshot.get("tier1", {})
        branch = t1.get("git_branch", "")
        commits = t1.get("recent_commits", "")
        headline = t1.get("memory_headline", "")
        t2 = snapshot.get("tier2", {})
        guard = t2.get("guard_status") or {}

        lines = [f"## Session resumed (snapshot from {compacted_at.strftime(\'%Y-%m-%d %H:%M\')} UTC)"]
        if branch:
            last = commits.splitlines()[0] if commits else ""
            lines.append(f"- Branch: {branch}" + (f" | Last: {last}" if last else ""))
        budget = guard.get("budget_pct")
        if budget is not None:
            lines.append(f"- Guard: {budget}% budget used")
        else:
            lines.append("- Guard: state unavailable")
        if headline:
            lines.append(f"- Memory index:\\n  {headline}")
        else:
            lines.append("- Memory index:\\n  (none)")

        print("\\n".join(lines))
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
'''


# ── Policy engine (also embedded in _HOOK_SCRIPT for standalone use) ──────────

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
    """Write _HOOK_SCRIPT to path, then py_compile-validate it.
    Raises RuntimeError if the written file fails to compile — prevents
    silently deploying a syntactically broken hook."""
    import py_compile, tempfile, os
    path.write_text(_HOOK_SCRIPT)
    path.chmod(0o755)
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"hook.py failed syntax check after write — hook NOT installed.\n{exc}"
        ) from exc


def _install_session_hooks() -> None:
    """Write PreCompact + SessionStart hook scripts and register them in ~/.claude/settings.json."""
    python = _best_python()

    precompact_path = GUARD_DIR / "guard-precompact.py"
    session_start_path = GUARD_DIR / "guard-session-start.py"

    precompact_path.write_text(_PRECOMPACT_HOOK_SCRIPT)
    precompact_path.chmod(0o755)
    session_start_path.write_text(_SESSION_START_HOOK_SCRIPT)
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

    # Capture savings from RTK and Agent Booster
    _report_savings(cfg, base_url, api_key)

    # Report AI tool coverage
    try:
        _report_tools_to_server()
    except Exception:
        pass

    print(f"\n{BOLD}Policy refreshed ({rule_count} rule(s)).{RESET}")


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

    return guard_p, guard_sub


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
    else:
        guard_p.print_help()
        sys.exit(1)
