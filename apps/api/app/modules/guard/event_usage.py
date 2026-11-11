"""Per-event usage detail for Flight Recorder (#2069).

Combines the audit row's own provenance (``usage_source`` / ``usage_status``)
with per-attempt receipts (``llm_attempt_receipts``) for the same request.
Totals come from ``read_request_evidence`` — the one aggregation that never
sums unknown usage as zero and marks a total partial when any attempt is
unknown or an expected attempt has no receipt. Receipts are read once per
request and are never joined, so fallback attempts cannot double count.
"""
from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from app.runtime.accounting.request_evidence import read_request_evidence


def _row_state(event) -> str:
    """pending | known | partial | unavailable | no_upstream | legacy."""
    status = getattr(event, "usage_status", None)
    if status is None:
        return "legacy"
    return "known" if status == "complete" else status


def event_usage(db, event) -> dict:
    row = {
        "input_tokens": event.tokens_before,
        "output_tokens": event.tokens_after,
        "source": getattr(event, "usage_source", None),
        "status": getattr(event, "usage_status", None),
        "state": _row_state(event),
        "cost_usd": event.cost_usd_after,
    }
    out = {"event_id": str(event.id), "request_id": None, "row": row,
           "attempts": [], "totals": None, "coverage": None}
    if not event.request_id:
        return out
    request_id = UUID(str(event.request_id))
    out["request_id"] = str(request_id)
    batch = read_request_evidence(
        db, workspace_id=event.workspace_id,
        requests={request_id: event.agent_identity_id},
    )
    usage = batch.requests[request_id]
    out["attempts"] = [
        {**asdict(a), "id": str(a.id), "request_id": str(a.request_id)} for a in usage.attempts
    ]
    out["totals"] = {
        key: asdict(getattr(usage.totals, key))
        for key in ("input_tokens", "output_tokens", "calculated_cost_microdollars")
    }
    out["coverage"] = {
        "complete": usage.coverage_complete,
        "expected_attempt_count": usage.expected_attempt_count,
        "missing_attempt_count": usage.missing_attempt_count,
    }
    return out
