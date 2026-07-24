"""ConductGuard SessionStart hook — prints context after compaction."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from conduct_cli.hooks.base import (
    CONDUCT_ENV_PATH,
    CONFIG_PATH,
    GUARD_DIR,
    SNAPSHOT_PATH,
    detect_repo,
    load_config,
    post_event,
)

MAX_AGE_HOURS = 2


def _check_proxy_token() -> None:
    """Warn + alert server if the proxy token is missing or malformed.

    Reads ~/.conduct/env directly (not shell env) so this works regardless
    of whether the user sourced their rc file in this session.
    """
    if not CONDUCT_ENV_PATH.exists():
        return
    env_text = CONDUCT_ENV_PATH.read_text()
    has_base_url    = "ANTHROPIC_BASE_URL=" in env_text
    has_valid_token = (
        'ANTHROPIC_API_KEY="guard-mt-' in env_text
        or "ANTHROPIC_API_KEY='guard-mt-" in env_text
    )
    if not has_base_url:
        return
    if has_valid_token:
        return

    print("## ConductGuard: proxy token missing or malformed")
    print("Run `conduct guard sync` to refresh your token before making LLM calls.\n")

    try:
        cfg = load_config()
        workspace_id  = cfg.get("workspace_id", "")
        clerk_user_id = cfg.get("clerk_user_id", "") or cfg.get("user_email", "")
        post_event(
            "session_start",
            {"note": "proxy token not found in ~/.conduct/env"},
            "warned",
            "proxy_token_missing",
            "Developer proxy token missing or malformed — run conduct guard sync",
            session_id=None,
        )
    except Exception:
        pass


def _check_instructions_staleness() -> None:
    """Warn if team AI instructions have been updated since last sync.

    Reads local instructions_version from config, hits GET /team-os/instructions/version,
    prints one-line warning if stale. Timeout 2s — never blocks the session.
    """
    try:
        import urllib.request as _req
        cfg = load_config()
        api_url = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
        agent_token = cfg.get("agent_token", "")
        local_version = cfg.get("instructions_version")
        if not agent_token or not local_version:
            return  # not synced yet — nothing to compare

        request = _req.Request(
            f"{api_url}/team-os/instructions/version",
            headers={"Authorization": f"Bearer {agent_token}"},
        )
        with _req.urlopen(request, timeout=2) as resp:
            data = json.loads(resp.read())
        remote_version = data.get("version")
        if remote_version and remote_version != local_version:
            print(f"⚠  Team AI instructions updated ({local_version} → {remote_version}) — run `conduct guard sync` to pull latest\n")
    except Exception:
        pass  # always silent — session-start must never fail


def _backfill_prev_session(current_session_id: str, cwd: str | None) -> None:
    """Parse + PATCH the most recent completed session (the one that just ended).

    Runs silently — never raises, never blocks the new session.
    """
    try:
        import re, urllib.request
        from pathlib import Path as _P

        claude_projects = _P.home() / ".claude" / "projects"
        if not claude_projects.exists():
            return

        # find the project slug dir for this cwd
        if cwd:
            slug = re.sub(r"[^a-zA-Z0-9]", "-", cwd)
            project_dir = claude_projects / slug
        else:
            # fall back: pick most recently modified project dir
            dirs = sorted(claude_projects.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True)
            project_dir = dirs[0] if dirs else None

        if not project_dir or not project_dir.exists():
            return

        # pick the latest JSONL that isn't the current session
        candidates = sorted(
            (f for f in project_dir.glob("*.jsonl") if f.stem != current_session_id),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return

        cfg_path = _P.home() / ".conduct" / "config.json"
        if not cfg_path.exists():
            return
        cfg = json.loads(cfg_path.read_text())
        server = cfg.get("server", "").rstrip("/")
        agent_token = cfg.get("agent_token", "")
        workspace_id = cfg.get("workspace_id") or cfg.get("workspace", "")
        if not server:
            return

        from conduct_cli.hooks.session_parser import parse_session
        for f in candidates:
            try:
                sid = f.stem
                data = parse_session("claude_code", sid, cwd)
                payload = json.dumps({
                    "intent": data.intent,
                    "tool_sequence": data.tool_sequence,
                    "session_parse_status": data.status,
                    "session_parser": data.parser,
                }).encode()
                req = urllib.request.Request(
                    f"{server}/guard/sessions/{sid}/intent",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {agent_token}",
                        "X-Workspace-ID": workspace_id,
                    },
                    method="PATCH",
                )
                urllib.request.urlopen(req, timeout=8)
            except Exception:
                pass
    except Exception:
        pass


def main() -> None:
    current_session_id = ""
    cwd = None
    try:
        raw = sys.stdin.read()
        hook_data = json.loads(raw) if raw.strip() else {}
        current_session_id = hook_data.get("session_id", "")
        cwd = hook_data.get("cwd")
    except Exception:
        pass

    if current_session_id:
        try:
            import subprocess as _sp
            _sp.Popen(
                [sys.executable, "-c",
                 f"import sys; sys.path.insert(0,''); "
                 f"from conduct_cli.hooks.session_start import _backfill_prev_session; "
                 f"_backfill_prev_session({current_session_id!r}, {cwd!r})"],
                stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass

    _check_proxy_token()
    _check_instructions_staleness()

    if not SNAPSHOT_PATH.exists():
        sys.exit(0)

    try:
        snapshot     = json.loads(SNAPSHOT_PATH.read_text())
        compacted_at = datetime.fromisoformat(snapshot.get("compacted_at", ""))
        age_hours    = (datetime.now(timezone.utc) - compacted_at).total_seconds() / 3600
        if age_hours > MAX_AGE_HOURS:
            sys.exit(0)

        t1      = snapshot.get("tier1", {})
        branch  = t1.get("git_branch", "")
        commits = t1.get("recent_commits", "")
        headline = t1.get("memory_headline", "")
        t2      = snapshot.get("tier2", {})
        guard   = t2.get("guard_status") or {}

        lines = [f"## Session resumed (snapshot from {compacted_at.strftime('%Y-%m-%d %H:%M')} UTC)"]
        if branch:
            last = commits.splitlines()[0] if commits else ""
            lines.append(f"- Branch: {branch}" + (f" | Last: {last}" if last else ""))
        budget = guard.get("budget_pct")
        if budget is not None:
            lines.append(f"- Guard: {budget}% budget used")
        else:
            lines.append("- Guard: state unavailable")
        if headline:
            lines.append(f"- Memory index:\n  {headline}")
        else:
            lines.append("- Memory index:\n  (none)")

        # Booster intercept status
        try:
            import shutil, sqlite3
            root = Path.cwd()
            if shutil.which("booster"):
                db_path    = root / ".booster" / "symbols.db"
                hooks_path = root / ".claude" / "hooks" / "booster-gate.py"
                if hooks_path.exists() and db_path.exists():
                    try:
                        conn = sqlite3.connect(str(db_path))
                        n    = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
                        conn.close()
                        lines.append(f"- Agent Booster: ACTIVE — {n} symbols indexed, Read/Grep intercept ON")
                    except Exception:
                        lines.append("- Agent Booster: installed (index unavailable)")
                elif shutil.which("booster"):
                    lines.append("- Agent Booster: installed but NOT wired — run: conduct guard sync")
            else:
                lines.append("- Agent Booster: not installed (pip install 'conduct-cli[booster]')")
        except Exception:
            pass

        # Inject relevant team memories for the current repo
        try:
            repo = detect_repo()
            from conduct_cli.memory import search_team_memory
            results = search_team_memory("recent learnings patterns bugs", repo=repo, limit=3)
            if results:
                lines.append("- Team knowledge:")
                for r in results[:3]:
                    dev     = r.get("developer_id", "teammate")[:8]
                    summary = r.get("summary", "")[:120]
                    lines.append(f"  {dev}: {summary}")
        except Exception:
            pass

        print("\n".join(lines))
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
