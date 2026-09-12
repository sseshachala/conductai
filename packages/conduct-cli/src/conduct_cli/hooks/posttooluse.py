"""ConductGuard PostToolUse hook — token tracking."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conduct_cli.hooks.base import (
    CONFIG_PATH,
    GUARD_DIR,
    detect_ai_tool,
    load_config,
    post_event,
    run_drain_daemon,
)
from conduct_cli.hooks.pretooluse import (
    _already_warned_this_session,
    _record_session_warn,
    check_policy,
)


# ── Token reading ─────────────────────────────────────────────────────────────

def _tail_lines(path: Path, n: int = 200):
    size = path.stat().st_size
    if size == 0:
        return []
    chunk = min(size, n * 300)
    with open(path, "rb") as f:
        f.seek(max(0, size - chunk))
        raw = f.read()
    text = raw.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if size > chunk:
        lines = lines[1:]
    return lines


def _read_tokens_from_transcript(transcript_path: str, tool_use_id: str):
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
            msg   = entry.get("message") or {}
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


def _scan_codex_tokens(transcript_path: str):
    """Robustly scan a Codex transcript for the last token_count event."""
    try:
        path = Path(transcript_path)
        if not path.exists():
            return 0, 0
        size       = path.stat().st_size
        chunk_size = 524288  # 512 KB
        buf        = b""
        pos        = size
        while pos >= 0:
            read_size = min(chunk_size, pos)
            pos -= read_size
            with open(path, "rb") as f:
                f.seek(pos)
                buf = f.read(read_size) + buf
            text  = buf.decode("utf-8", errors="ignore")
            parts = text.split("\n")
            start = 1 if pos > 0 else 0
            for line in reversed(parts[start:]):
                if "token_count" not in line or not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "event_msg":
                        info  = entry.get("payload", {}).get("info", {})
                        usage = info.get("last_token_usage", {})
                        if usage:
                            total_in  = usage.get("input_tokens", 0)
                            total_out = (
                                usage.get("output_tokens", 0)
                                + usage.get("reasoning_output_tokens", 0)
                            )
                            return total_in, total_out
                except Exception:
                    continue
            if pos == 0:
                break
    except Exception:
        pass
    return 0, 0


def _git_context() -> "tuple[str | None, str | None]":
    """Return (repo_url, branch) from git — best-effort, never raises."""
    import subprocess as _sp
    repo = branch = None
    try:
        repo = _sp.check_output(
            ["git", "remote", "get-url", "origin"],
            timeout=2, stderr=_sp.DEVNULL, text=True,
        ).strip() or None
    except Exception:
        pass
    try:
        branch = _sp.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            timeout=2, stderr=_sp.DEVNULL, text=True,
        ).strip() or None
    except Exception:
        pass
    return repo, branch


def _compute_blast_radius(tool_name: str, tool_input: dict, tool_response: str) -> "dict | None":
    """Classify blast radius after tool execution. Returns None for read-only tools."""
    import re as _re

    READ_ONLY = {"read", "ls", "glob", "search", "grep", "websearch", "webfetch", "computer"}
    if tool_name in READ_ONLY:
        return None

    files = 0
    symbols: "int | None" = None
    tier = "local"
    file_paths: "list[str]" = []

    if tool_name in ("bash", "terminal"):
        cmd = (tool_input.get("command") or "").lower()
        if _re.search(r"\brm\s+.*-rf|\brm\s+-rf", cmd):
            tier = "destructive"
        elif _re.search(r"\bgit\s+(push|commit|merge|rebase|reset|tag)\b", cmd):
            tier = "repo"
        elif _re.search(r"\b(curl|wget|fetch)\b|https?://", cmd):
            tier = "network"
        # count path-like lines in output as proxy for files touched
        lines = (tool_response or "").splitlines()
        path_lines = [l.strip() for l in lines if "/" in l or ("." in l and len(l) < 200)]
        files = min(len(path_lines), 50)
        file_paths = path_lines[:20]

    elif tool_name in ("write",):
        files = 1
        content = tool_input.get("content") or ""
        symbols = len(content.splitlines()) or None
        fp = tool_input.get("file_path") or tool_input.get("path")
        if fp:
            file_paths = [fp]

    elif tool_name in ("edit", "str_replace_based_edit_tool", "str_replace_editor"):
        files = 1
        new_str = tool_input.get("new_string") or tool_input.get("new_content") or ""
        symbols = len(new_str.splitlines()) or None
        fp = tool_input.get("file_path") or tool_input.get("path")
        if fp:
            file_paths = [fp]

    elif tool_name in ("multiedit",):
        edits = tool_input.get("edits") or []
        files = len(edits)
        file_paths = [e.get("file_path") or e.get("path") for e in edits if e.get("file_path") or e.get("path")]

    else:
        files = 1  # unknown write-like tool

    repo, branch = _git_context()
    return {"files": files, "symbols": symbols, "tier": tier, "file_paths": file_paths, "repo": repo, "branch": branch}


def _post_usage(session_id, tool_name, tokens_input, tokens_output, duration_ms, blast_radius=None, execution_status=None, result_summary=None) -> None:
    """Fire-and-forget POST to /guard/events/usage."""
    cfg = load_config()
    workspace_id = cfg.get("workspace_id")
    if not workspace_id or not session_id:
        return
    payload = json.dumps({
        "workspace_id":     workspace_id,
        "hook_session_id":  session_id,
        "tool_name":        tool_name,
        "tokens_input":     tokens_input,
        "tokens_output":    tokens_output,
        "duration_ms":      duration_ms,
        "ai_tool":          detect_ai_tool(),
        "blast_radius":     blast_radius,
        "execution_status": execution_status,
        "result_summary":   result_summary,
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


# ── Codex delayed reader (spawned as subprocess) ──────────────────────────────

def post_codex_main() -> None:
    """Delayed Codex token reader — spawned as background by main().

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
        _post_usage(args.get("session_id"), args.get("tool_name"), tokens_in, tokens_out, None, args.get("blast_radius"))
    sys.exit(0)


# ── Hook entrypoint ───────────────────────────────────────────────────────────

def main() -> None:
    """PostToolUse hook entrypoint — exits immediately; heavy work is async."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    _this_file    = Path(__file__).resolve()
    tool_name     = (data.get("tool_name") or "").lower()
    tool_use_id   = data.get("tool_use_id")
    transcript_path = data.get("transcript_path")
    is_codex      = (tool_use_id or "").startswith("call_")
    session_id    = data.get("session_id") or (f"transcript:{transcript_path}" if transcript_path else None)

    tool_response = data.get("tool_response") or data.get("output") or ""
    tool_input    = data.get("tool_input") or {}
    blast_radius  = _compute_blast_radius(tool_name, tool_input, str(tool_response))

    # Derive execution outcome from hook data
    _resp_str = str(tool_response)
    if data.get("error") or "Error" in _resp_str[:100]:
        execution_status = "error"
        result_summary   = _resp_str[:200] or None
    else:
        execution_status = "success"
        result_summary   = None

    if is_codex and transcript_path:
        import uuid as _uuid
        pending = GUARD_DIR / f"codex_pending_{_uuid.uuid4().hex[:8]}.json"
        try:
            pending.write_text(json.dumps({
                "session_id":      session_id,
                "tool_name":       tool_name,
                "transcript_path": transcript_path,
                "blast_radius":    blast_radius,
            }))
            subprocess.Popen(
                [sys.executable, str(_this_file), "post-codex", str(pending)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
    elif transcript_path:
        tokens_input, tokens_output = _read_tokens_from_transcript(transcript_path, tool_use_id)
        _post_usage(session_id, tool_name, tokens_input, tokens_output, None, blast_radius, execution_status, result_summary)
        _, action, rule_id, message = check_policy(tool_name, {}, tokens_before=tokens_input)
        if action in ("warn", "block"):
            decision = "warned" if action == "warn" else "blocked"
            if action == "warn" and session_id and rule_id and _already_warned_this_session(session_id, rule_id):
                pass
            else:
                if action == "warn" and session_id and rule_id:
                    _record_session_warn(session_id, rule_id)
                post_event(tool_name, {}, decision, rule_id, message, session_id, drain_via=_this_file, blast_radius=blast_radius)

    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "post-codex":
        post_codex_main()
    else:
        main()
