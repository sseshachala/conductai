"""Incremental, metadata-only usage collection for Codex and Claude transcripts.

The first scan establishes a baseline. Never import a pre-existing session's
usage into a newly selected workspace. Journal delivery and snapshot IDs make
retries safe; no transcript text is included in the upload or cursor.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from conduct_cli.credential_lock import credential_lock
from . import base
from .copilot_usage import context, _save
from .usage_details import FIELDS, add_delta, categories, identifier

MAX_LINE = 16 * 1024 * 1024
SURFACES = {"codex", "codex-cli", "codex-desktop", "claude-code"}


def transcript(data: dict, surface: str) -> Path | None:
    explicit = data.get("transcript_path") or data.get("transcriptPath")
    if explicit and Path(explicit).is_file():
        return Path(explicit).resolve()
    session = str(UUID(data["session_id"]))
    if surface.startswith("codex"):
        root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        matches = list((root / "sessions").glob(f"**/*-{session}.jsonl"))
    else:
        root = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
        matches = list((root / "projects").glob(f"*/{session}.jsonl"))
    return matches[0].resolve() if len(matches) == 1 else None


def _count(value):
    if type(value) is not int or not 0 <= value <= 2**31 - 1:
        raise ValueError("Invalid usage counter")
    return value


def _scan(path: Path, state: dict, surface: str) -> None:
    state["pending_usage"] = []
    state["usage_complete"] = True
    stat = path.stat()
    if state["offset"] > stat.st_size or state.get("inode", stat.st_ino) != stat.st_ino:
        raise ValueError("Transcript replaced or truncated")
    state["inode"] = stat.st_ino
    with path.open("rb") as stream:
        stream.seek(state["offset"])
        while True:
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                # Consume large tool output without retaining it in memory.
                while line and not line.endswith(b"\n"):
                    line = stream.readline(MAX_LINE + 1)
                if not line.endswith(b"\n"):
                    break
                state["offset"] = stream.tell()
                continue
            if not line.endswith(b"\n"):
                break  # Retry a partially flushed last record on the next hook.
            state["offset"] = stream.tell()
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            if surface.startswith("codex"):
                payload = event.get("payload") or {}
                if not isinstance(payload, dict):
                    continue
                if event.get("type") == "session_meta":
                    state["provider"] = identifier(payload.get("model_provider"))
                if event.get("type") == "turn_context":
                    state["model"] = identifier(payload.get("model"))
                if event.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                info = payload.get("info") or {}
                if not isinstance(info, dict):
                    continue
                usage = info.get("total_token_usage")
                if not isinstance(usage, dict):
                    continue
                try:
                    current = [_count(usage.get("input_tokens")), _count(usage.get("output_tokens"))]
                except ValueError:
                    continue
                # Output already includes reasoning; input already includes cache.
                if state["counts"] is not None and any(a < b for a, b in zip(current, state["counts"])):
                    state["reset"] = True
                detail = categories(usage, "codex")
                previous_detail = state.get("detail_counts")
                last = categories(info.get("last_token_usage", {}), "codex")
                response_id = info.get("response_id") if detail and previous_detail and last and all(
                    detail[key] - previous_detail[key] == last[key] for key in FIELDS) else None
                if not add_delta(state["pending_usage"], detail, state.get("detail_counts"),
                                 state.get("model"), state.get("provider"), response_id,
                                 info.get("conduct_request_id") if response_id else None):
                    state["usage_complete"] = False
                state["detail_counts"] = detail
                state["counts"] = current
            elif event.get("type") == "assistant":
                message = event.get("message") or {}
                if not isinstance(message, dict):
                    continue
                usage = message.get("usage")
                message_id = message.get("id")
                if not isinstance(usage, dict) or not isinstance(message_id, str):
                    continue
                try:
                    current = [_count(usage.get("input_tokens")) + sum(_count(usage.get(key, 0)) for key in
                                   ("cache_read_input_tokens", "cache_creation_input_tokens")),
                               _count(usage.get("output_tokens"))]
                except ValueError:
                    continue
                key = hashlib.sha256(message_id.encode()).hexdigest()
                previous = state["messages"].get(key, [0, 0])
                detail = categories(usage, "claude")
                old_detail = state["message_details"].get(key, dict.fromkeys(FIELDS, 0))
                if detail is not None and old_detail is not None:
                    detail = {k: max(detail[k], old_detail[k]) for k in FIELDS}
                if not add_delta(state["pending_usage"], detail, old_detail, message.get("model"),
                                 response_id=message_id, request_id=event.get("conduct_request_id")):
                    state["usage_complete"] = False
                state["message_details"][key] = detail
                # Streaming transcript entries can repeat or extend one message.
                current = [max(a, b) for a, b in zip(current, previous)]
                state["counts"] = [a + b - c for a, b, c in zip(state["counts"], current, previous)]
                state["messages"][key] = current


def collect(data: dict, surface: str, expected: tuple) -> bool:
    from conduct_cli.guard_commands.tool_lifecycle import disabled
    if disabled("codex" if surface.startswith("codex") else surface):
        return False
    if surface not in SURFACES or not expected[1] or context(base.load_config()) != tuple(expected):
        return False
    session = str(UUID(data["session_id"]))
    path = transcript(data, surface)
    if path is None:
        return False
    family = "codex" if surface.startswith("codex") else surface
    key = hashlib.sha256(json.dumps([family, session, str(path)]).encode()).hexdigest()
    context_key = hashlib.sha256(json.dumps(expected).encode()).hexdigest()
    cursor = Path.home() / ".conduct" / "session-usage" / (key + ".json")
    with credential_lock(cursor, timeout=1):
        fresh = not cursor.exists()
        state = json.loads(cursor.read_text()) if not fresh else {}
        fresh = fresh or state.get("context") != context_key or state.get("version") != 2
        if fresh:
            state = {"version": 2, "offset": 0, "counts": [0, 0], "messages": {}, "message_details": {},
                     "detail_counts": dict.fromkeys(FIELDS, 0), "ai_tool": surface,
                     "context": context_key, "epoch": str(uuid4())}
        stat = path.stat()
        if state["offset"] > stat.st_size or state.get("inode", stat.st_ino) != stat.st_ino:
            fresh = True
            state = {"version": 2, "offset": 0, "counts": [0, 0], "messages": {}, "message_details": {},
                     "detail_counts": dict.fromkeys(FIELDS, 0), "ai_tool": surface,
                     "context": context_key, "epoch": str(uuid4())}
        # Refine old generic cursors without resetting their usage baseline.
        if state.get("ai_tool") == "codex" and surface in {"codex-cli", "codex-desktop"}:
            state["ai_tool"] = surface
        before = list(state["counts"]) if state["counts"] is not None else None
        _scan(path, state, surface)
        if context(base.load_config()) != tuple(expected):
            return False
        after = state["counts"]
        queued = False
        reset = state.pop("reset", False)
        if not fresh and not reset and before is not None and after is not None and after != before:
            delta = [a - b for a, b in zip(after, before)]
            payload = {"workspace_id": expected[1], "ai_tool": state["ai_tool"], "hook_session_id": session,
                       "snapshot_id": str(uuid5(NAMESPACE_URL, json.dumps([key, context_key, state["epoch"], state["offset"], before, after]))),
                       "observed_at": datetime.now(timezone.utc).isoformat(),
                       "input_tokens": _count(delta[0]), "output_tokens": _count(delta[1])}
            parts = state["pending_usage"]
            if state["usage_complete"] and (
                sum(p[k] for p in parts for k in FIELDS[:3]) == delta[0]
                and sum(p["output_tokens"] for p in parts) == delta[1]
            ):
                payload["usage"] = parts
            if not base.journal_append(json.dumps(payload), expected[0], "/guard/events/session-usage"):
                return False
            queued = True
        state.pop("pending_usage", None)
        state.pop("usage_complete", None)
        _save(cursor, state)
    if queued:
        base.ensure_drain_daemon(base.GUARD_DIR / "hook.py")
    return queued


def handle(data: dict, surface: str | None = None, *, poll: bool = False) -> None:
    """Best-effort synchronous collection plus one bounded worker per session."""
    try:
        surface = surface or base.detect_ai_tool()
        if surface == "codex":
            detected = base.detect_ai_tool()
            if detected in {"codex-cli", "codex-desktop"}:
                surface = detected
        if surface not in SURFACES:
            return
        expected = context(base.load_config())
        safe = {key: data[key] for key in ("session_id", "transcript_path", "transcriptPath") if key in data}
        collect(safe, surface, expected)
        if poll:
            options = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
                       if os.name == "nt" else {"start_new_session": True})
            subprocess.Popen([sys.executable, "-m", __name__, json.dumps(safe), surface, json.dumps(expected)],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
    except (OSError, ValueError, KeyError, TypeError, TimeoutError):
        pass


def main() -> None:
    try:
        if len(sys.argv) == 4:
            data, surface, expected = json.loads(sys.argv[1]), sys.argv[2], tuple(json.loads(sys.argv[3]))
            family = "codex" if surface.startswith("codex") else surface
            key = hashlib.sha256(json.dumps([data.get("session_id"), family, expected]).encode()).hexdigest()
            lock = Path.home() / ".conduct" / "session-usage" / (key + ".worker")
            with credential_lock(lock, timeout=0.1):
                for _ in range(20):
                    time.sleep(0.5)
                    collect(data, surface, expected)
        else:
            data = json.load(sys.stdin)
            surface = sys.argv[1] if len(sys.argv) > 1 else None
            handle(data, surface, poll=data.get("hook_event_name") != "SessionStart")
    except (OSError, ValueError, KeyError, TypeError, TimeoutError):
        pass


if __name__ == "__main__":
    main()
