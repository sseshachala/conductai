"""
Subprocess entry point for Modal dispatch.

Called by dispatch_brain_tool with Modal credentials injected into this
process's env — never into the shared API worker env. Credentials exist
only for the lifetime of this subprocess.

Usage:
    python -m app.runtime.modal_runner '{"tool_name": "run_shell", "tool_input": {...}}'
"""
import json
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Error: payload argument required", end="", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON payload — {e}", end="", file=sys.stderr)
        sys.exit(1)

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input", {})

    if not tool_name:
        print("Error: tool_name missing from payload", end="", file=sys.stderr)
        sys.exit(1)

    from app.runtime.sandbox import _modal_dispatch
    result = _modal_dispatch(tool_name, tool_input)
    print(result, end="")


if __name__ == "__main__":
    main()
