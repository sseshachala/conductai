"""Guard CLI: hooks."""
from __future__ import annotations

from pathlib import Path
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
    from conduct_cli.tool_adapters import ADAPTERS
    from conduct_cli.tool_config import edit_document
    from .tool_lifecycle import disabled, _command
    if disabled("claude-code"):
        return
    python = _best_python()
    paths = {
        "PreCompact": ("guard-precompact.py", "precompact"),
        "SessionStart": ("guard-session-start.py", "session-start"),
    }
    for filename, launcher in [*paths.values(), ("guard-stop.py", "stop")]:
        _write_session_hook(_guard_shared.GUARD_DIR / filename, launcher)
    settings = ADAPTERS["claude-code"].root() / "settings.json"
    try:
        with edit_document(settings) as document:
            hooks = document.setdefault("hooks", {})
            if not isinstance(hooks, dict):
                raise ValueError("Invalid hook map")
            for event, (filename, _) in paths.items():
                entries = hooks.setdefault(event, [])
                if not isinstance(entries, list) or any(not isinstance(group, dict) for group in entries):
                    raise ValueError("Invalid hook groups")
                if any(not isinstance(group.get("hooks", []), list)
                       or any(not isinstance(entry, dict) for entry in group.get("hooks", []))
                       for group in entries):
                    raise ValueError("Invalid hook commands")
                command = _command([python, str(_guard_shared.GUARD_DIR / filename)])
                if not any(command == entry.get("command") for group in entries for entry in group.get("hooks", [])):
                    entries.append({"hooks": [{"type": "command", "command": command}]})
    except (OSError, ValueError, TimeoutError):
        print("Claude Code session hook configuration is invalid or unavailable; left unchanged.")


def _install_copilot_hooks(hook_path: Path) -> None:
    from .tool_lifecycle import configure_hooks, disabled
    from conduct_cli.tool_adapters import ADAPTERS
    if disabled("copilot-cli") or not _guard_shared._copilot_cli_installed():
        return
    ADAPTERS["copilot-cli"].root().mkdir(parents=True, exist_ok=True)
    try:
        changed = configure_hooks("copilot-cli", _best_python(), hook_path)
        print("Copilot CLI hooks registered." if changed else "Copilot CLI hooks already registered.")
    except (OSError, ValueError, TimeoutError):
        print("Copilot CLI hook configuration is invalid or unavailable; left unchanged.")


def _install_codex_hook(hook_path: Path) -> None:
    from .tool_lifecycle import configure_hooks, disabled
    if disabled("codex"):
        return
    try:
        changed = configure_hooks("codex", _best_python(), hook_path)
        print("Codex hooks registered." if changed else "Codex hooks already registered.")
    except (OSError, ValueError, TimeoutError):
        print("Codex hook configuration is invalid or unavailable; left unchanged.")


def _install_claude_hook(hook_path: Path) -> None:
    from .tool_lifecycle import configure_hooks, disabled
    from conduct_cli.tool_adapters import ADAPTERS
    if disabled("claude-code"):
        return
    ADAPTERS["claude-code"].root().mkdir(parents=True, exist_ok=True)
    try:
        changed = configure_hooks("claude-code", _best_python(), hook_path)
        print("Claude Code hooks registered." if changed else "Claude Code hooks already registered.")
    except (OSError, ValueError, TimeoutError):
        print("Claude Code hook configuration is invalid or unavailable; left unchanged.")


def _usage_lifecycle_hooks(hooks: dict, surface: str) -> bool:
    """Install independent usage hooks without replacing memory/user hooks."""
    import shlex
    import subprocess
    argv = [_best_python(), "-m", "conduct_cli.hooks.session_usage", surface]
    command = subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)
    changed = False
    for event in ("SessionStart", "Stop", "SessionEnd"):
        existing = hooks.get(event, [])
        kept = []
        for group in existing:
            commands = [hook for hook in group.get("hooks", [])
                        if "conduct_cli.hooks.session_usage" not in hook.get("command", "")]
            if commands:
                kept.append({**group, "hooks": commands})
        desired = [*kept, {"hooks": [{"type": "command", "command": command}]}]
        if existing != desired:
            hooks[event] = desired
            changed = True
    return changed
