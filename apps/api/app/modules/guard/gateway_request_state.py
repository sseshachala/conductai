"""Per-request state threaded through the Gateway lifecycle phases (#2399).

``handle_gateway_request`` used to keep ~60 locals in one 1,500-line
function. The phases (``gateway_phase_*``) now share one mutable
``GatewayCall``: each phase reads what earlier phases resolved and writes
what it resolves, at the same point the old local was assigned. Fields
the handler's outer ``finally`` reads (admission ticket, profile-rate
admission, v2 plan) are written the moment they are acquired so cleanup
sees them on every exit path, exactly as before.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import BackgroundTasks, Request


@dataclass
class GatewayCall:
    # ── entry arguments ──────────────────────────────────────────────
    request: Request
    background: BackgroundTasks
    provider: str
    upstream_path: str
    auth_header_in: str
    auth_header_out: str
    auth_header_fallback: str | None
    bearer: bool
    canonical_profile: bool
    operation: str
    started: float

    # ── read by the handler's outer finally ──────────────────────────
    admission_ticket: Any = None
    profile_rate_admission: Any = None
    v2_plan: Any = None

    # ── identity (gateway_phase_ingress) ─────────────────────────────
    token: str | None = None
    internal_key: str = ""
    is_internal: bool = False
    needs_run_token_validation: bool = False
    needs_agent_validation: bool = False
    workspace_id: str | None = None
    clerk_user_id: str | None = None
    agent_identity_id: str | None = None
    agent_risk_tier: str | None = None
    federation: Any = None

    # ── body + routing (gateway_phase_routing) ───────────────────────
    body: Any = None
    model: str | None = None
    routing_meta: dict | None = None
    tools_offered: list = field(default_factory=list)
    tool_names_supplied: list = field(default_factory=list)
    ai_tool: str | None = None
    user_email: str | None = None
    run_id: str | None = None
    workflow: str | None = None
    workflow_id: str | None = None
    environment_id: str | None = None
    hook_session_id: str | None = None
    is_trial: bool = False

    # ── prompt gate (gateway_phase_policy) ───────────────────────────
    prompt_summary: str = ""
    decision: dict | None = None
    guidance_text: str | None = None
    audit_decision: str = "allowed"
    audit_rule_id: str | None = None

    # ── v1 upstream + outbound request (gateway_phase_upstream) ──────
    upstream: Any = None
    upstream_key: Any = None
    vault_key_val: Any = None
    transport: Any = None
    real_key: Any = None
    is_stream: bool = False
    extra_headers: dict = field(default_factory=dict)
    client_request_id: str | None = None

    # ── durable audit + budget (gateway_phase_reserve) ───────────────
    durable: Any = None
    durable_row_id: Any = None
    audit_request_id: Any = None
    reservations: list = field(default_factory=list)

    @property
    def agent_identity_str(self) -> str | None:
        """``str(_agent_identity_id) if _agent_identity_id else None``."""
        return str(self.agent_identity_id) if self.agent_identity_id else None
