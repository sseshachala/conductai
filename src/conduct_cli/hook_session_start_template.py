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

        print("\n".join(lines))
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
