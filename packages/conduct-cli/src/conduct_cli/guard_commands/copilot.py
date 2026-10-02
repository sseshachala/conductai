"""Managed Copilot provider configuration; never execute shell files to inspect them."""
from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

from conduct_cli.deployment import resolve

PREFIX = "COPILOT_PROVIDER_"
MANAGED = ("BASE_URL", "TYPE", "BEARER_TOKEN", "WIRE_API", "API_KEY")


def env_lines(token: str, gateway: str, *, windows=False, enabled=True) -> list[str]:
    values = dict(zip(MANAGED, (gateway.rstrip("/") + "/openai/v1", "openai", token, "responses", "")))
    lines = []
    for name, value in values.items():
        name = PREFIX + name
        if not enabled:
            # Clear previously sourced managed values; user overrides run last.
            lines.append(f"Remove-Item Env:{name} -ErrorAction SilentlyContinue" if windows else f"unset {name}")
        elif windows:
            lines.append(f"$env:{name} = '" + value.replace("'", "''") + "'")
        else:
            lines.append(f"export {name}={shlex.quote(value)}")
    return lines


def read_values(path: Path, *, windows=False) -> dict[str, str] | None:
    """Only literal assignments are evidence. Dynamic overrides are unknown."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError):
        return None
    values = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or PREFIX not in line:
            continue
        if windows:
            assignment = re.fullmatch(r"\$env:(COPILOT_PROVIDER_\w+)\s*=\s*'((?:[^']|'')*)'", line, re.I)
            removal = re.fullmatch(r"Remove-Item Env:(COPILOT_PROVIDER_\w+) -ErrorAction SilentlyContinue", line, re.I)
            if assignment:
                values[assignment[1].upper()] = assignment[2].replace("''", "'")
            elif removal:
                values[removal[1].upper()] = ""
            else:
                return None
        else:
            try:
                parts = shlex.split(line, comments=True)
            except ValueError:
                return None
            if len(parts) == 2 and parts[0] == "unset" and parts[1].startswith(PREFIX):
                values[parts[1]] = ""
            elif len(parts) == 2 and parts[0] == "export" and "=" in parts[1]:
                name, value = parts[1].split("=", 1)
                if not name.startswith(PREFIX) or any(c in value for c in "`$"):
                    return None
                values[name] = value
            else:
                return None
    return values


def configured(config=None) -> bool:
    from .shared import _load_guard_config
    config = _load_guard_config() if config is None else config
    try:
        gateway = resolve(config).gateway
    except ValueError:
        return False
    if not gateway:
        return False
    # A running shell's provider configuration wins as a whole. Do not mix a
    # stale token/URL with a newly written file and report a false success.
    values = {key: value for key, value in os.environ.items() if key.startswith(PREFIX)}
    if not values:
        windows = sys.platform == "win32"
        root = Path.home() / ".conduct"
        values = read_values(root / ("env.ps1" if windows else "env"), windows=windows)
        overrides = read_values(root / ("env-override.ps1" if windows else "env-override"), windows=windows)
        if values is None or overrides is None:
            return False
        values.update(overrides)
    token = values.get(PREFIX + "API_KEY") or values.get(PREFIX + "BEARER_TOKEN", "")
    expected_token = config.get("agent_token", "")
    return bool(
        values.get(PREFIX + "BASE_URL", "").rstrip("/") == gateway.rstrip("/") + "/openai/v1"
        and values.get(PREFIX + "TYPE", "openai") == "openai"
        and values.get(PREFIX + "WIRE_API") == "responses"
        and not values.get(PREFIX + "WIRE_MODEL")
        and token.startswith("cond_agt_") and token == expected_token
    )


def clear_managed() -> None:
    """Remove old Copilot credentials before changing deployment/workspace."""
    from .gateway import SHELL_RC_MARKER, _write_private_env
    root = Path.home() / ".conduct"
    for filename, windows in (("env", False), ("env.ps1", True)):
        path = root / filename
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if not content.startswith(SHELL_RC_MARKER):
            continue
        lines = [line for line in content.splitlines() if PREFIX not in line]
        # Before the override file: explicitly user-owned settings still win.
        lines[1:1] = env_lines("", "", windows=windows, enabled=False)
        _write_private_env(path, "\n".join(lines) + "\n")
