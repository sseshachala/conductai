"""Read-only accounting coverage check; nonzero exit blocks fallback removal."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use an ISO timestamp with a timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("Timestamp must include a timezone")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=_timestamp, help="Earlier historical cutoff; default covers MTD and seven days")
    parser.add_argument("--notify", action="store_true", help="Also send a platform Slack alert if dirty or failed")
    args = parser.parse_args()
    try:
        from app.core.database import SessionLocal
        from app.runtime.accounting.audit_fallback_gate import reporting_window_start, run_startup_gate

        since = reporting_window_start()
        if args.since is not None:
            since = min(since, args.since)
        result = run_startup_gate(SessionLocal, since=since, notify=args.notify)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["ready_for_removal"] else 1
    except Exception as exc:
        print(f"Accounting gate failed ({type(exc).__name__}); no credentials printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
