"""Keep client configs on the current agent token after a rotation.

``/auth/refresh`` rotates the agent token and the previous one stops working
at once. MCP client configs and the proxy env file embed the token, so every
rotation path (hooks, sync, login) calls ``propagate_agent_token`` to swap the
old value for the new one wherever it appears. The swap is a literal string
replace limited to files that contain the old token; nothing else is touched.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _candidate_paths() -> list[Path]:
    home = Path.home()
    paths = [
        home / ".conduct" / "env",
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        home / "Library" / "Application Support" / "Code" / "User" / "mcp.json",
        home / ".config" / "Code" / "User" / "mcp.json",
        Path(os.environ.get("COPILOT_HOME", str(home / ".copilot"))).expanduser() / "mcp-config.json",
        Path.cwd() / ".mcp.json",
    ]
    try:
        from conduct_cli.tool_adapters import ADAPTERS
        for adapter in ADAPTERS.values():
            paths.extend(source.path for source in adapter.mcp_sources())
        paths.append(ADAPTERS["codex"].root() / "config.toml")
    except Exception:
        pass
    seen: set[Path] = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def _replace_in_file(path: Path, old: str, new: str) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return False
    if old not in text:
        return False
    mode = path.stat().st_mode & 0o777
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text.replace(old, new))
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        return False
    return True


def propagate_agent_token(old: str | None, new: str | None) -> list[Path]:
    """Replace ``old`` with ``new`` in every known client config. Never raises."""
    if not old or not new or old == new or len(old) < 20:
        return []
    updated = []
    for path in _candidate_paths():
        try:
            if _replace_in_file(path, old, new):
                updated.append(path)
        except Exception:
            continue
    return updated
