#!/usr/bin/env python3
"""
guard-session-start.py — ConductGuard SessionStart hook
Reads .booster/session_snapshot.json and injects a terse context reminder.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_MAX_AGE_SECONDS = 7200  # 2 hours


def main() -> None:
    try:
        sys.stdin.read()  # consume stdin
    except Exception:
        pass

    try:
        snapshot_path = Path.cwd() / ".booster" / "session_snapshot.json"
        if not snapshot_path.exists():
            sys.exit(0)

        snapshot = json.loads(snapshot_path.read_text())
        compacted_at = snapshot.get("compacted_at", "")

        # Age check
        if compacted_at:
            try:
                ts = datetime.fromisoformat(compacted_at)
                if ts.tzinfo is None:
                    from datetime import timezone as _tz
                    ts = ts.replace(tzinfo=_tz.utc)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                if age > _MAX_AGE_SECONDS:
                    sys.exit(0)
            except Exception:
                pass

        t1 = snapshot.get("tier1", {})
        t2 = snapshot.get("tier2", {})

        branch = t1.get("git_branch", "unknown")
        commits = t1.get("recent_commits", "")
        first_commit = commits.splitlines()[0] if commits else "—"
        memory = t1.get("memory_headline", "")
        memory_lines = "\n".join(f"  {l}" for l in memory.splitlines()[:3]) if memory else "  (none)"

        guard = t2.get("guard_status") or {}
        if guard:
            pct = guard.get("budget_pct", guard.get("used_pct", "?"))
            remaining = guard.get("budget_remaining", guard.get("remaining_usd", "?"))
            guard_line = f"Guard: {pct}% used (${remaining} remaining)"
        else:
            guard_line = "Guard: state unavailable"

        short_ts = compacted_at[:16].replace("T", " ") if compacted_at else "unknown"

        print(f"## Session resumed (snapshot from {short_ts} UTC)")
        print(f"- Branch: {branch} | Last: {first_commit}")
        print(f"- {guard_line}")
        print(f"- Memory index:\n{memory_lines}")

    except Exception:
        pass  # never block Claude Code

    sys.exit(0)


if __name__ == "__main__":
    main()
