"""`conduct session-report`: run bundled paxel and send the report."""
from __future__ import annotations

import sys
from pathlib import Path

from conduct_cli import api
from conduct_cli.commands.shared import _require_auth


def cmd_session_report(args):
    """Run paxel analysis and open an HTML report in the local browser."""
    import json as _json
    import shutil
    import subprocess
    import tempfile
    import webbrowser
    import getpass

    # ── 1. Use bundled paxel ─────────────────────────────────────────────────
    bundled = Path(__file__).parent.parent / "paxel.py"
    tmpdir = tempfile.mkdtemp(prefix="conduct-paxel-")
    paxel_script = Path(tmpdir) / "paxel.py"
    shutil.copy(bundled, paxel_script)

    # ── 2. Run paxel ─────────────────────────────────────────────────────────
    print("Analysing sessions…")
    try:
        result = subprocess.run(
            [sys.executable, str(paxel_script), "--no-open"],
            cwd=tmpdir, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("ERROR: analysis timed out after 120 s.")
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(1)

    stats_path = Path(tmpdir) / "stats.json"
    report_path = Path(tmpdir) / "report.md"

    if not stats_path.exists():
        print("ERROR: no transcripts found.")
        if result.stderr:
            print(result.stderr[:500])
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit(1)

    with open(stats_path) as f:
        stats = _json.load(f)
    report_md = report_path.read_text() if report_path.exists() else ""

    # ── 3. Extract stats ─────────────────────────────────────────────────────
    developer    = getattr(args, "developer", None) or getpass.getuser()
    volume       = stats.get("volume", {})
    behavior     = stats.get("behavior", {})
    autonomy     = stats.get("autonomy", {})
    tools        = stats.get("tools", {})
    velocity     = stats.get("velocity", {})
    sessions     = volume.get("total_sessions", "?")
    prompts      = volume.get("total_prompts", "?")
    autonomy_score = autonomy.get("autonomy_score_0_100", "?")
    top_tools    = [t[0] for t in (tools.get("top_tools") or [])[:8]]
    commits      = velocity.get("git_commits_real", "?") if isinstance(velocity, dict) else "?"
    planning_ratio = behavior.get("planning_ratio_explore_to_doing", 0)

    if autonomy_score != "?" and float(autonomy_score) >= 70:
        archetype = "Autonomous Builder"
    elif planning_ratio != 0 and float(planning_ratio) > 1.0:
        archetype = "Strategic Planner"
    else:
        archetype = "Execution-Focused Builder"

    tools_str = "  ".join(f"<span class='tag'>{t}</span>" for t in top_tools)
    md_html = report_md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

    # ── 4. Generate HTML ─────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Session Report — {developer}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f0f11; color: #e2e2e8; min-height: 100vh; padding: 40px 24px; }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -.02em; margin-bottom: 4px; }}
  .sub {{ font-size: 14px; color: #888; margin-bottom: 32px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 14px; margin-bottom: 32px; }}
  .card {{ background: #1a1a1f; border: 1px solid #2a2a33; border-radius: 10px; padding: 18px 20px; }}
  .card .label {{ font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #666; margin-bottom: 8px; }}
  .card .value {{ font-size: 28px; font-weight: 700; color: #fff; letter-spacing: -.02em; }}
  .card .unit {{ font-size: 13px; color: #888; margin-top: 2px; }}
  .archetype {{ background: #1a1a1f; border: 1px solid #2a2a33; border-radius: 10px; padding: 20px 24px; margin-bottom: 32px; display: flex; align-items: center; gap: 16px; }}
  .archetype .badge {{ font-size: 13px; font-weight: 700; background: #7c3aed22; color: #a78bfa; border: 1px solid #7c3aed44; border-radius: 8px; padding: 6px 14px; white-space: nowrap; }}
  .archetype .desc {{ font-size: 13px; color: #aaa; }}
  .section {{ margin-bottom: 32px; }}
  .section h2 {{ font-size: 12px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #666; margin-bottom: 12px; }}
  .tag {{ display: inline-block; font-size: 12px; font-weight: 600; background: #1e1e28; border: 1px solid #2a2a3a; border-radius: 6px; padding: 4px 10px; margin: 3px; color: #a0aec0; }}
  .report {{ background: #1a1a1f; border: 1px solid #2a2a33; border-radius: 10px; padding: 20px 24px; font-size: 13px; color: #ccc; line-height: 1.7; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Session Report</h1>
  <div class="sub">{developer} · generated just now</div>

  <div class="archetype">
    <span class="badge">{archetype}</span>
    <span class="desc">Autonomy score {autonomy_score}/100 &nbsp;·&nbsp; Planning ratio {planning_ratio}</span>
  </div>

  <div class="grid">
    <div class="card"><div class="label">Sessions</div><div class="value">{sessions}</div></div>
    <div class="card"><div class="label">Prompts</div><div class="value">{prompts}</div></div>
    <div class="card"><div class="label">Commits</div><div class="value">{commits}</div></div>
    <div class="card"><div class="label">Autonomy</div><div class="value">{autonomy_score}</div><div class="unit">/ 100</div></div>
  </div>

  <div class="section">
    <h2>Top Tools</h2>
    {tools_str if tools_str else "<span class='tag'>—</span>"}
  </div>

  <div class="section">
    <h2>Report</h2>
    <div class="report">{md_html or "No report generated."}</div>
  </div>
</div>
</body>
</html>"""

    html_path = Path(tmpdir) / "report.html"
    html_path.write_text(html)

    print(f"  Archetype  : {archetype}")
    print(f"  Autonomy   : {autonomy_score}/100   Sessions: {sessions}   Commits: {commits}")
    webbrowser.open(f"file://{html_path}")
    print("Opening report in browser…")

    # ── 5. Push report to Guard dashboard ────────────────────────────────────
    try:
        server, workspace_id, token = _require_auth(args)
        hdrs = api.headers(workspace_id, token, "application/json")
        import getpass as _getpass
        email = getattr(args, "developer", None) or _getpass.getuser()
        payload = _json.dumps({
            "developer_email": email,
            "archetype": archetype,
            "autonomy_score": float(autonomy_score) if autonomy_score != "?" else None,
            "planning_ratio": float(planning_ratio) if planning_ratio else None,
            "sessions": int(sessions) if sessions != "?" else 0,
            "prompts": int(prompts) if prompts != "?" else 0,
            "commits": int(commits) if commits != "?" else 0,
            "lines_per_hour": float(velocity.get("git_lines_per_active_hour", 0) or 0) if isinstance(velocity, dict) else None,
            "active_days": int(volume.get("active_days", 0) or 0),
            "tools_json": dict(tools.get("top_tools") or []),
            "report_md": report_md[:50000] if report_md else None,
        }).encode()
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            f"{server}/guard/session-reports",
            data=payload, headers=hdrs, method="POST",
        )
        __import__("urllib.request", fromlist=["urlopen"]).urlopen(req, timeout=10)
        print("✓ Report saved to Guard dashboard.")
    except Exception as _push_err:
        msg = str(_push_err)
        if "conduct login" in msg or "No server" in msg or "No workspace" in msg or "No credentials" in msg:
            print("  (Could not push to dashboard — run 'conduct login' to enable)")
        else:
            print(f"  (Dashboard push failed: {_push_err})")
