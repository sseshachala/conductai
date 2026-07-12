"""Standalone background job: run paxel on the current session and push results
to /guard/session-reports.  Invoked as a detached subprocess from the Stop hook
so it never blocks session close.

Usage (internal):
    python -m conduct_cli.hooks.session_report_push <session_id>
"""
from __future__ import annotations

import getpass
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def _load_config() -> dict:
    for p in [
        Path.home() / ".conduct" / "config.json",
        Path.home() / ".conduct" / "config.json",
    ]:
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
    return {}


def run(session_id: str = "") -> None:
    cfg = _load_config()
    server = (cfg.get("api_url") or cfg.get("server") or "https://api.conductai.ai").rstrip("/")
    api_key = cfg.get("api_key", "")
    member_token = cfg.get("member_token", "")
    workspace_id = cfg.get("workspace_id", "")

    if not server or not workspace_id:
        return

    bundled = Path(__file__).parent.parent / "paxel.py"
    if not bundled.exists():
        return

    tmpdir = Path(tempfile.mkdtemp(prefix="conduct-paxel-bg-"))
    try:
        paxel_script = tmpdir / "paxel.py"
        shutil.copy(bundled, paxel_script)

        result = subprocess.run(
            [sys.executable, str(paxel_script), "--no-open"],
            cwd=str(tmpdir),
            capture_output=True,
            text=True,
            timeout=120,
        )

        stats_path = tmpdir / "stats.json"
        report_path = tmpdir / "report.md"

        if not stats_path.exists():
            return

        stats = json.loads(stats_path.read_text())
        report_md = report_path.read_text() if report_path.exists() else ""

        volume   = stats.get("volume", {})
        behavior = stats.get("behavior", {})
        autonomy = stats.get("autonomy", {})
        tools    = stats.get("tools", {})
        velocity = stats.get("velocity", {})

        sessions     = volume.get("total_sessions", 0)
        prompts      = volume.get("total_prompts", 0)
        active_days  = volume.get("active_days", 0)
        autonomy_score = autonomy.get("autonomy_score_0_100")
        planning_ratio = behavior.get("planning_ratio_explore_to_doing", 0)
        commits      = velocity.get("git_commits_real") if isinstance(velocity, dict) else None
        lines_per_hr = velocity.get("git_lines_per_active_hour") if isinstance(velocity, dict) else None
        top_tools    = dict(tools.get("top_tools") or [])

        # Skip push for trivial sessions (< 3 prompts — not worth reporting)
        if int(prompts or 0) < 3:
            return

        if autonomy_score is not None and float(autonomy_score) >= 70:
            archetype = "Autonomous Builder"
        elif planning_ratio and float(planning_ratio) > 1.0:
            archetype = "Strategic Planner"
        else:
            archetype = "Execution-Focused Builder"

        email = cfg.get("user_email") or getpass.getuser()

        payload = json.dumps({
            "developer_email": email,
            "archetype": archetype,
            "autonomy_score": float(autonomy_score) if autonomy_score is not None else None,
            "planning_ratio": float(planning_ratio) if planning_ratio else None,
            "sessions": int(sessions or 0),
            "prompts": int(prompts or 0),
            "commits": int(commits) if commits is not None else 0,
            "lines_per_hour": float(lines_per_hr) if lines_per_hr is not None else None,
            "active_days": int(active_days or 0),
            "tools_json": top_tools,
            "report_md": report_md[:50000] if report_md else None,
            "source": "auto",
        }).encode()

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Workspace-ID": workspace_id,
        }
        if member_token:
            headers["Authorization"] = f"Bearer {member_token}"
        elif api_key:
            headers["X-API-Key"] = api_key

        req = urllib.request.Request(
            f"{server}/guard/session-reports",
            data=payload,
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=15)

    except Exception:
        pass
    finally:
        shutil.rmtree(str(tmpdir), ignore_errors=True)


if __name__ == "__main__":
    session_id = sys.argv[1] if len(sys.argv) > 1 else ""
    run(session_id)
