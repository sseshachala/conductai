"""Read-only session correlation. Reported deltas never become ledger charges."""
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select

from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.modules.guard.models import GuardAuditEvent
from app.runtime.accounting.request_evidence import read_request_evidence


def session_evidence(db, event):
    session = UUID(event.hook_session_id)
    actor, identity = event.clerk_user_id, event.agent_identity_id
    if not actor and not identity:
        raise ValueError("Session has no authenticated actor")
    family = ["codex", "codex-cli", "codex-desktop"] if event.ai_tool.startswith("codex") else [event.ai_tool]
    a = GuardAuditEvent
    reports = db.execute(select(a.tokens_before, a.tokens_after, a.routing_meta).where(
        a.workspace_id == event.workspace_id, a.hook_session_id == str(session),
        a.clerk_user_id == actor, a.agent_identity_id == identity,
        a.ai_tool.in_(family), a.tool_call == "session_usage",
        a.routing_meta["session_usage"]["source"].astext == "client_reported",
    ).order_by(a.ts, a.id).limit(1001)).all()
    reports_truncated = len(reports) > 1000
    reports = reports[:1000]
    estimates = [r.routing_meta["session_usage"].get("estimated_microdollars") for r in reports]
    known = [value for value in estimates if type(value) is int and value >= 0]
    r = LlmAttemptReceipt
    filters = [r.workspace_id == event.workspace_id, r.hook_session_id == session,
               r.source.in_(["gateway", "proxy"])]
    if actor:
        filters.append(r.developer_external_id == actor)
    if identity:
        filters.append(r.agent_identity_id == identity)
    pairs = db.execute(select(r.request_id, r.agent_identity_id).where(*filters)
                       .distinct().order_by(r.request_id).limit(101)).all()
    gateway_truncated = len(pairs) > 100
    # A request with conflicting identities is not a safe join key.
    requests = {}
    ambiguous = set()
    for request_id, agent_id in pairs[:100]:
        if request_id in requests and requests[request_id] != agent_id:
            ambiguous.add(request_id)
        requests[request_id] = agent_id
    for request_id in ambiguous:
        requests.pop(request_id)
    evidence = read_request_evidence(db, workspace_id=event.workspace_id, requests=requests)
    gateway = asdict(evidence.totals)
    if gateway_truncated or ambiguous:
        for key in ("input_tokens", "output_tokens", "calculated_cost_microdollars"):
            if gateway[key]["status"] == "complete":
                gateway[key]["status"] = "partial"
    return {
        "hook_session_id": str(session), "scope": "session",
        "link_status": "session_id_linked" if requests else "unlinked",
        "overlap": "unknown", "combined_cost_microdollars": None,
        "reported": {
            "snapshot_count": len(reports), "truncated": reports_truncated,
            "input_tokens": sum(row.tokens_before or 0 for row in reports),
            "output_tokens": sum(row.tokens_after or 0 for row in reports),
            "estimated_microdollars": sum(known) if known else None,
            "cost_status": "estimated" if known and len(known) == len(reports) and not reports_truncated
                           else "partial" if known else "unpriced",
            "unpriced_snapshot_count": len(reports) - len(known), "budget_eligible": False,
        },
        "gateway": {**gateway, "truncated": gateway_truncated,
                    "ambiguous_request_count": len(ambiguous)},
        "request_ids": [str(key) for key in requests],
    }
