"""Read-only session correlation. Reported deltas never become ledger charges."""
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import or_, select

from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.modules.guard.models import GuardAuditEvent
from app.runtime.accounting.request_evidence import read_request_evidence, rollup_request_evidence


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
    response_ids = {part.get("provider_response_id") for row in reports
                    for part in row.routing_meta["session_usage"].get("slices", [])
                    if isinstance(part.get("provider_response_id"), str)}
    response_ids_truncated = len(response_ids) > 100
    response_ids = sorted(response_ids)[:100]
    request_ids = set()
    for row in reports:
        for part in row.routing_meta["session_usage"].get("slices", []):
            try:
                request_ids.add(UUID(part["gateway_request_id"]))
            except (KeyError, ValueError, TypeError):
                pass
    request_ids_truncated = len(request_ids) > 100
    request_ids = sorted(request_ids)[:100]
    found = gateway_receipts(db, workspace_id=event.workspace_id, actor=actor, identity=identity,
                             session=session, response_ids=response_ids, request_ids=request_ids)
    requests, ambiguous, gateway_truncated = found.requests, found.ambiguous, found.truncated
    evidence = read_request_evidence(db, workspace_id=event.workspace_id, requests=requests)
    response_map, request_map = found.response_map, found.request_map
    matching = match_reported_usage(reports, response_map, request_map)
    matching["truncated"] = response_ids_truncated or request_ids_truncated
    matching["complete"] = matching["complete"] and not matching["truncated"]
    gateway = asdict(evidence.totals)
    gateway_rollups = [{**item, "totals": asdict(item["totals"])}
                       for item in rollup_request_evidence(evidence)]
    reported_groups = reported_rollups(reports)
    if reports_truncated:
        for group in reported_groups:
            if group["cost_status"] == "estimated":
                group["cost_status"] = "partial"
    if gateway_truncated or ambiguous:
        for key in ("input_tokens", "output_tokens", "calculated_cost_microdollars"):
            if gateway[key]["status"] == "complete":
                gateway[key]["status"] = "partial"
        for group in gateway_rollups:
            for key in ("input_tokens", "output_tokens", "calculated_cost_microdollars"):
                if group["totals"][key]["status"] == "complete":
                    group["totals"][key]["status"] = "partial"
    return {
        "hook_session_id": str(session), "scope": "session",
        "link_status": "request_id_linked" if matching["linked_attempts"] else "session_id_linked" if requests else "unlinked",
        "overlap": "reported_totals_match" if matching["complete"] else "unknown",
        "combined_cost_microdollars": gateway["calculated_cost_microdollars"]["value"]
            if matching["complete"] and not reports_truncated and not gateway_truncated and not ambiguous
            and gateway["calculated_cost_microdollars"]["status"] == "complete" else None,
        "matching": matching,
        "rollups": {
            "reported": reported_groups,
            "gateway": gateway_rollups,
        },
        "reported": {
            "snapshot_count": len(reports), "truncated": reports_truncated,
            "input_tokens": sum(row.tokens_before or 0 for row in reports),
            "output_tokens": sum(row.tokens_after or 0 for row in reports),
            "estimated_microdollars": sum(known) if known else None,
            "cost_status": "estimated" if known and len(known) == len(reports) and not reports_truncated
                           and all(row.routing_meta["session_usage"].get("cost_status", "estimated") == "estimated" for row in reports)
                           else "partial" if known else "unpriced",
            "unpriced_snapshot_count": sum(
                row.routing_meta["session_usage"].get("cost_status", "estimated") != "estimated"
                or type(row.routing_meta["session_usage"].get("estimated_microdollars")) is not int
                for row in reports), "budget_eligible": False,
        },
        "gateway": {**gateway, "truncated": gateway_truncated,
                    "ambiguous_request_count": len(ambiguous)},
        "request_ids": [str(key) for key in requests],
    }


@dataclass
class GatewayReceipts:
    requests: dict
    ambiguous: set
    truncated: bool
    response_map: dict
    request_map: dict
    session_linked: bool = False


def gateway_receipts(db, *, workspace_id, actor, identity, session, response_ids, request_ids):
    """Gateway receipts correlated to an authenticated actor by session, response id or request id."""
    r = LlmAttemptReceipt
    filters = [r.workspace_id == workspace_id,
               r.source.in_(["gateway", "proxy"])]
    if actor:
        filters.append(r.developer_external_id == actor)
    if identity:
        filters.append(r.agent_identity_id == identity)
    correlation = or_(r.hook_session_id == session,
                      r.calculation_provenance["provider_response_id"].astext.in_(response_ids),
                      r.request_id.in_(request_ids))
    pairs = db.execute(select(r.request_id, r.agent_identity_id).where(*filters, correlation)
                       .distinct().order_by(r.request_id).limit(101)).all()
    truncated = len(pairs) > 100
    # A request with conflicting identities is not a safe join key.
    requests = {}
    ambiguous = set()
    for request_id, agent_id in pairs[:100]:
        if request_id in requests and requests[request_id] != agent_id:
            ambiguous.add(request_id)
        requests[request_id] = agent_id
    for request_id in ambiguous:
        requests.pop(request_id)
    identities = db.execute(select(r.request_id, r.agent_identity_id, r.attempt_ordinal, r.provider, r.model,
        r.total_input_tokens, r.total_output_tokens, r.usage_completeness, r.execution_outcome,
        r.calculation_provenance).where(
            *filters, r.request_id.in_(requests), correlation)).all() if requests else []
    response_map = {}
    request_map = {}
    for receipt in identities:
        if requests.get(receipt.request_id) != receipt.agent_identity_id:
            continue
        key = (receipt.calculation_provenance or {}).get("provider_response_id")
        if key:
            response_map.setdefault(key, []).append(receipt)
        if receipt.execution_outcome == "succeeded":
            request_map.setdefault(str(receipt.request_id), []).append(receipt)
    linked = db.execute(select(r.request_id).where(*filters, r.hook_session_id == session).limit(1)).first()
    return GatewayReceipts(requests, ambiguous, truncated, response_map, request_map, linked is not None)


def reported_rollups(reports):
    groups = {}
    for row in reports:
        meta = row.routing_meta["session_usage"]
        parts = meta.get("slices") or [{"model": None, "provider": None,
            "uncached_input_tokens": row.tokens_before or 0, "output_tokens": row.tokens_after or 0,
            "estimated_microdollars": meta.get("estimated_microdollars")}]
        for part in parts:
            key = (part.get("provider"), part.get("model"))
            group = groups.setdefault(key, {"provider": key[0], "model": key[1], "input_tokens": 0,
                "output_tokens": 0, "estimated_microdollars": None, "unpriced_slice_count": 0,
                "pricing_versions": set(), "budget_eligible": False})
            group["input_tokens"] += sum(part.get(field, 0) for field in
                ("uncached_input_tokens", "cache_read_tokens", "cache_write_tokens"))
            group["output_tokens"] += part.get("output_tokens", 0)
            cost = part.get("estimated_microdollars")
            if type(cost) is int and cost >= 0:
                group["estimated_microdollars"] = (group["estimated_microdollars"] or 0) + cost
            else:
                group["unpriced_slice_count"] += 1
            if meta.get("pricing_version"):
                group["pricing_versions"].add(meta["pricing_version"])
    for group in groups.values():
        group["pricing_versions"] = sorted(group["pricing_versions"])
        group["cost_status"] = "unpriced" if group["estimated_microdollars"] is None else (
            "partial" if group["unpriced_slice_count"] else "estimated")
    return list(groups.values())


def match_slice(part, response_map, request_map=None):
    """("matched", receipt) | ("unmatched", None) | ("mismatched", None) for one reported slice."""
    candidates = response_map.get(part.get("provider_response_id"), [])
    if part.get("gateway_request_id"):
        direct = (request_map or {}).get(str(part["gateway_request_id"]), [])
        if part.get("provider_response_id") and candidates != direct:
            return "mismatched", None
        candidates = direct
    # Ambiguous provider IDs are not filtered into a false unique match.
    if len(candidates) != 1:
        return "unmatched", None
    receipt = candidates[0]
    if ((part.get("provider") and part["provider"] != receipt.provider)
            or (part.get("model") and part["model"] != receipt.model)):
        return "mismatched", None
    return "matched", receipt


def match_reported_usage(reports, response_map, request_map=None):
    """Exact protocol IDs plus authenticated scope; never time/model similarity."""
    linked = {}
    unmatched = mismatched = slice_count = 0
    legacy = 0
    for row in reports:
        parts = row.routing_meta["session_usage"].get("slices", [])
        if not parts:
            legacy += 1
        for part in parts:
            slice_count += 1
            outcome, receipt = match_slice(part, response_map, request_map)
            if outcome != "matched":
                unmatched += outcome == "unmatched"
                mismatched += outcome == "mismatched"
                continue
            key = (receipt.request_id, receipt.attempt_ordinal)
            item = linked.setdefault(key, {"request_id": str(receipt.request_id),
                "attempt_ordinal": receipt.attempt_ordinal, "input_tokens": 0, "output_tokens": 0,
                "receipt_input_tokens": receipt.total_input_tokens, "receipt_output_tokens": receipt.total_output_tokens,
                "receipt_complete": receipt.usage_completeness == "complete"})
            item["input_tokens"] += sum(part.get(field, 0) for field in
                ("uncached_input_tokens", "cache_read_tokens", "cache_write_tokens"))
            item["output_tokens"] += part.get("output_tokens", 0)
    for item in linked.values():
        item["totals_match"] = item.pop("receipt_complete") and (
            item["input_tokens"] == item["receipt_input_tokens"]
            and item["output_tokens"] == item["receipt_output_tokens"])
    return {"linked_attempts": list(linked.values()), "slice_count": slice_count,
            "unmatched_slice_count": unmatched, "mismatched_slice_count": mismatched,
            "legacy_snapshot_count": legacy,
            "complete": bool(linked) and not unmatched and not mismatched and not legacy
                and all(item["totals_match"] for item in linked.values())}
