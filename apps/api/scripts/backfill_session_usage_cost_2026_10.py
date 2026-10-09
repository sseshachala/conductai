"""One-shot: price client-reported session_usage rows that have had NULL cost since 2026-09-29.

Re-prices the stored slices with the same functions as ingest (``build_evidence``,
``coverage_for``), applying the Gateway-wins rule, then sets routing_meta evidence
and cost_usd_before/after. Dry-run by default (prints totals, writes nothing).
Idempotent: only rows whose cost is still NULL are visited, and re-pricing is
deterministic.

Run (Render shell, from apps/api):
  python -m scripts.backfill_session_usage_cost_2026_10           # dry run
  python -m scripts.backfill_session_usage_cost_2026_10 --apply   # write, commit per 500 rows

Delete this file once the backfill has been applied.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import select

SINCE = datetime(2026, 9, 29, tzinfo=timezone.utc)
BATCH = 500


def run(db, apply: bool = False) -> dict:
    from app.modules.guard.models import GuardAuditEvent as A, GuardSession
    from app.modules.guard.session_coverage import coverage_for
    from app.modules.guard.session_usage import SESSION_USAGE_TOOL_CALL, build_evidence, evidence_cost_usd

    stats = {"rows": 0, "legacy_no_slices": 0, "covered_slices": Counter(), "unpriced_slices": Counter(),
             "priced_rows": 0, "unpriced_rows": 0, "by_day_tool": defaultdict(lambda: [0, 0.0])}
    cursor = None
    while True:
        query = select(A).where(A.tool_call == SESSION_USAGE_TOOL_CALL, A.ts >= SINCE,
                                A.cost_usd_after.is_(None)).order_by(A.ts, A.id).limit(BATCH)
        if cursor:
            query = query.where(sa.tuple_(A.ts, A.id) > cursor)
        rows = db.execute(query).scalars().all()
        if not rows:
            break
        for row in rows:
            meta = (row.routing_meta or {}).get("session_usage") or {}
            parts = meta.get("slices") or []
            stats["rows"] += 1
            if not parts:
                stats["legacy_no_slices"] += 1  # totals-only snapshot: nothing to price
                continue
            coverage = coverage_for(db, workspace_id=row.workspace_id, actor=row.clerk_user_id,
                                    identity=row.agent_identity_id, session=row.hook_session_id, parts=parts)
            evidence = build_evidence(parts, meta.get("observed_at") or row.ts.isoformat(), coverage)
            cost = evidence_cost_usd(evidence)
            for part in evidence["slices"]:
                if part.get("covered_by"):
                    stats["covered_slices"][part["covered_by"]] += 1
                elif part["cost_status"] == "unpriced":
                    stats["unpriced_slices"][part["unpriced_reason"]] += 1
            if cost is None:
                stats["unpriced_rows"] += 1
            else:
                stats["priced_rows"] += 1
                bucket = stats["by_day_tool"][(row.ts.date().isoformat(), row.ai_tool)]
                bucket[0] += 1
                bucket[1] += cost
            if apply:
                row.routing_meta = {**row.routing_meta, "session_usage": evidence}
                row.cost_usd_before = row.cost_usd_after = cost
                session = db.get(GuardSession, row.session_id) if row.session_id and cost else None
                if session:
                    session.total_cost_usd = (session.total_cost_usd or 0.0) + cost
        cursor = (rows[-1].ts, rows[-1].id)
        if apply:
            db.commit()
        else:
            db.rollback()  # dry run never leaves a transaction open
    return stats


def report(stats: dict, apply: bool) -> None:
    print(f"{'APPLIED' if apply else 'DRY RUN'}: {stats['rows']} rows "
          f"(priced {stats['priced_rows']}, still unpriced {stats['unpriced_rows']}, "
          f"totals-only {stats['legacy_no_slices']})")
    print("day, ai_tool, rows, cost_usd")
    for (day, tool), (count, usd) in sorted(stats["by_day_tool"].items()):
        print(f"{day}, {tool}, {count}, {usd:.4f}")
    print("slices covered by gateway:", dict(stats["covered_slices"]) or 0)
    print("slices still unpriced by reason:", dict(stats["unpriced_slices"]) or 0)


if __name__ == "__main__":
    from app.core.database import SessionLocal

    apply_changes = "--apply" in sys.argv[1:]
    with SessionLocal() as session_:
        report(run(session_, apply=apply_changes), apply_changes)
