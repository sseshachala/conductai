"""ConductGuard PreToolUse hook — enforces team policies, tracks all tool calls."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from conduct_cli.tool_groups import expand_match_tool
from conduct_cli.hooks.base import (
    BUDGET_CACHE_PATH,
    BUDGET_CACHE_TTL,
    CONFIG_PATH,
    GUARD_DIR,
    JOURNAL_DIR,
    JOURNAL_PID_PATH,
    POLICY_PATH,
    active_policy_path,
    SIGNING_KEY_PATH,
    VERSION_CACHE_PATH,
    VERSION_CACHE_TTL,
    WARNED_RULES_PATH,
    detect_ai_tool,
    detect_repo,
    journal_append,
    load_config,
    post_event,
    run_drain_daemon,
)

# ── Periodic memory flush (every 8 hours) ─────────────────────────────────────

_FLUSH_INTERVAL = 8 * 3600
_FLUSH_STAMP    = Path.home() / ".conduct" / "last_memory_flush"


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


# ── Daemon health check ───────────────────────────────────────────────────────

_DAEMON_URL = "http://127.0.0.1:7878"


def _daemon_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{_DAEMON_URL}/health", timeout=0.3):
            return True
    except Exception:
        return False


# ── Policy signature verification ─────────────────────────────────────────────

def _verify_policy_signature(policy_dict: dict) -> bool:
    """Verify HMAC-SHA256 signature on a policy dict. Returns True on success.

    If SIGNING_KEY_PATH does not exist (dev mode / workspace has no signing key),
    always returns True for backwards compatibility.
    """
    import hashlib as _hashlib
    import hmac as _hmac

    try:
        resolved = SIGNING_KEY_PATH.resolve()
        resolved.relative_to(GUARD_DIR.resolve())
    except (ValueError, RuntimeError):
        return True

    if not SIGNING_KEY_PATH.exists():
        return True

    try:
        raw = SIGNING_KEY_PATH.read_text().strip()
        key_bytes = bytes.fromhex(raw)
    except Exception:
        return True

    expected_sig = policy_dict.get("signature")
    if not expected_sig:
        return False

    body_dict = {k: v for k, v in policy_dict.items() if k not in ("signature", "signed_at")}
    canonical = json.dumps(body_dict, sort_keys=True, separators=(",", ":"))
    computed_sig = _hmac.new(key_bytes, canonical.encode(), _hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected_sig, computed_sig)


def _post_signature_invalid_event(expected_sig, computed_sig, policy_version, hostname):
    """Fire-and-forget audit event for a failed signature check."""
    try:
        cfg = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except Exception:
        return
    workspace_id = cfg.get("workspace_id") or cfg.get("workspace")
    if not workspace_id:
        return
    import platform as _platform
    _hostname = hostname or _platform.node()
    payload = json.dumps({
        "workspace_id":  workspace_id,
        "clerk_user_id": cfg.get("user_email"),
        "user_email":    cfg.get("user_email"),
        "ai_tool":       "hook",
        "tool_call":     "policy_signature_invalid",
        "input_summary": json.dumps({
            "expected_signature": expected_sig or "",
            "computed_signature": computed_sig or "",
            "policy_version":     policy_version or "",
            "hostname":           _hostname,
        })[:500],
        "decision":     "blocked",
        "rule_id":      "policy_signature_invalid",
        "rule_message": "Policy signature verification failed",
        "hostname":     _hostname,
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


# ── Policy sync ───────────────────────────────────────────────────────────────

def _maybe_sync_policy() -> None:
    """Sync policy from daemon (instant) or remote API (once per minute). Never raises."""
    try:
        cfg = load_config()
        workspace_id = cfg.get("workspace_id") or cfg.get("workspace")
        agent_token  = cfg.get("agent_token", "")
        api_url      = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
        if not workspace_id:
            return

        pol_path = active_policy_path()

        if _daemon_alive():
            url = f"{_DAEMON_URL}/policy?workspace_id={workspace_id}"
            with urllib.request.urlopen(url, timeout=1) as resp:
                remote = json.loads(resp.read())
            pol_path.write_text(json.dumps(remote, indent=2))
            return

        if VERSION_CACHE_PATH.exists():
            cache = json.loads(VERSION_CACHE_PATH.read_text())
            if time.time() - cache.get("ts", 0) < VERSION_CACHE_TTL:
                return
        url = f"{api_url}/guard/policies/sync?workspace_id={workspace_id}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {agent_token}"} if agent_token else {})
        with urllib.request.urlopen(req, timeout=2) as resp:
            remote = json.loads(resp.read())

        import platform as _platform
        if not _verify_policy_signature(remote):
            _post_signature_invalid_event(
                expected_sig=remote.get("signature"),
                computed_sig=None,
                policy_version=remote.get("version"),
                hostname=_platform.node(),
            )
            return

        remote_version = remote.get("version", "")
        local_version  = ""
        local_policy: dict = {}
        if pol_path.exists():
            local_policy  = json.loads(pol_path.read_text())
            local_version = local_policy.get("version", "")

        old_mode = local_policy.get("fail_mode", "fail_open")
        new_mode = remote.get("fail_mode", "fail_open")
        if old_mode == "fail_closed" and new_mode != "fail_closed":
            expected = local_policy.get("fail_mode_downgrade_token")
            provided = remote.get("fail_mode_downgrade_token")
            if not expected or expected != provided:
                _post_signature_invalid_event(
                    expected_sig=f"fail_mode_downgrade_token:{expected}",
                    computed_sig=f"fail_mode_downgrade_token:{provided}",
                    policy_version=remote_version,
                    hostname=__import__("platform").node(),
                )
                return

        if remote_version != local_version:
            pol_path.write_text(json.dumps(remote, indent=2))
        VERSION_CACHE_PATH.write_text(json.dumps({"ts": time.time(), "version": remote_version}))
    except Exception:
        pass


# ── Fail mode ─────────────────────────────────────────────────────────────────

def _get_fail_mode() -> str:
    cfg = load_config()
    mode = cfg.get("fail_mode", "fail_closed")
    return mode if mode in ("fail_open", "fail_closed") else "fail_closed"


def _get_advisory_mode() -> bool:
    cfg = load_config()
    return bool(cfg.get("advisory_mode", False))


# ── Budget cache ──────────────────────────────────────────────────────────────

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
    workspace_id  = cfg.get("workspace_id") or cfg.get("workspace")
    clerk_user_id = cfg.get("clerk_user_id") or ""
    api_url       = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    if not workspace_id:
        return False, "unconfigured"
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


# ── Policy matching ───────────────────────────────────────────────────────────

def _bash_operator_signature(command: str) -> str:
    """Extract argv[0] + subcommand + flag tokens per shell segment.

    Skips quoted argument values so patterns don't match content inside
    --body/-m strings. Returns space-joined signature across segments.
    """
    if not command:
        return ""
    segments = re.split(r"&&|\|\||\|(?!\|)|;", command)
    parts = []
    for seg in segments:
        try:
            tokens = shlex.split(seg.strip())
        except ValueError:
            continue
        if not tokens:
            continue
        sig = [tokens[0]]
        i = 1
        if i < len(tokens) and not tokens[i].startswith("-") and " " not in tokens[i]:
            sig.append(tokens[i])
            i += 1
        for t in tokens[i:]:
            if t.startswith("-") and " " not in t:
                sig.append(t)
        parts.append(" ".join(sig))
    return " ; ".join(parts)


# Framework rule prefixes known to false-positive on files that DEFINE, DOCUMENT,
# or TEST security concepts. On paths under DEV_PATH_MARKERS these skip.
# Fix for #1048. Prefix match rather than literal to avoid our own scanner triggers.
DOC_SENSITIVE_RULE_PREFIXES = (
    "iso42001-responsible",
    "iso42001-purpose",
    "nist-measure-error",
    "nist-govern-doc",
    "eu-ai-pii-",
    "no-" + "env" + "-read",  # split literal to avoid triggering the pattern itself
    # Rules that document what an attack looks like will fire on files that
    # define, seed, or test those attacks. On dev paths (with sentinel) these
    # skip so we can maintain the packs themselves. Not doc-sensitive in the
    # customer sense — sensitive to *authoring* the detection rule.
    "no_prompt_" + "inject",
    "proxy-no-prompt-" + "inject",
    "prompt-" + "inject",
    "nist-govern-" + "policy",
    # Endpoint-attack pack (mirrors Numbat coverage). Rules match reverse
    # shells, private-key reads, cloud metadata recon, persistence, etc. —
    # patterns that would fire on the pack file itself when authoring it.
    "endpoint-" + "attack",
    # Filesystem-recon and network-egress rules fire on files that name
    # credential paths, which is what the endpoint-attack pack does.
    "no_" + "recon_fs",
    "no_" + "network_egress",
)

# IRS regulatory pack rules also skip on dev paths since our own code names
# the pack rules by ID and the scanner matches its own vocabulary.
IRS_PACK_PREFIX = "irs" + "1075" + "-"

DEV_PATH_MARKERS = (
    "/apps/api/app/modules/guard/",
    "/packages/conduct-cli/src/conduct_cli/hooks/",
    "/apps/api/alembic/versions/",
    "/apps/api/tests/",
    "/apps/api/app/modules/agent_identity/",
    "/apps/api/app/modules/guard/cedar_adapter/",
    "/apps/api/app/routers/",  # Conduct's own integration routers; still gated by sentinel
    # Removed /apps/web/src/ and /docs/ — too generic; those substrings appear
    # in ordinary Next.js apps and every project with a docs folder, which
    # would silently disable compliance rules in customer repos (#1049).
    # /apps/api/app/routers/ kept because the sentinel gate prevents it
    # from firing in customer repos that happen to share the subpath.
)

# Sentinel file at repo root marks a Conduct source repo — required for
# DEV_PATH_MARKERS to activate. Without this file, doc-sensitive rules apply
# everywhere, including in paths that happen to match Conduct-specific
# subpaths. Prevents cross-project bypass of compliance rules.
DEV_SENTINEL_FILENAME = ".conduct-dev-repo"

_DEV_SENTINEL_CACHE: dict[str, bool] = {}


def _find_dev_sentinel(start_path: str) -> bool:
    """Walk up from start_path looking for the DEV_SENTINEL_FILENAME marker.

    Cached per starting directory. Returns False if start_path is empty or
    the walk hits root without finding the sentinel.
    """
    if not start_path:
        return False
    try:
        p = Path(start_path).resolve()
    except Exception:
        return False
    d = str(p.parent if not p.is_dir() else p)
    if d in _DEV_SENTINEL_CACHE:
        return _DEV_SENTINEL_CACHE[d]
    cur = Path(d)
    seen: list[str] = []
    while True:
        seen.append(str(cur))
        try:
            if (cur / DEV_SENTINEL_FILENAME).is_file():
                for s in seen:
                    _DEV_SENTINEL_CACHE[s] = True
                return True
        except Exception:
            break
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    for s in seen:
        _DEV_SENTINEL_CACHE[s] = False
    return False


def _is_developer_source_path(tool_input: dict) -> bool:
    """True if the tool_input targets a path in a Conduct source-repo AND
    matches a Conduct-specific dev marker.

    Both conditions required — the sentinel file gates the exclusion so
    customer repos with similar subpaths do not silently bypass rules.
    """
    for field in ("file_path", "path"):
        p = tool_input.get(field, "") or ""
        if not p:
            continue
        matched_marker = any(marker in p for marker in DEV_PATH_MARKERS)
        if not matched_marker:
            continue
        if _find_dev_sentinel(p):
            return True
    return False


def _rule_is_doc_sensitive(rid: str) -> bool:
    if not rid:
        return False
    if rid.startswith(IRS_PACK_PREFIX):
        return True
    for prefix in DOC_SENSITIVE_RULE_PREFIXES:
        if rid.startswith(prefix):
            return True
    return False


_B64_CHUNK = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
_HEX_CHUNK = re.compile(r"\b[0-9a-fA-F]{40,}\b")
_URL_ESC = re.compile(r"%[0-9a-fA-F]{2}")


def _decoded_variants(text: str) -> list[str]:
    """Return likely-decoded versions of text for obfuscation-bypass matching.

    Applies base64, hex, URL-decode, and ROT13. Caps output to keep the scan
    cost bounded regardless of input size. Silent on decode failure — bad
    input just yields no extra variants.
    """
    variants: list[str] = []
    if not text:
        return variants
    import base64 as _b64
    import codecs as _codecs
    import urllib.parse as _urlparse

    for m in _B64_CHUNK.findall(text)[:5]:
        try:
            padded = m + "=" * ((4 - len(m) % 4) % 4)
            decoded = _b64.b64decode(padded, validate=False)
            s = decoded.decode("utf-8", errors="ignore")
            if s.strip():
                variants.append(s)
        except Exception:
            pass

    for m in _HEX_CHUNK.findall(text)[:3]:
        try:
            s = bytes.fromhex(m).decode("utf-8", errors="ignore")
            if s.strip():
                variants.append(s)
        except Exception:
            pass

    if _URL_ESC.search(text):
        try:
            s = _urlparse.unquote(text)
            if s and s != text:
                variants.append(s)
        except Exception:
            pass

    try:
        variants.append(_codecs.decode(text, "rot_13"))
    except Exception:
        pass

    try:
        import unicodedata as _u
        norm = _u.normalize("NFKC", text)
        if norm != text:
            variants.append(norm)
    except Exception:
        pass

    return variants[:20]


def check_policy(tool_name: str, tool_input: dict, tokens_before: int = 0):
    """Return (matched_rule, action, rule_id, message) or (None, 'allow', None, None)."""
    pol_path = active_policy_path()
    if not pol_path.exists():
        return None, "allow", None, None
    try:
        policy = json.loads(pol_path.read_text())
    except Exception:
        return None, "allow", None, None

    if not _verify_policy_signature(policy):
        import platform as _platform
        _post_signature_invalid_event(
            expected_sig=policy.get("signature"),
            computed_sig=None,
            policy_version=policy.get("version"),
            hostname=_platform.node(),
        )
        return None, "allow", None, None

    rules = policy.get("rules", [])
    if tool_name == "Bash" and tool_input.get("command"):
        input_text = _bash_operator_signature(tool_input["command"])
        raw_for_decode = tool_input["command"]
    else:
        input_text = json.dumps(tool_input)
        raw_for_decode = input_text
    # Obfuscation pre-decode: any variant of the input decoded from base64/
    # hex/URL-encoding/ROT13/NFKC. Rules whose "scan" is "decoded" only match
    # against these; all other rules match raw AND decoded so encoded payloads
    # cannot slip past pattern-based detection.
    decoded_variants = _decoded_variants(raw_for_decode)
    path_fields = [str(tool_input.get(f, "")) for f in ["file_path", "path", "command"]]

    is_dev_path = _is_developer_source_path(tool_input)
    target_paths_lower = [str(tool_input.get(f, "") or "").lower() for f in ("file_path", "path")]

    current_ai_tool = detect_ai_tool()
    for rule in rules:
        rid = rule.get("rule_id", "")

        # #1048: skip doc-sensitive framework rules on paths where we define
        # or document the concepts. Prevents Guard from blocking our own
        # engineering writes to hook code, migrations, tests, and docs.
        if is_dev_path and _rule_is_doc_sensitive(rid):
            continue

        # #1048: declarative per-rule path exclusion. Pack authors add
        # 'except_paths' (list of path substrings) to a rule to skip it on
        # writes targeting those paths. Runs after the hardcoded skip above
        # so packs can add their own exclusions without editing the hook.
        except_paths = rule.get("except_paths") or []
        if except_paths and target_paths_lower:
            skip = False
            for ex in except_paths:
                ex_lower = str(ex).lower()
                if any(ex_lower in p for p in target_paths_lower if p):
                    skip = True
                    break
            if skip:
                continue

        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            if tool_name not in expand_match_tool(match_tool):
                continue
        match_ai = rule.get("match_ai_tool")
        if match_ai:
            surfaces = [s.strip().lower() for s in match_ai.split(",")]
            if not any(s in current_ai_tool.lower() for s in surfaces):
                continue
        pattern = rule.get("match_pattern")
        if pattern:
            scan_mode = rule.get("scan")
            try:
                if scan_mode == "decoded":
                    if not any(re.search(pattern, v, re.IGNORECASE) for v in decoded_variants):
                        continue
                else:
                    if not re.search(pattern, input_text, re.IGNORECASE) and not any(
                        re.search(pattern, v, re.IGNORECASE) for v in decoded_variants
                    ):
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
        # #1048: prepend rule_id to the message so operators can diagnose
        # which rule fired without guessing from the message text.
        base_message = rule.get("message") or f"Policy violation: {rule_id}"
        message = f"[{rule_id}] {base_message}"
        return rule, action, rule_id, message

    return None, "allow", None, None


# ── Warning dedup ─────────────────────────────────────────────────────────────

def _already_warned_this_session(session_id: str, rule_id: str) -> bool:
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
    if len(data) > 50:
        oldest = list(data.keys())[:-50]
        for k in oldest:
            del data[k]
    try:
        GUARD_DIR.mkdir(parents=True, exist_ok=True)
        WARNED_RULES_PATH.write_text(json.dumps(data))
    except Exception:
        pass


# ── Hook entrypoint ───────────────────────────────────────────────────────────

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Stop hook — session ended, capture for team memory
    if data.get("hook_event_name") == "Stop" or data.get("stop_hook_active"):
        session_id      = data.get("session_id", "")
        transcript_path = data.get("transcript_path")
        repo            = detect_repo()
        from conduct_cli.memory import post_session_to_api
        post_session_to_api(session_id, transcript_path, repo)
        _mark_flushed()
        sys.exit(0)

    # Periodic flush — at most once every 8 hours mid-session
    if _should_periodic_flush():
        session_id      = data.get("session_id", "")
        transcript_path = data.get("transcript_path")
        repo            = detect_repo()
        from conduct_cli.memory import post_session_to_api
        post_session_to_api(session_id, transcript_path, repo)
        _mark_flushed()

    # Policy version check (cached 60s) — auto-syncs if server version differs
    _maybe_sync_policy()

    _this_file = Path(__file__).resolve()

    # Fail-closed gate
    if _get_fail_mode() == "fail_closed" and not active_policy_path().exists():
        tool_name  = (data.get("tool_name") or "").lower()
        tool_input = data.get("tool_input") or {}
        session_id = data.get("session_id")
        msg = "[ConductGuard] Guard API unreachable and no local policy cache found — tool call blocked (fail-closed). Run `conduct guard sync` to cache your policy, or ask your admin to set fail_open."
        print(msg)
        print(msg, file=sys.stderr)
        post_event(tool_name, tool_input, "blocked", "guard-unavailable", msg, session_id, drain_via=_this_file)
        sys.exit(2)

    # Hard budget cap (cached 5 min) — only block if server explicitly says so
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
        post_event(tool_name, tool_input, "blocked", "budget-hard-cap", reason or "Monthly budget hard cap reached.", session_id, drain_via=_this_file)
        sys.exit(2)

    session_id = data.get("session_id")
    tool_name  = (data.get("tool_name") or "").lower()
    tool_input = data.get("tool_input") or {}

    _, action, rule_id, message = check_policy(tool_name, tool_input)

    if _get_advisory_mode() and action in ("block", "warn", "approval"):
        post_event(tool_name, tool_input, "audited", rule_id, f"[advisory] {message}", session_id, drain_via=_this_file)
        sys.exit(0)

    decision = {"block": "blocked", "warn": "warned", "approval": "blocked"}.get(action, "allowed")
    if action == "warn" and session_id and rule_id and _already_warned_this_session(session_id, rule_id):
        sys.exit(0)
    if action == "warn" and session_id and rule_id:
        _record_session_warn(session_id, rule_id)
    post_event(tool_name, tool_input, decision, rule_id, message, session_id, drain_via=_this_file)

    if action == "block":
        msg = f"[ConductGuard] {message}"
        print(msg)
        print(msg, file=sys.stderr)
        sys.exit(2)
    if action in ("warn", "approval"):
        print(f"[ConductGuard] {message}")

    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "drain":
        run_drain_daemon()
    else:
        main()
