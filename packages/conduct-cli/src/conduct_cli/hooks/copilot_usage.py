"""Collect cumulative Copilot shutdown counters as session-level deltas.

Tool hooks and context-window occupancy are not model usage. Only persisted
shutdown tokenDetails are accepted; prompts and tool arguments never leave disk.
"""
from __future__ import annotations

from conduct_cli.deployment import api_url as deployment_api_url
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import UUID

from . import base
from conduct_cli.credential_lock import credential_lock

FIELDS = ("input", "cache_read", "cache_write", "output")


def shutdowns(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result = []
    with path.open(encoding="utf-8") as stream:
        while True:
            line = stream.readline(1024 * 1024 + 1)
            if not line:
                break
            if len(line) > 1024 * 1024:
                while line and not line.endswith("\n"):
                    line = stream.readline(1024 * 1024 + 1)
                continue  # Large tool output must not hide later usage snapshots.
            try:
                event = json.loads(line)
            except ValueError:
                continue  # A writer may not have finished its last line yet.
            if event.get("type") != "session.shutdown":
                continue
            details = event.get("data", {}).get("tokenDetails", {})
            counts = {key: details.get(key, {}).get("tokenCount") for key in FIELDS}
            if any(type(value) is not int or not 0 <= value <= 2**31 - 1
                   for value in counts.values()):
                raise ValueError("Invalid shutdown counters")
            result.append({"id": str(UUID(event["id"])), "counts": counts,
                           "observed_at": event["timestamp"]})
    return result


def context(cfg: dict) -> tuple:
    return (deployment_api_url(cfg),
            cfg.get("workspace_id"), cfg.get("clerk_user_id"))


def collect(session_id: str, hook_path: Path, expected: tuple) -> bool:
    session_id = str(UUID(session_id))  # Never accept a path from hook input.
    cfg = base.load_config()
    if not expected[1] or context(cfg) != tuple(expected):
        return False
    root = Path(os.environ.get("COPILOT_HOME", str(Path.home() / ".copilot")))
    path = root / "session-state" / session_id / "events.jsonl"
    if path.resolve().parent.parent != (root / "session-state").resolve():
        raise ValueError("Session path escaped Copilot home")
    key = hashlib.sha256(json.dumps([session_id, str(path.resolve())]).encode()).hexdigest()
    context_key = hashlib.sha256(json.dumps(expected).encode()).hexdigest()
    state = Path.home() / ".conduct" / "copilot-usage" / (key + ".json")
    with credential_lock(state, timeout=1):
        records = shutdowns(path)
        cursor = json.loads(state.read_text()) if state.exists() else {}
        if cursor.get("context") != context_key:
            # Begin at the current snapshot, never import historical usage on sync.
            cursor = records[-1] if records else {"id": None, "counts": dict.fromkeys(FIELDS, 0)}
            _save(state, {**cursor, "context": context_key})
            return False
        pending = records
        if cursor["id"]:
            positions = [i for i, record in enumerate(records) if record["id"] == cursor["id"]]
            if not positions:
                return False  # Truncated/replaced logs cannot establish a safe delta.
            pending = records[positions[-1] + 1:]
        queued = False
        for record in pending:
            delta = {key: record["counts"][key] - cursor["counts"][key] for key in FIELDS}
            if any(value < 0 for value in delta.values()):
                # Rebaseline a reset without inventing usage across the gap.
                _save(state, {**record, "context": context_key})
                cursor = record
                continue
            if context(base.load_config()) != tuple(expected):
                return queued
            payload = {"workspace_id": expected[1], "hook_session_id": session_id,
                       "snapshot_id": record["id"], "observed_at": record["observed_at"],
                       "input_tokens": delta["input"] + delta["cache_read"] + delta["cache_write"],
                       "output_tokens": delta["output"]}
            if not base.journal_append(json.dumps(payload), expected[0], "/guard/events/session-usage"):
                return queued
            _save(state, {**record, "context": context_key})
            cursor = record
            queued = True
        if queued:
            base.ensure_drain_daemon(hook_path)
        return queued


def _save(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(path)


def handle(mode: str, data: dict, hook_path: Path) -> None:
    session_id = str(UUID(data.get("sessionId", data.get("session_id", ""))))
    expected = context(base.load_config())
    collect(session_id, hook_path, expected)
    if mode != "session-end":
        return
    # Copilot may write shutdown after sessionEnd returns. Poll out of process.
    options = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([sys.executable, "-m", __name__, session_id, str(hook_path), json.dumps(expected)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **options)


def main() -> None:
    try:
        expected = tuple(json.loads(sys.argv[3]))
        for _ in range(20):
            if collect(sys.argv[1], Path(sys.argv[2]), expected):
                break
            time.sleep(0.5)
    except (OSError, ValueError, KeyError, TypeError, TimeoutError):
        pass  # Usage collection must never block policy evaluation or tool execution.


if __name__ == "__main__":
    main()
