"""Cursor and Windsurf hook translation. Post hooks observe; they cannot block."""
import json
import os
import subprocess
import sys
from uuid import UUID, uuid5, NAMESPACE_URL


def normalize(surface, data):
    if not isinstance(data, dict):
        raise ValueError("Invalid hook payload")
    if surface == "cursor":
        tool = data.get("tool_name")
        args = data.get("tool_input")
        session = data.get("conversation_id") or data.get("session_id")
        tool = {"Shell": "bash", "Read": "read", "Write": "write", "Delete": "delete"}.get(tool, tool)
    elif surface == "windsurf":
        event = data.get("agent_action_name", "")
        args = data.get("tool_info")
        session = data.get("trajectory_id") or data.get("execution_id")
        if not isinstance(args, dict):
            raise ValueError("Invalid Windsurf tool payload")
        if event in {"pre_run_command", "post_run_command"}:
            tool, args = "bash", {"command": args.get("command_line"), "cwd": args.get("cwd")}
        elif event in {"pre_read_code", "post_read_code", "pre_write_code", "post_write_code"}:
            tool = "read" if "read" in event else "write"
        elif event in {"pre_mcp_tool_use", "post_mcp_tool_use"}:
            tool, args = args.get("mcp_tool_name"), args.get("mcp_tool_arguments")
        else:
            raise ValueError("Unsupported hook event")
    else:
        raise ValueError("Unsupported hook surface")
    if not isinstance(tool, str) or not tool or not isinstance(args, dict):
        raise ValueError("Invalid tool payload")
    if tool == "bash" and not isinstance(args.get("command"), str):
        raise ValueError("Missing command")
    if isinstance(session, str) and session:
        try:
            session = str(UUID(session))
        except ValueError:
            session = str(uuid5(NAMESPACE_URL, f"conduct:{surface}:{session}"))
    else:
        session = None
    return {"tool_name": tool, "tool_input": args, "session_id": session}


def run(surface, mode, data):
    normalized = normalize(surface, data)
    if mode == "pre":
        from .base import load_config, active_policy_path
        config = load_config()
        if not (config.get("workspace_id") or config.get("workspace")) or not active_policy_path().exists():
            return False
        try:
            result = subprocess.run(
                [sys.executable, "-m", "conduct_cli.hooks.pretooluse"],
                input=json.dumps(normalized), capture_output=True, text=True, timeout=20,
                env={**os.environ, "CONDUCT_HOOK_SURFACE": surface},
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    if mode not in {"post", "failure"}:
        raise ValueError("Invalid hook mode")
    from .base import post_event, record_hook_heartbeat, GUARD_DIR
    os.environ["CONDUCT_HOOK_SURFACE"] = surface
    record_hook_heartbeat("post_tool_use")
    post_event(normalized["tool_name"], {}, "audited", message=f"{surface} tool execution recorded",
               session_id=normalized["session_id"], drain_via=GUARD_DIR / "hook.py",
               execution_status="error" if mode == "failure" else "success")
    return True


def main():
    surface = sys.argv[1] if len(sys.argv) > 1 else ""
    mode = sys.argv[2] if len(sys.argv) > 2 else "pre"
    allowed = False
    try:
        raw = sys.stdin.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Oversized hook payload")
        allowed = run(surface, mode, json.loads(raw))
    except Exception:
        pass
    if mode != "pre":
        return  # Observation failure cannot undo an executed tool call.
    if surface == "cursor":
        print(json.dumps({"permission": "allow" if allowed else "deny",
                          **({} if allowed else {"user_message": "Conduct Guard blocked this call or could not validate it."})}))
    if not allowed:
        sys.exit(2)


if __name__ == "__main__":
    main()
