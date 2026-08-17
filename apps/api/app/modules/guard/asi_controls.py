"""OWASP Agentic Security Initiative (ASI) top-10 taxonomy.

Fixed taxonomy - 10 rows, changes only when OWASP publishes a new revision.
Kept in code because it is not per-workspace state (see audit/03).

Each row = (id, name, control_description, active_predicate). The predicate
receives a SimpleNamespace of live signals and returns "active" | "partial"
| "missing".
"""
from __future__ import annotations

from types import SimpleNamespace


def _tri(is_active: bool, guard_active: bool) -> str:
    if is_active:    return "active"
    if guard_active: return "partial"
    return "missing"


CONTROLS = [
    ("ASI-01", "Prompt Injection",         "PreToolUse hook intercepts before LLM call",
        lambda c: _tri(c.guard_active, c.guard_active)),
    ("ASI-02", "Insecure Tool Use",        "Guard proxy enforces tool-use policies",
        lambda c: _tri(c.guard_active, c.guard_active)),
    ("ASI-03", "Excessive Agency",         "Turn and cost limits on runs",
        # ponytail: token_guardrails is the current proxy; upgrade when
        # GuardConfig gains explicit per-run turn and cost columns
        lambda c: _tri(c.guardrails_configured, c.guard_active)),
    ("ASI-04", "Unauthorized Escalation",  "RBAC + require_permission() on all endpoints",
        lambda c: _tri(c.role_count > 0, c.guard_active)),
    ("ASI-05", "Trust Boundary Violation", "All LLM traffic routed through Guard proxy",
        lambda c: _tri(c.guard_active, c.guard_active)),
    ("ASI-06", "Insufficient Logging",     "guard_audit_events with SHA-256 hash chain",
        lambda c: _tri(c.guard_active and c.events_24h > 0 and c.chain_live, c.guard_active)),
    ("ASI-07", "Insecure Identity",        "agent_role_id + member tokens per agent",
        lambda c: _tri(c.agent_identity_count > 0, c.guard_active)),
    ("ASI-08", "Policy Bypass",            "fail_mode=fail_closed on Guard outage",
        lambda c: "active" if c.fail_closed else "partial"),
    ("ASI-09", "Supply Chain Integrity",   "Signed policies (signing_key)",
        lambda c: "active" if c.signing_key else "missing"),
    ("ASI-10", "Behavioral Anomaly",       "Session scanning + violations_count tracking",
        # ponytail: sessions_24h > 0 proxies scanner-running; upgrade to
        # sum(GuardSession.violations_count) once every scanner path writes it
        lambda c: _tri(c.sessions_24h > 0, c.guard_active)),
]


def evaluate(ctx: SimpleNamespace) -> list[tuple[str, str, str, str]]:
    """Return [(asi_id, name, control_description, status), ...]."""
    return [(asi, name, control, fn(ctx)) for asi, name, control, fn in CONTROLS]
