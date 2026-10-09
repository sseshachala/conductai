"""Gateway-wins rule: client-reported slices the Gateway already billed cost nothing here."""
from uuid import UUID

from app.modules.guard.session_reconciliation import gateway_receipts, match_slice

_NO_SESSION = UUID(int=0)


class GatewayCoverage:
    def __init__(self, receipts):
        self.receipts = receipts

    def classify(self, part: dict):
        """(rule, covered_by) when Gateway receipts already account for this slice, else None."""
        if part.get("provider_response_id") or part.get("gateway_request_id"):
            outcome, _ = match_slice(part, self.receipts.response_map, self.receipts.request_map)
            return ("response_or_request_id_match", "gateway") if outcome == "matched" else None
        # Id-less slices (Codex, Copilot): a session with Gateway receipts is never double counted.
        return ("session_has_gateway_receipts", "gateway_session") if self.receipts.session_linked else None


def coverage_for(db, *, workspace_id, actor, identity, session, parts):
    """Receipt lookup scoped to the authenticated actor; None when the reporter is unidentified."""
    if not actor and not identity:
        return None
    try:
        session = UUID(str(session))
    except ValueError:
        session = _NO_SESSION
    request_ids = set()
    for part in parts:
        try:
            request_ids.add(UUID(str(part["gateway_request_id"])))
        except (KeyError, ValueError, TypeError):
            pass
    response_ids = sorted({p["provider_response_id"] for p in parts if p.get("provider_response_id")})[:100]
    receipts = gateway_receipts(db, workspace_id=workspace_id, actor=actor, identity=identity,
                                session=session, response_ids=response_ids,
                                request_ids=sorted(request_ids)[:100])
    return GatewayCoverage(receipts)


def apply_session_cost(event, body, db, workspace_id, actor, request):
    """Attach priced evidence to a session_usage HookEvent and set its cost columns."""
    from app.modules.guard.session_usage import evidence_cost_usd, usage_evidence

    hook_identity = getattr(getattr(request, "state", None), "guard_hook_identity", None)
    identity = hook_identity[1] if isinstance(hook_identity, tuple) and hook_identity[0] == str(workspace_id) else None
    parts = [p.model_dump(mode="json") for p in body.usage or []]
    coverage = parts and coverage_for(db, workspace_id=workspace_id, actor=actor, identity=identity,
                            session=body.hook_session_id, parts=parts)
    event._session_usage = usage_evidence(body, coverage)
    event.cost_usd_before = event.cost_usd_after = evidence_cost_usd(event._session_usage)
