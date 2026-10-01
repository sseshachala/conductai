"""Ownership-aware editor hook setup. Never rewrite invalid user configuration."""
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from conduct_cli.credential_lock import credential_lock
from conduct_cli.tool_adapters import ADAPTERS

MODULE = "conduct_cli.hooks.editors"
EVENTS = {
    "cursor": {"preToolUse": "pre", "postToolUse": "post", "postToolUseFailure": "failure"},
    "windsurf": {f"{phase}_{event}": phase for phase in ("pre", "post")
                 for event in ("read_code", "write_code", "run_command", "mcp_tool_use")},
}


def owned(entry, surface):
    if not isinstance(entry, dict) or not isinstance(entry.get("command"), str):
        return False
    try:
        argv = shlex.split(entry["command"])
    except ValueError:
        return False
    return len(argv) == 5 and argv[1:4] == ["-m", MODULE, surface] and argv[4] in {"pre", "post", "failure"}


def configure(surface, python, remove=False):
    root = ADAPTERS[surface].root()
    if not root.is_dir():
        return False
    path = root / "hooks.json"
    with credential_lock(path):
        if path.is_symlink():
            raise ValueError("Refusing to modify symlinked hook configuration")
        if path.exists() and path.stat().st_size > 1_000_000:
            raise ValueError("Oversized hook configuration")
        config = json.loads(path.read_text()) if path.exists() else {}
        if not isinstance(config, dict) or not isinstance(config.get("hooks", {}), dict):
            raise ValueError("Invalid hook configuration")
        hooks = config.setdefault("hooks", {})
        before = json.dumps(config, sort_keys=True)
        for event, mode in EVENTS[surface].items():
            entries = hooks.get(event, [])
            if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
                raise ValueError("Invalid hook entries")
            kept = [e for e in entries if not owned(e, surface)]
            if not remove:
                argv = [python, "-m", MODULE, surface, mode]
                command = subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
                entry = {"command": command}
                if surface == "cursor":
                    entry.update(timeout=25, failClosed=mode == "pre")
                else:
                    entry["powershell"] = "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in argv)
                kept.append(entry)
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
        if surface == "cursor" and not remove:
            config.setdefault("version", 1)
        if json.dumps(config, sort_keys=True) == before:
            return False
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(config, handle, indent=2)
        try:
            temporary.chmod(0o600)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return True


def install():
    from .hooks import _best_python
    for surface in EVENTS:
        try:
            if configure(surface, _best_python()):
                print(f"  {surface} hooks configured; live verification pending (restart the editor)")
        except (OSError, ValueError, TimeoutError):
            print(f"  {surface} hook configuration could not be updated; left unchanged")
