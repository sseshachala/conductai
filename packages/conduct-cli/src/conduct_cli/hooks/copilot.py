"""Translate Copilot CLI hook payloads to the shared Conduct policy engine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def normalize(data: dict) -> dict:
    tool = data.get("toolName", data.get("tool_name"))
    args = data.get("toolArgs", data.get("tool_input", {}))
    if isinstance(args, str):
        args = json.loads(args)
    if not isinstance(tool, str) or not tool or not isinstance(args, dict):
        raise ValueError("Invalid tool payload")
    tool = {"powershell": "bash", "view": "read", "create": "write",
            "apply_patch": "edit", "str_replace_editor": "edit"}.get(tool.lower(), tool.lower())
    args = dict(args)
    if "path" in args and "file_path" not in args:
        args["file_path"] = args["path"]
    return {"tool_name": tool, "tool_input": args,
            "session_id": data.get("sessionId", data.get("session_id"))}


def _team_memory(mode: str, data: dict) -> dict:
    """Capture learnings at sessionEnd; return sessionStart additionalContext (never raises).

    Copilot consumes only ``additionalContext`` from sessionStart and ignores
    sessionEnd output, so capture runs in a detached worker.
    """
    try:
        from conduct_cli import memory
        session_id = str(data.get("sessionId") or data.get("session_id") or "")
        if mode == "session-end":
            memory.spawn_capture("copilot-cli", session_id, None)
            return {}
        lines = memory.team_knowledge_lines()
        return {"additionalContext": "\n".join(["Conduct team memory for this repo:", *lines])} if lines else {}
    except Exception:
        return {}


def run(mode: str, hook_path: Path, data: dict) -> dict:
    if mode in ("session-start", "session-end"):
        from .copilot_usage import handle
        try:
            handle(mode, data, hook_path)
        except (OSError, ValueError, KeyError, TypeError, TimeoutError):
            pass  # Usage collection is best-effort; team memory still runs.
        return _team_memory(mode, data)
    normalized = normalize(data)
    if mode == "pre":
        # Establish the usage baseline even if sync was run mid-session.
        try:
            from .copilot_usage import handle
            handle("pre", data, hook_path)
        except (OSError, ValueError, KeyError, TypeError, TimeoutError):
            pass
        # Finish before Copilot's fail-open 30s timeout, even if Guard is offline.
        try:
            result = subprocess.run(
                [sys.executable, "-m", "conduct_cli.hooks.pretooluse"], input=json.dumps(normalized),
                capture_output=True, text=True, timeout=20,
                env={**os.environ, "CONDUCT_HOOK_SURFACE": "copilot-cli"},
            )
        except (OSError, subprocess.TimeoutExpired):
            return {"permissionDecision": "deny", "permissionDecisionReason": "Conduct Guard check unavailable or timed out. Retry after checking Guard connectivity."}
        if result.returncode:
            return {"permissionDecision": "deny", "permissionDecisionReason": "Conduct Guard blocked this tool call. Review the Guard event for policy details."}
        # Do not grant permissions that Copilot would otherwise ask the user for.
        if result.stdout.strip():
            print(result.stdout.strip(), file=sys.stderr)
        return {}
    if mode not in ("post", "failure"):
        raise ValueError("Unknown hook mode")
    from .base import post_event, record_hook_heartbeat

    os.environ["CONDUCT_HOOK_SURFACE"] = "copilot-cli"
    record_hook_heartbeat("post_tool_use")
    post_event(
        normalized["tool_name"], {}, "audited", message="Copilot CLI tool execution recorded",
        session_id=normalized["session_id"], drain_via=hook_path,
        execution_status="error" if mode == "failure" else "success",
    )
    # Recover a completed shutdown snapshot on the next action after resume.
    try:
        from .copilot_usage import handle
        handle("post", data, hook_path)
    except (OSError, ValueError, KeyError, TypeError, TimeoutError):
        pass
    return {}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        result = run(mode, Path(sys.argv[2]), json.load(sys.stdin))
    except Exception:
        result = ({"permissionDecision": "deny", "permissionDecisionReason": "Conduct Guard could not validate the tool call."}
                  if mode == "pre" else {})
    print(json.dumps(result))


if __name__ == "__main__":
    main()
