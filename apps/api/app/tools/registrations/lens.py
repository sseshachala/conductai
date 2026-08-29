"""Lens tool registrations for the default ToolRegistry.

Every ToolDef here surfaces on the MCP HTTP surface, the stdio surface,
and Lens chat via app.mcp.lens_adapter — same policy gate everywhere.
Dispatch is enforced by MCPCore for MCP callers and by lens_adapter for
Lens chat callers (both run the composable policy engine).

── Adding a new Lens tool ────────────────────────────────────────────

**New tools skip Executor** (team convention, 2026-08-29 / #1281 sweep).
Write the impl as a free function in this module (or a companion module
under app/modules/glens/) and point ToolDef.impl at it directly:

    def get_soc2_status(ctx, framework: str = "SOC2"):
        from app.core.database import SessionLocal
        from app.modules.governance.rollup import compute_framework_coverage
        db = SessionLocal()
        try:
            return compute_framework_coverage(db, ctx.workspace_id, framework=framework)
        finally:
            db.close()

    _TOOLS.append(ToolDef(
        name="get_soc2_status",
        description="Framework coverage % + gaps for SOC2 / HIPAA / NIST AI RMF / EU AI Act.",
        input_schema={"type": "object", "properties": {"framework": {"type": "string"}}},
        impl=get_soc2_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ))

── Legacy tools (44 tools, via Executor) ─────────────────────────────

The 44 tools registered below via `_impl(method_name)` still route
through `Executor._tool_{method_name}` (see app/modules/glens/executor.py).
Kept as-is post-#1422 — no big-bang migration. New tools use the free-
function pattern above so the codebase gradually flattens without churn.

Read-only over Guard DB state; three of them (search_memory,
search_sessions, search_knowledge) call the embedding provider and one
(get_governance_narrative) calls the LLM — marked open_world for those.
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


# ── #1295 + #1420 governance rollup tools ────────────────────────────────────
# First tools registered under the new convention: free functions (no
# Executor._tool_* shim). Impls import _compute_framework_coverage from the
# governance router — a pure computation, safe to import.

def _run_framework_coverage(workspace_id: str):
    from app.core.database import SessionLocal
    from app.routers.governance import _compute_framework_coverage
    db = SessionLocal()
    try:
        return _compute_framework_coverage(db, workspace_id)
    finally:
        db.close()


def get_governance_summary(ctx):
    """Full framework coverage matrix — installed + bonus + rules totals."""
    return _run_framework_coverage(ctx.workspace_id).model_dump()


def get_soc2_status(ctx, framework: str = "SOC2"):
    """Rollup for a single compliance framework. Defaults to SOC2. Returns
    installed status + rules + controls + recommended pack for uninstalled."""
    from app.routers.governance import RECOMMENDED_PACK
    result = _run_framework_coverage(ctx.workspace_id)
    fw = framework.upper()
    for row in result.installed:
        if row.framework == fw:
            return {"status": "installed", **row.model_dump()}
    for row in result.bonus:
        if row.framework == fw:
            return {"status": "bonus", **row.model_dump()}
    return {
        "status": "not_covered",
        "framework": fw,
        "rules_count": 0,
        "controls": [],
        "packs": [],
        "recommended_pack": RECOMMENDED_PACK.get(fw),
    }


def get_ai_rollout_status(ctx):
    """AI rollout instructions published for the workspace — published flag,
    content length, version, last update, publisher."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.workspace_instructions import WorkspaceInstructions
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        row = db.query(WorkspaceInstructions).filter(
            WorkspaceInstructions.workspace_id == ws_uuid
        ).first()
        if row is None:
            return {
                "published": False,
                "content_length": 0,
                "version": None,
                "updated_at": None,
                "updated_by": None,
            }
        return {
            "published": True,
            "content_length": len(row.content or ""),
            "version": row.version,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by,
        }
    finally:
        db.close()


_TOOLS.extend([
    ToolDef(
        name="get_governance_summary",
        description="Full framework coverage matrix — installed frameworks, bonus (cross-tag) coverage, and rules totals.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_governance_summary,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_soc2_status",
        description="Rollup for one compliance framework (defaults to SOC2). Returns installed status + rules + controls + recommended pack.",
        input_schema={
            "type": "object",
            "properties": {
                "framework": {
                    "type": "string",
                    "description": "Framework name: SOC2, HIPAA, OWASP, PCI_DSS, ISO_42001, GDPR, EU_AI_ACT, NIST, NIS2, DORA.",
                },
            },
            "required": [],
        },
        impl=get_soc2_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_ai_rollout_status",
        description="AI rollout instructions published for the workspace — published flag, content length, version, last update.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_ai_rollout_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
])


# ── #1281 batch A — small-lookup read tools ──────────────────────────────────
# Playbooks (#1413), sync state (#1416), LLM primitives (#1418), rate limits
# (#1419). All free-function ToolDefs per the new convention.

def list_playbooks(ctx, category: str | None = None):
    """Playbook catalog — builtin templates + user-submitted templates.
    Optional category filter (e.g. 'incident_response', 'ci_cd')."""
    from app.core.database import SessionLocal
    from app.routers.playbooks import _TEMPLATE_PLAYBOOKS, _PLAYBOOK_META
    from app.models.workflow import Workflow

    entries: list[dict] = []
    for slug in _TEMPLATE_PLAYBOOKS:
        meta = _PLAYBOOK_META.get(slug)
        if not meta:
            continue
        if category and meta.get("category") != category:
            continue
        entries.append({
            "slug": slug,
            "name": slug.replace("_", " ").title(),
            "description": meta.get("description"),
            "category": meta.get("category", "Other"),
            "tags": meta.get("tags", []),
            "featured": meta.get("featured", False),
            "source": "builtin",
        })
    db = SessionLocal()
    try:
        db_playbooks = (
            db.query(Workflow)
            .filter(Workflow.workspace_id == ctx.workspace_id, Workflow.is_template == True)  # noqa: E712
            .all()
        )
        for wf in db_playbooks:
            entries.append({
                "slug": wf.playbook_slug or str(wf.id),
                "name": wf.name,
                "description": "",
                "category": "custom",
                "tags": [],
                "featured": False,
                "source": "user",
            })
    finally:
        db.close()
    return {"count": len(entries), "playbooks": entries}


def get_playbook(ctx, slug: str):
    """Playbook detail — name, description, blocks, inputs, YAML source."""
    from app.routers.playbooks import get_playbook as _get_playbook_route
    try:
        return _get_playbook_route(slug)
    except Exception as e:
        return {"error": str(e), "slug": slug}


def list_machines_sync_state(ctx, filter: str = "all"):
    """Per-machine sync state — user_email, detected tools, mcp_registered,
    hook_registered, last_sync_at, in_sync. filter=out_of_sync returns only
    machines missing a tool registration.

    GuardDeveloperTools.workspace_id is Text, not UUID, so we pass a string
    directly (no uuid conversion).
    """
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardDeveloperTools
    db = SessionLocal()
    try:
        rows = (
            db.query(GuardDeveloperTools)
            .filter(GuardDeveloperTools.workspace_id == ctx.workspace_id)
            .order_by(GuardDeveloperTools.reported_at.desc())
            .all()
        )
        out: list[dict] = []
        for r in rows:
            detected = list(r.detected_tools or [])
            mcp_reg = list(r.mcp_registered or [])
            hook_reg = list(r.hook_registered or [])
            in_sync = all(t in mcp_reg or t in hook_reg for t in detected)
            if filter == "out_of_sync" and in_sync:
                continue
            out.append({
                "user_email": r.user_email,
                "detected_tools": detected,
                "mcp_registered": mcp_reg,
                "hook_registered": hook_reg,
                "last_sync_at": r.reported_at.isoformat() if r.reported_at else None,
                "in_sync": in_sync,
            })
        return {"count": len(out), "machines": out}
    finally:
        db.close()


def get_llm_primitives(ctx):
    """Workspace LLM routing config — preferred provider + per-tier models
    (cheap / balanced / smart). API keys are never returned; those live in
    Vault."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.workspace_llm_primitives import WorkspaceLLMPrimitives
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        row = db.query(WorkspaceLLMPrimitives).filter(
            WorkspaceLLMPrimitives.workspace_id == ws_uuid
        ).first()
        if row is None:
            return {
                "configured": False,
                "preferred_provider": "anthropic",
                "tier_map": {},
                "updated_at": None,
            }
        return {
            "configured": True,
            "preferred_provider": row.preferred_provider,
            "tier_map": row.tier_map or {},
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    finally:
        db.close()


def get_rate_limits(ctx):
    """Workspace rate limits — default RPM/TPM plus any per-agent overrides.
    Blocks return 429 with x-guard reason when either cap trips."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardRateLimit
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        rows = db.query(GuardRateLimit).filter(GuardRateLimit.workspace_id == ws_uuid).all()
        default_row = next((r for r in rows if r.agent_identity_id is None), None)
        overrides = [
            {
                "agent_identity_id": r.agent_identity_id,
                "rpm": r.rpm,
                "tpm": r.tpm,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows if r.agent_identity_id is not None
        ]
        return {
            "default": {
                "rpm": default_row.rpm if default_row else None,
                "tpm": default_row.tpm if default_row else None,
                "updated_at": default_row.updated_at.isoformat() if default_row and default_row.updated_at else None,
            },
            "overrides": overrides,
            "override_count": len(overrides),
        }
    finally:
        db.close()


_TOOLS.extend([
    ToolDef(
        name="list_playbooks",
        description="Playbook catalog — builtin templates + user-submitted templates. Optional category filter (e.g. 'incident_response', 'ci_cd').",
        input_schema={
            "type": "object",
            "properties": {"category": {"type": "string", "description": "Filter by category slug."}},
            "required": [],
        },
        impl=list_playbooks,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_playbook",
        description="Playbook detail — name, description, blocks, inputs, YAML source.",
        input_schema={
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "Playbook slug (e.g. 'incident_response')."}},
            "required": ["slug"],
        },
        impl=get_playbook,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_machines_sync_state",
        description="Per-machine Guard sync state — detected tools vs MCP/hook registrations. filter=out_of_sync returns only unsynced machines.",
        input_schema={
            "type": "object",
            "properties": {"filter": {"type": "string", "description": "'all' (default) or 'out_of_sync'."}},
            "required": [],
        },
        impl=list_machines_sync_state,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_llm_primitives",
        description="Workspace LLM routing config — preferred provider + per-tier models. API keys are never returned.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_llm_primitives,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_rate_limits",
        description="Workspace rate limits — default RPM/TPM plus any per-agent overrides.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_rate_limits,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
])


# ── #1281 batch B — join-heavy read tools ────────────────────────────────────
# Workspace KPIs (#1414), Discovery (#1415), Vault metadata (#1417), autopilot
# activity (#1296). All free-function ToolDefs per the new convention.

def _window_start(time_window: str):
    """Resolve a symbolic time window to a UTC datetime lower bound."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    if time_window == "last_7d":
        return now - timedelta(days=7)
    if time_window == "mtd":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(hours=24)  # last_24h default


def get_workspace_kpis(ctx, time_window: str = "last_24h"):
    """Rollup counters for the workspace over a time window.

    Returns: blocked_calls (Guard blocks in window), spend (proxy cost sum),
    runs {total/succeeded/failed} (workflow runs in window), active_agents
    (distinct agent identities in window).
    """
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardAuditEvent
    from app.models.run import Run
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        since = _window_start(time_window)

        blocked_calls = (
            db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.decision == "block",
                GuardAuditEvent.ts >= since,
            )
            .count()
        )

        spend_rows = (
            db.query(GuardAuditEvent.cost_usd_after)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.ts >= since,
                GuardAuditEvent.cost_usd_after.isnot(None),
            )
            .all()
        )
        spend_total = sum((r[0] or 0.0) for r in spend_rows)

        runs = (
            db.query(Run)
            .filter(Run.workspace_id == ws_uuid, Run.created_at >= since)
            .all()
        )
        run_status: dict[str, int] = {}
        for r in runs:
            run_status[r.status] = run_status.get(r.status, 0) + 1

        active_agents = (
            db.query(GuardAuditEvent.agent_identity_id)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.ts >= since,
                GuardAuditEvent.agent_identity_id.isnot(None),
            )
            .distinct()
            .count()
        )

        return {
            "time_window": time_window,
            "since": since.isoformat(),
            "blocked_calls": blocked_calls,
            "spend": {"amount_usd": round(spend_total, 6), "currency": "USD"},
            "runs": {
                "total": sum(run_status.values()),
                "succeeded": run_status.get("succeeded", 0),
                "failed": run_status.get("failed", 0),
                "by_status": run_status,
            },
            "active_agents": active_agents,
        }
    finally:
        db.close()


def list_discovered_agents(ctx, framework: str | None = None, since: str | None = None):
    """Discovered AI agents in the workspace — name, framework, source,
    risk_score, under_guard, proxy_routed. Optional framework filter (e.g.
    'langchain', 'crewai') and since ISO-8601 lower bound on last_seen_at.
    """
    import uuid as _uuid
    from datetime import datetime
    from app.core.database import SessionLocal
    from app.modules.guard.models import DiscoveredAgent
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id == ws_uuid)
        if framework:
            q = q.filter(DiscoveredAgent.framework == framework)
        if since:
            try:
                q = q.filter(DiscoveredAgent.last_seen_at >= datetime.fromisoformat(since))
            except ValueError:
                pass
        rows = q.order_by(DiscoveredAgent.last_seen_at.desc()).all()
        return {
            "count": len(rows),
            "agents": [
                {
                    "name": r.name,
                    "framework": r.framework,
                    "source": r.source,
                    "location": r.location,
                    "risk_score": r.risk_score,
                    "under_guard": r.under_guard,
                    "proxy_routed": r.proxy_routed,
                    "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
                    "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


def list_credentials(ctx, environment_id: str | None = None, service: str | None = None):
    """Vault inventory — service + handle + auth_method + scopes + last_used_at
    per Integration row. NEVER returns encrypted_credentials or any raw
    secret material.

    Optional filters: environment_id (Vault UUID), service
    (github / slack / linear / …).
    """
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.integration import Integration
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(Integration).filter(Integration.workspace_id == ws_uuid)
        if service:
            q = q.filter(Integration.service == service)
        if environment_id:
            try:
                q = q.filter(Integration.environment_id == _uuid.UUID(environment_id))
            except ValueError:
                pass
        rows = q.order_by(Integration.created_at.desc()).all()
        return {
            "count": len(rows),
            "credentials": [
                {
                    "id": str(r.id),
                    "service": r.service,
                    "handle": r.handle,
                    "auth_method": r.auth_method,
                    "scopes": r.scopes or [],
                    "environment_id": str(r.environment_id) if r.environment_id else None,
                    "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


def get_autopilot_activity(ctx, since: str | None = None, limit: int = 50, status: str | None = None):
    """Feed of autopilot-driven security activity. Synthesized from
    SecurityFinding rows scoped to this workspace, ordered by updated_at
    desc. Optional since (ISO-8601 lower bound on updated_at), status
    (open/triaging/fixed/dismissed), limit (default 50, max 500).
    """
    import uuid as _uuid
    from datetime import datetime
    from app.core.database import SessionLocal
    from app.models.security_finding import SecurityFinding
    limit = min(max(int(limit or 50), 1), 500)
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(SecurityFinding).filter(SecurityFinding.workspace_id == ws_uuid)
        if status:
            q = q.filter(SecurityFinding.status == status)
        if since:
            try:
                q = q.filter(SecurityFinding.updated_at >= datetime.fromisoformat(since))
            except ValueError:
                pass
        rows = q.order_by(SecurityFinding.updated_at.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "findings": [
                {
                    "id": str(r.id),
                    "tool": r.tool,
                    "severity": r.severity,
                    "type": r.type,
                    "file": r.file,
                    "line": r.line,
                    "description": r.description,
                    "status": r.status,
                    "repo_full_name": r.repo_full_name,
                    "run_id": r.run_id,
                    "github_issue_url": r.github_issue_url,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


_TOOLS.extend([
    ToolDef(
        name="get_workspace_kpis",
        description="Workspace rollup — blocked calls, spend, workflow runs, active agents over a time window (last_24h / last_7d / mtd).",
        input_schema={
            "type": "object",
            "properties": {
                "time_window": {"type": "string", "description": "'last_24h' (default) / 'last_7d' / 'mtd'."},
            },
            "required": [],
        },
        impl=get_workspace_kpis,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_discovered_agents",
        description="AI agents discovered in this workspace by the discovery daemon. Optional framework filter (langchain/crewai/…) and since lower bound.",
        input_schema={
            "type": "object",
            "properties": {
                "framework": {"type": "string"},
                "since": {"type": "string", "description": "ISO-8601 lower bound on last_seen_at"},
            },
            "required": [],
        },
        impl=list_discovered_agents,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_credentials",
        description="Vault inventory — metadata only. Returns service, handle, auth_method, scopes, environment, last_used_at. NEVER returns the secret value.",
        input_schema={
            "type": "object",
            "properties": {
                "environment_id": {"type": "string", "description": "Filter by environment (Vault) UUID."},
                "service": {"type": "string", "description": "Filter by service slug (github/slack/…)"},
            },
            "required": [],
        },
        impl=list_credentials,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_autopilot_activity",
        description="Autopilot feed — recent SecurityFinding rows (open/triaging/fixed/dismissed). Optional since (ISO-8601) + status filter + limit (default 50, max 500).",
        input_schema={
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "ISO-8601 lower bound on updated_at"},
                "status": {"type": "string", "description": "Filter: open/triaging/fixed/dismissed"},
                "limit": {"type": "integer", "minimum": 1},
            },
            "required": [],
        },
        impl=get_autopilot_activity,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
])


# ── #1439 batch — /dashboard + /observability KPI parity ─────────────────────
# Free-function ToolDefs mirroring the router-side computations so Lens chat
# and MCP callers can read every card on those pages. See #1439 for the roadmap.

def get_dashboard_outcomes(ctx, time_window: str = "last_7d"):
    """Outcome rollup for the workspace over a time window — matches the
    header of /dashboard: PRs opened, issues triaged, reviews completed,
    incidents investigated, plus succeeded/failed automation counts.
    """
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.routers.insights import _outcome_type

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        since = _window_start(time_window)

        rows = (
            db.query(Run, Workflow.playbook_slug.label("slug"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .filter(Workflow.workspace_id == ws_uuid, Run.created_at >= since)
            .all()
        )

        prs = issues = reviews = incidents = ok = fail = 0
        for run, slug in rows:
            if run.status == "succeeded":
                ok += 1
                ot = _outcome_type(run, slug)
                if ot == "pr_opened":
                    prs += 1
                elif ot == "issue_triaged":
                    issues += 1
                elif ot == "review_completed":
                    reviews += 1
                elif ot == "incident_investigated":
                    incidents += 1
            elif run.status == "failed":
                fail += 1

        return {
            "time_window": time_window,
            "since": since.isoformat(),
            "prs_opened": prs,
            "issues_triaged": issues,
            "reviews_completed": reviews,
            "incidents_investigated": incidents,
            "successful_automations": ok,
            "failed_automations": fail,
        }
    finally:
        db.close()


_TOOLS.extend([
    ToolDef(
        name="get_dashboard_outcomes",
        description="Workspace outcome rollup — PRs opened, issues triaged, reviews completed, incidents investigated, succeeded/failed automations. Matches the /dashboard header.",
        input_schema={
            "type": "object",
            "properties": {
                "time_window": {
                    "type": "string",
                    "description": "One of last_24h, last_7d (default), mtd.",
                },
            },
            "required": [],
        },
        impl=get_dashboard_outcomes,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
])


def register(replace: bool = False) -> None:
    """Register all Lens tools into the default registry. Idempotent when
    replace=True (used only in tests that reload)."""
    default_registry.register_all(_TOOLS, replace=replace)


# Side-effect on import: populate the registry.
register()
