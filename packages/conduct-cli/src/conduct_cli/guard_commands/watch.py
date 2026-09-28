"""Guard CLI: watch."""
from __future__ import annotations

from pathlib import Path
import os

from . import discovery as _guard_discovery
from . import shared as _guard_shared


_WATCH_PID  = Path.home() / ".conduct" / "watch.pid"


_WATCH_LOG  = Path.home() / ".conduct" / "watch.log"


_WATCH_INTERVAL = 15 * 60


def _is_watch_running():
    """Returns (is_running: bool, pid: int | None)."""
    if not _WATCH_PID.exists():
        return False, None
    try:
        pid = int(_WATCH_PID.read_text().strip())
        os.kill(pid, 0)
        return True, pid
    except (ValueError, ProcessLookupError):
        _WATCH_PID.unlink(missing_ok=True)
        return False, None


def _watch_loop():
    """Background loop — runs discover+push every 15 min. Invoked as subprocess."""
    import time, json as _json
    # resolve config at each iteration so workspace switches are picked up
    def _cfg():
        return _guard_shared._load_guard_config()

    while True:
        try:
            c       = _cfg()
            api_url = _guard_shared._api_url(c)
            token   = c.get("agent_token", "")
            agent_token = c.get("agent_token", "")
            agents = []
            for name, config_path, mcp_key in _guard_discovery._discover_config_agents():
                agents.append({
                    "name": name, "framework": name, "source": "config",
                    "location": str(config_path),
                    "evidence": {"config_path": str(config_path), "under_guard": mcp_key},
                    "risk_score": 20 if mcp_key else 70,
                    "under_guard": mcp_key,
                })
            try:
                process_agents = _guard_discovery._scan_processes()
                registered = {a["framework"] for a in agents if a["under_guard"]}
                for a in process_agents:
                    a["under_guard"] = a["framework"] in registered
                agents += process_agents
            except Exception:
                pass
            _guard_shared._req("POST", f"{api_url}/guard/discover/scan",
                 body={"triggered_by": "watch", "agents": agents},
                 token=token or agent_token)
        except Exception:
            pass
        time.sleep(_WATCH_INTERVAL)


def cmd_guard_watch(args):
    """Start/stop/status the background discovery daemon."""
    import signal as _signal

    if getattr(args, "status", False):
        running, pid = _is_watch_running()
        if running:
            print(f"  Guard watch daemon running (pid {pid})")
            log_tail = ""
            if _WATCH_LOG.exists():
                lines = _WATCH_LOG.read_text().splitlines()
                log_tail = "\n".join(lines[-5:])
            if log_tail:
                print(f"  Last log:\n{log_tail}")
        else:
            print("  Guard watch daemon not running. Start with: conduct guard watch")
        return

    if getattr(args, "stop", False):
        running, pid = _is_watch_running()
        if not running:
            print("  Guard watch daemon is not running.")
            return
        os.kill(pid, _signal.SIGTERM)
        _WATCH_PID.unlink(missing_ok=True)
        print(f"  Guard watch daemon stopped (pid {pid}).")
        return

    # Start
    running, pid = _is_watch_running()
    if running:
        print(f"  Guard watch daemon already running (pid {pid}). Stop with: conduct guard watch --stop")
        return

    _WATCH_PID.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(_WATCH_LOG, "a")
    import subprocess, sys as _sys
    proc = subprocess.Popen(
        [_sys.executable, "-c",
         "from conduct_cli.guard import _watch_loop; _watch_loop()"],
        start_new_session=True,
        stdout=log_file,
        stderr=log_file,
    )
    _WATCH_PID.write_text(str(proc.pid))
    print(f"  Guard watch daemon started (pid {proc.pid}).")
    print(f"  Scans every 15 min — results visible at conductai.ai/guard/discovery")
    print(f"  Stop with: conduct guard watch --stop")
