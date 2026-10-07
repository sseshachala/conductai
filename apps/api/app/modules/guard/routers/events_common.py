"""ConductGuard events — shared schemas, scoping and serialization helpers."""

import ipaddress
from datetime import datetime, timezone
from uuid import UUID
from typing import Literal
import structlog
from fastapi import Request
from pydantic import BaseModel, Field, PrivateAttr, model_validator
from app.modules.guard.session_usage import UsageSlice
from app.core.config import settings
from app.models.workspace import Workspace
from app.modules.guard.models import GuardAuditEvent

log = structlog.get_logger("app.modules.guard.routers.events")


def _trusted_cidrs() -> list[ipaddress._BaseNetwork]:
    """Parsed TRUSTED_PROXY_CIDRS. Small enough to recompute per call — the
    hot path here is DB-bound, not this.
    """
    out: list[ipaddress._BaseNetwork] = []
    for chunk in (settings.trusted_proxy_cidrs or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            log.warning("guard.events.trusted_proxy_cidr_invalid", cidr=chunk)
    return out


def _client_ip_from(request: Request) -> str | None:
    """Extract the caller's IP, respecting only configured trusted proxies
    (audit S12 — same rule as /guard/trial/*).

    Without TRUSTED_PROXY_CIDRS, ignore X-Forwarded-For entirely and use
    request.client.host — blindly trusting the first XFF value lets any
    anonymous caller forge the recorded session IP. With CIDRs set, walk
    XFF right-to-left and return the first non-trusted hop.
    """
    trusted = _trusted_cidrs()
    if not trusted:
        return request.client.host if request.client else None
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if not xff:
        return request.client.host if request.client else None
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    for hop in reversed(hops):
        try:
            ip = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if not any(ip in net for net in trusted):
            return hop
    log.warning("guard.events.all_xff_hops_trusted", xff=xff)
    return hops[0] if hops else (request.client.host if request.client else None)


SSE_POLL_INTERVAL = 2    # seconds between DB polls


SSE_MAX_DURATION  = 300  # reconnect after 5 min


def _org_ws_subquery(db, workspace_id: str):
    """Return a subquery containing only the requested workspace_id.

    Historically this helper broadened queries to every workspace in the same
    org (or every workspace the current user owned when no org was set). That
    broadening silently mixed data across tenants on every list endpoint — see
    issue #1564. Strict single-workspace scoping is the only safe default.

    Legitimate cross-workspace rollups (e.g. an org-admin "all workspaces
    spend" view) must be built as explicit /org/* endpoints gated on
    `guard.*.view_all` permissions — never as silent broadening here.
    """
    import uuid as _uuid
    ws_uuid = _uuid.UUID(workspace_id)
    return db.query(Workspace.id).filter(Workspace.id == ws_uuid)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HookEvent(BaseModel):
    _session_usage: dict | None = PrivateAttr(default=None)
    workspace_id: str
    clerk_user_id: str | None = None
    session_id: str | None = None
    user_email: str | None = None
    ai_tool: str                      # claude_code | claude_chat | claude_desktop | claude_work | codex | codex_cli | codex_chat | cursor | copilot | windsurf | gemini
    tool_call: str                    # bash | edit | write | read
    input_summary: str | None = None
    input_summary_encoding: str | None = None
    decision: str                     # allowed | blocked | warned | approval
    rule_id: str | None = None
    rule_message: str | None = None
    tokens_before: int | None = None
    tokens_after: int | None = None
    tokens_saved: int | None = None
    cost_usd_before: float | None = None
    cost_usd_after: float | None = None
    conductai_run_id: str | None = None
    conductai_workflow: str | None = None
    duration_ms: int | None = None
    tool_use_id: str | None = None
    hook_session_id: str | None = None
    blast_radius: dict | None = None
    os_info: str | None = None
    hostname: str | None = None
    discovery_device_id: UUID | None = None
    discovery_installation_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    goal_id:   str | None = None
    goal_name: str | None = None
    # #1150 phase 1 — layered verdict envelope; hooks may forward the same shape
    evaluated_rules: list[dict] | None = None
    defense_score: int | None = None
    # #1712 Track 1 — hook-side pre-minted receipt id. When present the
    # audit row's PK is set to this uuid so the URL the hook printed to
    # stderr resolves to the row we just wrote. Optional; when absent the
    # row gets its usual server-generated uuid and no receipt is emitted.
    receipt_id: str | None = None


class UsageUpdate(BaseModel):
    workspace_id: str
    hook_session_id: str
    tool_name: str | None = None
    tokens_input: int | None = Field(default=None, ge=0, le=2**31 - 1, strict=True)
    tokens_output: int | None = Field(default=None, ge=0, le=2**31 - 1, strict=True)
    tool_use_id: str | None = None
    duration_ms: int | None = None
    ai_tool: str | None = None   # for pricing
    blast_radius: dict | None = None
    execution_status: str | None = None   # success | error | timeout
    result_summary: str | None = None


class UsageOut(BaseModel):
    updated: bool


class EventOut(BaseModel):
    id: str
    workspace_id: str
    agent_identity_id: str | None = None
    clerk_user_id: str | None
    session_id: str | None
    hook_session_id: str | None = None
    user_email: str | None
    ai_tool: str
    tool_call: str | None
    source: str = "hook"
    provider: str | None = None
    model: str | None = None
    input_summary: str | None
    decision: str
    rule_id: str | None
    rule_message: str | None
    tokens_before: int | None
    tokens_after: int | None
    tokens_saved: int | None
    cost_usd_before: float | None
    cost_usd_after: float | None
    conductai_run_id: str | None
    conductai_workflow: str | None
    conductai_workflow_id: str | None = None
    duration_ms: int | None
    execution_status: str | None = None
    result_summary: str | None = None
    blast_radius: dict | None = None
    ts: str
    entry_hash: str | None = None
    policy_hash: str | None = None
    goal_id:   str | None = None
    goal_name: str | None = None
    # #1150 phase 1 — layered verdict envelope (nullable for pre-migration rows)
    evaluated_rules: list[dict] | None = None
    defense_score: int | None = None
    routing_meta: dict | None = None
    federation: dict | None = None
    # Added by #1973 — FastAPI request path (e.g. /gateway/v1/anthropic/v1/messages).
    # NULL for in-process callers that never had an HTTP route.
    route: str | None = None
    # Added by #1959 Phase 3 — durable audit lifecycle. NULL for legacy
    # single-phase rows; populated for two-phase writes from
    # audit.insert_accepted() / audit.finalize().
    lifecycle_state: str | None = None
    accepted_at: str | None = None
    finalized_at: str | None = None
    lease_expires_at: str | None = None
    request_id: str | None = None


class RuleFireOut(BaseModel):
    """#1755 Slice 2 — safe projection of a rule firing for the Policies UI
    'Recent Firings' panel. Property 9: raw input_summary NEVER surfaces —
    the field is routed through ``redact_secrets`` before serialization
    and augmented with a hash prefix + size hint so consumers can dedupe
    without needing the raw content."""
    id: str
    ts: str
    rule_id: str | None
    decision: str
    tool_call: str | None = None
    source: str
    ai_tool: str
    # Redacted preview (matched-span shape, credentials + emails/SSNs masked).
    input_summary_redacted: str | None = None
    # sha256 of the raw input_summary, first 16 hex chars — dedupe without leaking payload.
    input_hash_prefix: str | None = None
    input_size_bytes: int = 0


def _end_of_day_if_bare(dt):
    """Bare-date `until` like `2026-08-27` parses to midnight → `ts <= that`
    excludes the whole day. When time component is exactly midnight, extend
    to end-of-day so bare-date filters are inclusive."""
    from datetime import time as _time
    if dt is None or dt.time() != _time(0, 0, 0, 0):
        return dt
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def _event_to_dict(e: GuardAuditEvent) -> dict:
    from app.modules.auth.federation.attribution import attribution
    return {
        "id": str(e.id),
        "workspace_id": str(e.workspace_id),
        "agent_identity_id": getattr(e, "agent_identity_id", None),  # column not yet migrated on prod
        "clerk_user_id": e.clerk_user_id,
        "session_id": str(e.session_id) if e.session_id else None,
        "hook_session_id": e.hook_session_id,
        "user_email": e.user_email,
        "ai_tool": e.ai_tool,
        "tool_call": e.tool_call,
        "source": e.source or "hook",
        "provider": e.provider,
        "model": e.model,
        "input_summary": e.input_summary,
        "decision": e.decision,
        "rule_id": e.rule_id,
        "rule_message": e.rule_message,
        "tokens_before": e.tokens_before,
        "tokens_after": e.tokens_after,
        "tokens_saved": e.tokens_saved,
        "cost_usd_before": e.cost_usd_before,
        "cost_usd_after": e.cost_usd_after,
        "conductai_run_id": e.conductai_run_id,
        "conductai_workflow": e.conductai_workflow,
        "conductai_workflow_id": e.conductai_workflow_id,
        "duration_ms": e.duration_ms,
        "execution_status": e.execution_status,
        "result_summary": e.result_summary,
        "blast_radius": e.blast_radius,
        "ts": e.ts.isoformat(),
        "entry_hash": e.entry_hash,
        "evaluated_rules": e.evaluated_rules,
        "defense_score": e.defense_score,
        "routing_meta": getattr(e, "routing_meta", None),
        "federation": attribution(getattr(e, "routing_meta", None)),
        "route": getattr(e, "route", None),
        "lifecycle_state": getattr(e, "lifecycle_state", None),
        "accepted_at": getattr(e, "accepted_at", None) and getattr(e, "accepted_at").isoformat(),
        "finalized_at": getattr(e, "finalized_at", None) and getattr(e, "finalized_at").isoformat(),
        "lease_expires_at": getattr(e, "lease_expires_at", None) and getattr(e, "lease_expires_at").isoformat(),
        "request_id": getattr(e, "request_id", None) and str(getattr(e, "request_id")),
        "policy_hash": e.policy_hash,
        "goal_id": e.goal_id,
        "goal_name": e.goal_name,
    }


class SessionUsageReport(BaseModel):
    workspace_id: UUID
    hook_session_id: UUID
    snapshot_id: UUID
    observed_at: datetime
    input_tokens: int = Field(ge=0, le=2**31 - 1, strict=True)
    output_tokens: int = Field(ge=0, le=2**31 - 1, strict=True)
    ai_tool: Literal["copilot-cli", "codex", "codex-cli", "codex-desktop", "claude-code"] = "copilot-cli"
    usage: list[UsageSlice] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def usage_matches_totals(self):
        if self.usage is not None and (
            sum(p.input_tokens for p in self.usage) != self.input_tokens
            or sum(p.output_tokens for p in self.usage) != self.output_tokens
        ):
            raise ValueError("usage slices must match reported token totals")
        return self


class BatchEventIn(BaseModel):
    events: list[HookEvent]
