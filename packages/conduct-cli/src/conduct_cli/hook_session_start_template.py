#!/usr/bin/env python3
"""ConductGuard SessionStart hook — prints context after compaction."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_PATH = Path.home() / ".conductguard" / "session_snapshot.json"
MAX_AGE_HOURS = 2


def main():
    try:
        sys.stdin.read()
    except Exception:
        pass

    if not SNAPSHOT_PATH.exists():
        sys.exit(0)

    try:
        snapshot = json.loads(SNAPSHOT_PATH.read_text())
        compacted_at = datetime.fromisoformat(snapshot.get("compacted_at", ""))
        age_hours = (datetime.now(timezone.utc) - compacted_at).total_seconds() / 3600
        if age_hours > MAX_AGE_HOURS:
            sys.exit(0)

        t1 = snapshot.get("tier1", {})
        branch = t1.get("git_branch", "")
        commits = t1.get("recent_commits", "")
        headline = t1.get("memory_headline", "")
        t2 = snapshot.get("tier2", {})
        guard = t2.get("guard_status") or {}

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
                db_path = root / ".booster" / "symbols.db"
                hooks_path = root / ".claude" / "hooks" / "booster-gate.py"
                if hooks_path.exists() and db_path.exists():
                    try:
                        conn = sqlite3.connect(str(db_path))
                        n = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
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
            repo = None
            try:
                import subprocess
                out = subprocess.check_output(["git", "remote", "get-url", "origin"],
                                               stderr=subprocess.DEVNULL, text=True).strip()
                if "github.com" in out:
                    repo = out.split("github.com")[-1].lstrip("/:").rstrip(".git")
            except Exception:
                pass

            from conduct_cli.memory import search_team_memory
            results = search_team_memory("recent learnings patterns bugs", repo=repo, limit=3)
            if results:
                lines.append("- Team knowledge:")
                for r in results[:3]:
                    dev = r.get("developer_id", "teammate")[:8]
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
