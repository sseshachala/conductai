"""Guard CLI: shared."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import sys
import urllib.error
import urllib.request


RESET  = "\033[0m"


BOLD   = "\033[1m"


GREEN  = "\033[32m"


RED    = "\033[31m"


BLUE   = "\033[34m"


GRAY   = "\033[90m"


CYAN   = "\033[36m"


YELLOW = "\033[33m"


CONDUCT_HOME = Path.home() / ".conduct"


GUARD_DIR    = CONDUCT_HOME


CONFIG_PATH  = CONDUCT_HOME / "config.json"


POLICY_PATH  = GUARD_DIR / "policy.json"


def active_policy_path() -> Path:
    return POLICY_PATH


def _load_guard_config(workspace_id: str | None = None) -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_guard_config(data: dict, workspace_id: str | None = None):
    CONDUCT_HOME.mkdir(parents=True, exist_ok=True)
    existing = {}
    if CONFIG_PATH.exists():
        try:
            existing = json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    existing.update(data)
    CONFIG_PATH.write_text(json.dumps(existing, indent=2))
    from conduct_cli.hooks.base import restrict_to_owner
    restrict_to_owner(CONFIG_PATH)


def _require_guard_config() -> dict:
    cfg = _load_guard_config()
    ws = cfg.get("workspace_id") or cfg.get("workspace")
    if not cfg or not ws:
        print(f"{RED}Guard not connected. Run: conduct login{RESET}", file=sys.stderr)
        sys.exit(1)
    if not cfg.get("agent_token"):
        print(f"{RED}Guard config is missing credentials. Run: conduct login{RESET}", file=sys.stderr)
        sys.exit(1)
    return cfg


def _api_url(cfg: dict) -> str:
    return cfg.get("api_url", "https://api.conductai.ai").rstrip("/")


def _copilot_home() -> Path:
    return Path(os.environ.get("COPILOT_HOME", str(Path.home() / ".copilot"))).expanduser()


def _copilot_cli_installed() -> bool:
    import shutil
    return bool(shutil.which("copilot") or _copilot_home().exists())


def _default_agent_token() -> str | None:
    """Read the agent_token minted by `conduct login` from ~/.conduct/config.json.
    This is the CLI's single canonical credential — every call to the central
    API should carry it via Authorization: Bearer."""
    try:
        cfg_path = Path.home() / ".conduct" / "config.json"
        if cfg_path.exists():
            return json.loads(cfg_path.read_text()).get("agent_token") or None
    except Exception:
        pass
    return None


def _req(method: str, url: str, body=None, token: str = None, timeout: int = 20) -> dict:
    # If no explicit token passed, fall back to the login-minted agent_token.
    if not token:
        token = _default_agent_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("detail", raw)
        except Exception:
            detail = raw
        print(f"{RED}HTTP {e.code}: {detail} [{url}]{RESET}")
        sys.exit(1)
    except Exception:
        print(f"{RED}Could not reach ConductAI API. Check your connection.{RESET}")
        sys.exit(1)


def _parse_since(since_str: str) -> str:
    """Convert '7d', '24h', '1h', '30d' to an ISO-8601 UTC timestamp string."""
    unit  = since_str[-1].lower()
    value = int(since_str[:-1])
    delta_map = {"h": timedelta(hours=value), "d": timedelta(days=value)}
    if unit not in delta_map:
        print(f"{RED}Invalid --since value '{since_str}'. Use: 1h, 24h, 7d, 30d{RESET}")
        sys.exit(1)
    return (datetime.now(tz=timezone.utc) - delta_map[unit]).strftime("%Y-%m-%dT%H:%M:%SZ")
