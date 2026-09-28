"""Guard CLI: hooks."""
from __future__ import annotations

from pathlib import Path
import json
import sys

from . import shared as _guard_shared


_THIN_LAUNCHERS = {
    "pretooluse": (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "_cmd = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "if _cmd == 'post':\n"
        "    try:\n        from conduct_cli.hooks.posttooluse import main; main()\n"
        "    except (ImportError, ModuleNotFoundError): sys.exit(0)\n"
        "elif _cmd == 'drain':\n"
        "    try:\n        from conduct_cli.hooks.base import run_drain_daemon; run_drain_daemon()\n"
        "    except (ImportError, ModuleNotFoundError): sys.exit(0)\n"
        "else:\n"
        "    try:\n        from conduct_cli.hooks.pretooluse import main; main()\n"
        "    except (ImportError, ModuleNotFoundError): sys.exit(0)\n"
    ),
    "posttooluse": (
        "#!/usr/bin/env python3\n"
        "try:\n    from conduct_cli.hooks.posttooluse import main; main()\n"
        "except (ImportError, ModuleNotFoundError): import sys; sys.exit(0)\n"
    ),
    "stop": (
        "#!/usr/bin/env python3\n"
        "try:\n    from conduct_cli.hooks.stop import main; main()\n"
        "except (ImportError, ModuleNotFoundError): import sys; sys.exit(0)\n"
    ),
    "precompact": (
        "#!/usr/bin/env python3\n"
        "try:\n    from conduct_cli.hooks.precompact import main; main()\n"
        "except (ImportError, ModuleNotFoundError): import sys; sys.exit(0)\n"
    ),
    "session-start": (
        "#!/usr/bin/env python3\n"
        "try:\n    from conduct_cli.hooks.session_start import main; main()\n"
        "except (ImportError, ModuleNotFoundError): import sys; sys.exit(0)\n"
    ),
}


def _is_thin_launcher(path: Path) -> bool:
    try:
        text = path.read_text()
        return "from conduct_cli.hooks." in text
    except Exception:
        return False


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


def _write_hook(path: Path) -> None:
    """Write a thin launcher to path (or legacy template for backward compat), then validate.

    Thin launcher (new default):
        #!/usr/bin/env python3
        from conduct_cli.hooks.pretooluse import main; main()

    If conduct_cli.hooks is not importable (e.g. editable install not set up),
    falls back to writing the full template so hooks still work.
    On syntax failure: restores previous hook (or writes a safe stub) so the
    system is never left without a working hook file.
    """
    import py_compile
    backup = None
    if path.exists():
        backup = path.read_text()
    path.parent.mkdir(parents=True, exist_ok=True)

    content = _THIN_LAUNCHERS["pretooluse"]

    path.write_text(content)
    path.chmod(0o755)
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        if backup is not None:
            path.write_text(backup)
        else:
            path.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n")
        raise RuntimeError(
            f"hook.py failed syntax check — previous hook restored.\n{exc}"
        ) from exc


def _write_session_hook(path: Path, launcher_key: str) -> None:
    content = _THIN_LAUNCHERS[launcher_key]
    path.write_text(content)
    path.chmod(0o755)


def _install_session_hooks() -> None:
    """Write PreCompact + SessionStart + Stop hook scripts and register them in ~/.claude/settings.json."""
    python = _best_python()

    precompact_path    = _guard_shared.GUARD_DIR / "guard-precompact.py"
    session_start_path = _guard_shared.GUARD_DIR / "guard-session-start.py"
    stop_path          = _guard_shared.GUARD_DIR / "guard-stop.py"

    _write_session_hook(precompact_path,    "precompact")
    _write_session_hook(session_start_path, "session-start")
    _write_session_hook(stop_path,          "stop")

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


def _install_copilot_hooks(hook_path: Path) -> None:
    if not _guard_shared._copilot_cli_installed():
        return
    hooks_dir = _guard_shared._copilot_home() / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    config = {"version": 1, "hooks": {
        event: [{"type": "command", "exec": _best_python(),
                 "args": ["-m", "conduct_cli.hooks.copilot", mode, str(hook_path)],
                 "timeoutSec": 30}]
        for event, mode in (("preToolUse", "pre"), ("postToolUse", "post"),
                            ("postToolUseFailure", "failure"),
                            ("sessionStart", "session-start"), ("sessionEnd", "session-end"))
    }}
    (hooks_dir / "conduct-guard.json").write_text(json.dumps(config, indent=2) + "\n")
    print(f"  {_guard_shared.GREEN}Copilot CLI tool hooks registered (restart Copilot){_guard_shared.RESET}")


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

    hook_path_str = str(hook_path)
    # Match the retired location only to delete stale registrations. The
    # desired entry below always points at the current ~/.conduct/hook.py.
    stale_hook_path = str(Path.home() / ".conductguard" / "hook.py")
    conduct_hook_paths = {
        hook_path_str,
        str(Path.home() / ".conduct" / "hook.py"),
        stale_hook_path,
    }

    def _is_conduct_hook(entry: dict) -> bool:
        command = entry.get("command", "")
        return any(path in command for path in conduct_hook_paths)

    def _replace_conduct_entries(entries: list, command: str) -> tuple[list, bool]:
        kept = []
        removed = False
        for registration in entries:
            commands = registration.get("hooks", [])
            filtered = [entry for entry in commands if not _is_conduct_hook(entry)]
            if len(filtered) != len(commands):
                removed = True
            if filtered:
                kept.append({**registration, "hooks": filtered})
        desired = {"matcher": ".*", "hooks": [{"type": "command", "command": command}]}
        return [*kept, desired], removed or entries != [*kept, desired]

    # PreToolUse
    pre_cmd = f"{_best_python()} {hook_path}"
    pre = hook_section.setdefault("PreToolUse", [])
    # Match by hook path so old python3/python3.11 entries are treated as already registered
    pre_already = any(
        hook_path_str in e.get("command", "")
        for h in pre
        for e in h.get("hooks", [])
    )
    changed = False
    normalized_pre, pre_changed = _replace_conduct_entries(pre, pre_cmd)
    hook_section["PreToolUse"] = normalized_pre
    changed = pre_changed

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
    normalized_post, post_changed = _replace_conduct_entries(post, post_cmd)
    hook_section["PostToolUse"] = normalized_post
    changed = changed or post_changed
    if cleaned:
        changed = True

    if changed:
        codex_hooks.parent.mkdir(parents=True, exist_ok=True)
        codex_hooks.write_text(json.dumps(hooks, indent=2))
        if not pre_already:
            print(f"  {_guard_shared.GREEN}Codex PreToolUse hook registered{_guard_shared.RESET}")
        if not post_already or cleaned:
            print(f"  {_guard_shared.GREEN}Codex PostToolUse hook registered{_guard_shared.RESET}")
    else:
        print(f"  {_guard_shared.GRAY}Codex hooks already registered{_guard_shared.RESET}")


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

    # Stop — capture session for team memory only (guard sync removed — exits 1 without TTY)
    stop = hooks.setdefault("Stop", [])

    python = _best_python()
    stop_path = _guard_shared.GUARD_DIR / "guard-stop.py"
    mem_cmd = f"{python} {stop_path}"
    mem_already = any(
        "guard-stop" in e.get("command", "")
        for h in stop
        for e in h.get("hooks", [])
    )
    if not mem_already and stop_path.exists():
        stop.append({"hooks": [{"type": "command", "command": mem_cmd}]})
        changed = True

    if changed:
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        claude_settings.write_text(json.dumps(settings, indent=2))
        if not pre_already:
            print(f"  {_guard_shared.GREEN}Claude Code PreToolUse hook registered{_guard_shared.RESET}")
        if not post_already or cleaned:
            print(f"  {_guard_shared.GREEN}Claude Code PostToolUse hook registered{_guard_shared.RESET}")
        if not mem_already:
            print(f"  {_guard_shared.GREEN}Claude Code Stop hook registered (team memory capture){_guard_shared.RESET}")
    else:
        print(f"  {_guard_shared.GRAY}Claude Code hooks already registered{_guard_shared.RESET}")
