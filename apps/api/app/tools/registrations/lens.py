"""Lens Executor tool registrations for the default ToolRegistry.

Each ToolDef.impl opens a SessionLocal, instantiates Executor bound to the
caller's workspace, and dispatches to the matching `_tool_*` method. Every
tool goes through MCPCore's policy gate before this impl runs, so we call
`_tool_*` directly (bypassing Executor.call's second guard eval) — one
policy source of truth per request.

Tools are read-only over Guard DB state; three of them (search_memory,
search_sessions, search_knowledge) call the embedding provider and one
(get_governance_narrative) calls the LLM — marked open_world for those.

Adding a new Lens tool: add the method to Executor, add a ToolDef here.
That's it.
"""
from __future__ import annotations

from typing import Any, Callable

from app.tools.registry import default_registry
from app.tools.types import ToolAnnotations, ToolDef


def _run(method_name: str, workspace_id: str, kwargs: dict[str, Any]) -> Any:
    """Open a session, dispatch to Executor._tool_{method_name}, close."""
    from app.core.database import SessionLocal
    from app.modules.glens.executor import Executor

    db = SessionLocal()
    try:
        executor = Executor(db, workspace_id)
        fn = getattr(executor, f"_tool_{method_name}", None)
        if fn is None:
            return {"error": f"Executor is missing tool: {method_name}"}
        return fn(**kwargs)
    finally:
        db.close()


def _impl(method_name: str) -> Callable[..., Any]:
    """Build a ctx-accepting impl for one Lens tool."""
    def _lens_impl(ctx, **kwargs):  # ctx: MCPContext
        return _run(method_name, ctx.workspace_id, kwargs)
    _lens_impl.__name__ = f"lens_impl_{method_name}"
    return _lens_impl


# ── Common schema shapes ──────────────────────────────────────────────────────

_LIMIT = {"type": "integer", "description": "Max rows to return", "minimum": 1}
_DECISION = {
    "type": "string",
    "description": "Filter by decision (blocked/allowed/warned/audited). Aliases: block/allow/warn/audit.",
}
_TS_SINCE = {"type": "string", "description": "ISO-8601 lower bound on event timestamp"}
_TS_UNTIL = {"type": "string", "description": "ISO-8601 upper bound on event timestamp"}
_RULE_ID = {"type": "string", "description": "Filter by rule_id"}

_READ_ONLY = ToolAnnotations(read_only=True)
_READ_ONLY_OPEN_WORLD = ToolAnnotations(read_only=True, open_world=True)

_LENS_TAGS = ("lens",)


# ── The 21 tools ──────────────────────────────────────────────────────────────

_TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_spend_summary",
        description="Guard workspace spend summary — events today, cost, active devs, tokens saved. Optional month filter (YYYY-MM).",
        input_schema={"type": "object", "properties": {"month": {"type": "string"}}, "required": []},
        impl=_impl("get_spend_summary"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_recent_events",
        description="Recent Guard audit events, optionally filtered by decision, rule_id, time range.",
        input_schema={
            "type": "object",
            "properties": {
                "limit": _LIMIT, "decision": _DECISION,
                "since": _TS_SINCE, "until": _TS_UNTIL, "rule_id": _RULE_ID,
            },
            "required": [],
        },
        impl=_impl("get_recent_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_sessions",
        description="Recent Guard sessions (agent transcripts) for the workspace.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=_impl("get_sessions"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_event_count",
        description="Exact COUNT of audit events matching filters. Use for 'how many X' questions.",
        input_schema={
            "type": "object",
            "properties": {
                "decision": _DECISION, "since": _TS_SINCE,
                "until": _TS_UNTIL, "rule_id": _RULE_ID,
            },
            "required": [],
        },
        impl=_impl("get_event_count"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_memory",
        description="Semantic search across team session memory (past agent work summaries).",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": _LIMIT},
            "required": ["q"],
        },
        impl=_impl("search_memory"),
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_sessions",
        description="Semantic search across session reports (Guard-generated agent transcripts).",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": _LIMIT},
            "required": ["q"],
        },
        impl=_impl("search_sessions"),
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_team_memory_feed",
        description="Recent team memory entries. No embeddings required.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=_impl("get_team_memory_feed"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_session_reports_feed",
        description="Recent session reports. No embeddings required.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=_impl("get_session_reports_feed"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_policies",
        description="All custom workspace policies (rule_id, enabled, persona, action, description).",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("list_policies"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_policy",
        description="Full body of one custom policy by rule_id.",
        input_schema={
            "type": "object",
            "properties": {"rule_id": {"type": "string"}},
            "required": ["rule_id"],
        },
        impl=_impl("get_policy"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_knowledge",
        description="Semantic search across all Guard knowledge (audit events, rules, discovered agents). Optional kind filter.",
        input_schema={
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "kind": {"type": "string", "description": "Optional source_kind filter"},
                "limit": _LIMIT,
            },
            "required": ["q"],
        },
        impl=_impl("search_knowledge"),
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_guard_config",
        description="Workspace Guard config — enforcement mode, fail mode, persona, notification settings.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_guard_config"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_budgets",
        description="Workspace and per-developer spend budgets.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_budgets"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_discovery_summary",
        description="Discovered agents inventory — total, coverage, high-risk agents, per-framework breakdown.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_discovery_summary"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_compliance_status",
        description="ASI-01..10 compliance scorecard for this workspace (grade, score, per-control status).",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_compliance_status"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_governance_kpis",
        description="Governance KPIs — events today, blocks today, active devs today, blocks MTD, risk avoided MTD.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_governance_kpis"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_framework_coverage",
        description="Installed compliance packs and rules count per framework (OWASP, SOC2, HIPAA, etc.).",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_framework_coverage"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_correlated_events",
        description="Guard audit events grouped by session. Defaults to blocked events. Time-bounded via since/until.",
        input_schema={
            "type": "object",
            "properties": {
                "decision": _DECISION, "since": _TS_SINCE,
                "until": _TS_UNTIL, "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("get_correlated_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_savings_summary",
        description="Team token/cost savings from RTK + Booster.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_savings_summary"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_governance_narrative",
        description="LLM-generated governance narrative for the workspace. Calls the configured LLM provider.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_governance_narrative"),
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_recent_governance_events",
        description="Recent governance-relevant audit events (blocked, warned, audited by default).",
        input_schema={
            "type": "object",
            "properties": {
                "limit": _LIMIT, "decision": _DECISION,
                "since": _TS_SINCE, "until": _TS_UNTIL,
            },
            "required": [],
        },
        impl=_impl("get_recent_governance_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_workflows",
        description="Enumerate workflows in this workspace's org. status = active (default) | archived | all.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "archived", "all"]},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("list_workflows"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    # ── Approvals (#1287) ─────────────────────────────────────────────────
    ToolDef(
        name="list_pending_approvals",
        description="HITL approval queue. status = pending (default) | approved | rejected | timed_out | all.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "approved", "rejected", "timed_out", "all"]},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("list_pending_approvals"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_approval",
        description="One approval request with full tool_input payload.",
        input_schema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Approval UUID"}},
            "required": ["id"],
        },
        impl=_impl("get_approval"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    # ── Packs (#1288) ─────────────────────────────────────────────────────
    ToolDef(
        name="list_installed_packs",
        description="List installed skill packs for this workspace's org.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("list_installed_packs"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="browse_marketplace",
        description="Available skill packs in the catalog (latest version per slug). Optional query for substring match on slug/name/description.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Substring search"},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("browse_marketplace"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_pack_details",
        description="One skill pack's latest version with the full rule list.",
        input_schema={
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "Pack slug"}},
            "required": ["slug"],
        },
        impl=_impl("get_pack_details"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    # ── Integrations (#1289) ──────────────────────────────────────────────
    ToolDef(
        name="list_integrations",
        description="All integrations (Slack, GitHub, Okta, Vercel, ...) configured for this workspace.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("list_integrations"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_integration_status",
        description="One integration by service. Returns configured=false if none.",
        input_schema={
            "type": "object",
            "properties": {"service": {"type": "string", "description": "e.g. github, slack, okta, vercel"}},
            "required": ["service"],
        },
        impl=_impl("get_integration_status"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    # ── Team members (#1290) ──────────────────────────────────────────────
    ToolDef(
        name="list_members",
        description="Workspace members with role. Optional role filter (admin/developer/security/viewer).",
        input_schema={
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["admin", "developer", "security", "viewer"]},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("list_members"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_member",
        description="One workspace member's role + join info by Clerk user id.",
        input_schema={
            "type": "object",
            "properties": {"clerk_user_id": {"type": "string"}},
            "required": ["clerk_user_id"],
        },
        impl=_impl("get_member"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    # ── Platform audit log (#1291) ────────────────────────────────────────
    ToolDef(
        name="get_audit_events",
        description=(
            "Platform audit events (invites, role changes, credential edits, run triggers). "
            "Separate from Guard events — this is org-wide platform activity."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "actor_email": {"type": "string"},
                "action": {"type": "string", "description": "e.g. run.triggered, invite.sent"},
                "resource_type": {"type": "string"},
                "since": _TS_SINCE, "until": _TS_UNTIL,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("get_audit_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_audit_log",
        description="Substring search across audit action, actor_email, resource_type, resource_id.",
        input_schema={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search query"},
                "limit": _LIMIT,
            },
            "required": ["q"],
        },
        impl=_impl("search_audit_log"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    # ── Projects (#1292) ──────────────────────────────────────────────────
    ToolDef(
        name="list_projects",
        description="Projects in this workspace.",
        input_schema={
            "type": "object",
            "properties": {"limit": _LIMIT},
            "required": [],
        },
        impl=_impl("list_projects"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_project",
        description="One project by UUID or slug.",
        input_schema={
            "type": "object",
            "properties": {"id_or_slug": {"type": "string"}},
            "required": ["id_or_slug"],
        },
        impl=_impl("get_project"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    # ── Observability alerts (#1293) ──────────────────────────────────────
    ToolDef(
        name="list_alerts",
        description=(
            "Watchdog alerts (stale worker, credential expiry, silent playbook, "
            "repeated failures). Excludes resolved unless include_resolved=true."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                "event_type": {"type": "string"},
                "include_resolved": {"type": "boolean"},
                "since": _TS_SINCE,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("list_alerts"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_alert",
        description="One watchdog alert with full payload.",
        input_schema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Alert UUID"}},
            "required": ["id"],
        },
        impl=_impl("get_alert"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    # ── Run logs (#1294) ──────────────────────────────────────────────────
    ToolDef(
        name="list_run_events",
        description=(
            "Events emitted during one workflow run — block_started/completed/failed, "
            "approval_requested, etc. Use when the user asks 'what happened during run X'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run UUID"},
                "kind": {"type": "string", "description": "Filter to one event kind"},
                "limit": _LIMIT,
            },
            "required": ["run_id"],
        },
        impl=_impl("list_run_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_agent_identities",
        description=(
            "List agent identities in this workspace. status = active (default) | "
            "deactivated | pending_review | expired | all. Returns id, name, "
            "token_prefix, lifecycle_state, risk_tier, source, created_at, "
            "deactivated_at, last_used_at, expires_at."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "deactivated", "pending_review", "expired", "all"],
                },
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("list_agent_identities"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_agent_identity_count",
        description=(
            "Exact COUNT of agent identities matching status. Use for 'how many "
            "invalidated/active/expired identities' questions."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "deactivated", "pending_review", "expired", "all"],
                },
            },
            "required": [],
        },
        impl=_impl("get_agent_identity_count"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_workflow_details",
        description=(
            "One workflow's full metadata + latest run status. Match by workflow_id "
            "OR name. Use when the user asks 'what's the status of workflow X'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Workflow UUID"},
                "name": {"type": "string", "description": "Workflow name"},
            },
            "required": [],
        },
        impl=_impl("get_workflow_details"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_runs",
        description=(
            "Recent workflow runs across this workspace's org. Filters: "
            "workflow_id, status (pending/running/paused/succeeded/failed/cancelled), "
            "since/until (ISO ts). Returns run_id, workflow_id, workflow_name, "
            "status, started_at, completed_at, triggered_by, actual_turns."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Filter to one workflow"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "paused", "succeeded", "failed", "cancelled"],
                },
                "since": _TS_SINCE, "until": _TS_UNTIL,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("list_runs"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_run",
        description=(
            "One run's status + timings + outcome payload. Use when the user asks "
            "'what happened in run <id>' or drills into a specific run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run UUID"},
            },
            "required": ["run_id"],
        },
        impl=_impl("get_run"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_blocked_workflows",
        description=(
            "Workflows Guard has blocked, ranked by block count. Returns "
            "[{workflow_id, name, block_count, top_rule_id, last_blocked_at}]. "
            "Optional filters: since/until (ISO ts), workflow_id, rule_id."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "since": _TS_SINCE, "until": _TS_UNTIL,
                "workflow_id": {"type": "string", "description": "Filter to one workflow"},
                "rule_id": _RULE_ID,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("get_blocked_workflows"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]


def register(replace: bool = False) -> None:
    """Register all Lens tools into the default registry. Idempotent when
    replace=True (used only in tests that reload)."""
    default_registry.register_all(_TOOLS, replace=replace)


# Side-effect on import: populate the registry.
register()
