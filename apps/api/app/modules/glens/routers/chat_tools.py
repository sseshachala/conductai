"""GLens chat tool catalog + system prompt (split from chat.py).

``TOOLS`` is derived from ``default_registry`` at import time, so this module
imports ``app.tools.registrations`` first for its registration side effect.
"""
from app.tools import registrations as _tool_registrations  # noqa: F401  # side-effect: populate default_registry before TOOLS derives


# ── Tools exposed to the LLM ─────────────────────────────────────────────────
#
# TOOLS is DERIVED from `default_registry` — every ToolDef tagged 'lens' becomes
# an entry the LLM can invoke. `_LEGACY_TOOLS` below carries the hand-tuned
# descriptions from the pre-#1281 catalog; those override the ToolDef.description
# for the ~21 tools that had detailed formatting instructions. New tools use
# their ToolDef.description straight from registrations/lens.py.
#
# Result: one source of truth for the tool catalog. Adding a new ToolDef ⇒ the
# LLM sees it immediately.

_LEGACY_TOOLS = [
    {
        "name": "get_event_count",
        "description": "Count Guard audit events. Use for 'how many blocks/warnings/allows' questions. Returns a single integer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["blocked", "warned", "allowed"], "description": "Filter by decision type"},
                "since": {"type": "string", "description": "ISO date start, e.g. 2026-07-01"},
                "until": {"type": "string", "description": "ISO date end, e.g. 2026-07-31T23:59:59"},
                "rule_id": {"type": "string", "description": "Filter by specific rule ID"},
            },
        },
    },
    {
        "name": "get_recent_events",
        "description": (
            "Fetch recent Guard audit events with details (id, ts, decision, user_email, ai_tool, rule_id, tool_name). "
            "Use for 'what happened', 'who got blocked', 'show recent activity', 'show me blocks'. "
            "When user asks 'show me' or lists 3+ events, format as a markdown table with columns Time | User | Tool | Rule | Decision | Link, "
            "using the returned id to build [View](/logs/guard?id=<id>) in the Link column. "
            "Pass since='today' to filter to today's events. Keep limit<=10 unless user asks for more."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5, "description": "Max events (max 20)"},
                "decision": {"type": "string", "enum": ["blocked", "warned", "allowed"]},
                "since": {"type": "string", "description": "ISO date start"},
                "until": {"type": "string", "description": "ISO date end"},
                "rule_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_spend_summary",
        "description": "Get AI spend/cost summary: total cost, events today, active developers, tokens saved, cost by tool and developer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "YYYY-MM, defaults to current month"},
            },
        },
    },
    {
        "name": "list_policies",
        "description": "List all Guard policies/rules configured for this workspace.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_governance_kpis",
        "description": "Get high-level governance KPIs: blocks today, warnings today, events today, active developers, blocks month-to-date.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_savings_summary",
        "description": "Get token and cost savings from Guard enforcement: tokens blocked, estimated cost saved.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_memory",
        "description": "Semantic search across team memory entries. Use for 'what did the team work on', 'find sessions about X', 'who worked on Y topic'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 5, "description": "Max results (max 10)"},
            },
            "required": ["q"],
        },
    },
    {
        "name": "search_sessions",
        "description": "Semantic search across developer session reports. Use for 'find sessions about X', 'what sessions involved Y', 'show productivity reports for topic Z'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 5, "description": "Max results (max 10)"},
            },
            "required": ["q"],
        },
    },
    {
        "name": "get_discovery_summary",
        "description": "Get live discovery findings: installed tools, possible integrations, scan freshness, configured integrations, and recent hook evidence. These are distinct facts, not a protection percentage or risk score.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_compliance_status",
        "description": "Get compliance posture: overall grade (A-F), score, ASI control statuses, events in last 24h. Use for 'compliance', 'SOC2', 'grade', 'are we compliant', 'ASI controls' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_framework_coverage",
        "description": "List installed compliance framework packs (OWASP, SOC2, HIPAA, etc.) with rule counts. Use for 'which frameworks', 'compliance packs', 'framework coverage' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_budgets",
        "description": "Get spend budgets: workspace-level and per-developer monthly limits, hard limits, alert thresholds. Use for 'budget', 'spending limit', 'who has a cap' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_guard_config",
        "description": "Get Guard configuration: enforcement mode (block/warn/advisory/off), fail mode, whether Slack notifications are on. Use for 'guard settings', 'is guard blocking', 'enforcement mode' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_workflows",
        "description": "List workflows in this workspace's org. Use for 'what workflows do we have', 'show all workflows', 'archived workflows'. status defaults to 'active'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "archived", "all"]},
                "limit": {"type": "integer", "default": 20, "description": "Max rows (max 100)"},
            },
        },
    },
    {
        "name": "list_agent_identities",
        "description": (
            "List agent identities (long-lived AI actor tokens) in this workspace. Use for "
            "'which agents/tokens do we have', 'show deactivated tokens', 'invalidated tokens', "
            "'expired agent identities'. status defaults to 'active'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "deactivated", "pending_review", "expired", "all"],
                    "description": "lifecycle_state filter",
                },
                "limit": {"type": "integer", "default": 20, "description": "Max rows (max 100)"},
            },
        },
    },
    {
        "name": "get_agent_identity_count",
        "description": (
            "Exact COUNT of agent identities matching status. Use for 'how many invalidated/"
            "active/expired identities/tokens' questions. Returns a single integer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "deactivated", "pending_review", "expired", "all"],
                },
            },
        },
    },
    {
        "name": "get_workflow_details",
        "description": (
            "One workflow's full metadata + latest run status. Use when the user asks about "
            "a specific workflow: 'what's the status of workflow X', 'when did X last run', "
            "'is X archived'. Match by workflow_id OR name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Workflow UUID"},
                "name": {"type": "string", "description": "Workflow name"},
            },
        },
    },
    {
        "name": "list_runs",
        "description": (
            "Recent workflow runs across this workspace's org. Use for 'show recent runs', "
            "'what runs failed today', 'runs of workflow X'. Filter by workflow_id, status, "
            "since/until."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Filter to one workflow"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "paused", "succeeded", "failed", "cancelled"],
                },
                "since": {"type": "string", "description": "ISO date start"},
                "until": {"type": "string", "description": "ISO date end"},
                "limit": {"type": "integer", "default": 20, "description": "Max rows (max 100)"},
            },
        },
    },
    {
        "name": "get_run",
        "description": (
            "One run's status + timings + outcome payload. Use when the user asks 'what "
            "happened in run <id>' or drills into a specific run."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run UUID"},
            },
            "required": ["run_id"],
        },
    },
    {"name": "list_pending_approvals", "description": "HITL approval events. Two semantics matter: status='pending' returns only calls still awaiting a decision (the live queue). status='all' returns every approval event including approved/rejected/timed_out. Use status='all' for past-tense questions like 'how many required approvals today' or 'approvals last week' (any status counts). Use status='pending' only for present-tense queue questions ('what needs my approval', 'what is waiting'). Pass since='today' or since='YYYY-MM-DD' to filter by created_at. Default status is 'pending' for backward compat; always specify status='all' when the user asked past-tense. When you show individual approvals to the user, render each as a markdown link on its own line: [<rule_id> · <status>](/theguard/approvals?id=<full-uuid>). The chat surface renders these as clickable links straight to the approval detail.",
     "input_schema": {"type": "object", "properties": {"status": {"type": "string", "enum": ["pending", "approved", "rejected", "timed_out", "all"]}, "since": {"type": "string", "description": "ISO date (YYYY-MM-DD) or the literal string 'today'. Filters created_at >= this date UTC."}, "limit": {"type": "integer", "default": 20}}}},
    {"name": "get_approval", "description": "One approval request by id with the full tool_input payload.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string", "description": "Approval UUID"}}, "required": ["id"]}},
    {"name": "list_installed_packs", "description": "Installed skill packs for this workspace. Use for 'what packs are installed', 'do we have SOC2 pack'.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "browse_marketplace", "description": "Available skill packs in the marketplace. Substring search on slug/name/description.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 20}}}},
    {"name": "get_pack_details", "description": "One skill pack's rules and metadata.",
     "input_schema": {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]}},
    {"name": "list_integrations", "description": "Configured integrations (Slack, GitHub, Okta). Use for 'what integrations are set up'.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_integration_status", "description": "Status of one integration by service name. Use for 'is Slack connected'.",
     "input_schema": {"type": "object", "properties": {"service": {"type": "string"}}, "required": ["service"]}},
    {"name": "list_members", "description": "Workspace members with role. Use for 'who is on the team', 'who are the admins'.",
     "input_schema": {"type": "object", "properties": {"role": {"type": "string", "enum": ["admin", "developer", "security", "viewer"]}, "limit": {"type": "integer", "default": 50}}}},
    {"name": "get_member", "description": "One workspace member's role + join info.",
     "input_schema": {"type": "object", "properties": {"clerk_user_id": {"type": "string"}}, "required": ["clerk_user_id"]}},
    {"name": "get_audit_events", "description": "Platform audit log — invites, role changes, credential edits, run triggers. Separate from Guard events.",
     "input_schema": {"type": "object", "properties": {"actor_email": {"type": "string"}, "action": {"type": "string"}, "resource_type": {"type": "string"}, "since": {"type": "string"}, "until": {"type": "string"}, "limit": {"type": "integer", "default": 25}}}},
    {"name": "search_audit_log", "description": "Substring search across audit action, actor_email, resource_type, resource_id.",
     "input_schema": {"type": "object", "properties": {"q": {"type": "string"}, "limit": {"type": "integer", "default": 25}}, "required": ["q"]}},
    {"name": "list_projects", "description": "Projects in this workspace.",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 50}}}},
    {"name": "get_project", "description": "One project by UUID or slug.",
     "input_schema": {"type": "object", "properties": {"id_or_slug": {"type": "string"}}, "required": ["id_or_slug"]}},
    {"name": "list_alerts", "description": "Watchdog alerts — stale worker, credential expiry, silent playbook, repeated failures. Excludes resolved unless include_resolved=true.",
     "input_schema": {"type": "object", "properties": {"severity": {"type": "string", "enum": ["info", "warning", "error"]}, "event_type": {"type": "string"}, "include_resolved": {"type": "boolean"}, "since": {"type": "string"}, "limit": {"type": "integer", "default": 25}}}},
    {"name": "get_alert", "description": "One watchdog alert by id.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "list_run_events", "description": "Events emitted during one workflow run. Use for 'what happened during run X', 'which blocks failed'.",
     "input_schema": {"type": "object", "properties": {"run_id": {"type": "string"}, "kind": {"type": "string"}, "limit": {"type": "integer", "default": 100}}, "required": ["run_id"]}},
    {
        "name": "get_blocked_workflows",
        "description": (
            "Workflows Guard has blocked, ranked by block count. Use for 'which workflow triggered a block', "
            "'which workflows are being blocked', 'top blocked workflows'. Filter by workflow_id or rule_id "
            "to drill in. since/until narrow the window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "ISO date start"},
                "until": {"type": "string", "description": "ISO date end"},
                "workflow_id": {"type": "string", "description": "Filter to one workflow"},
                "rule_id": {"type": "string", "description": "Filter to one rule"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
]

# Detailed descriptions from the hand-tuned catalog (index by tool name).
_LEGACY_DESCRIPTIONS: dict[str, str] = {t["name"]: t["description"] for t in _LEGACY_TOOLS}


def _lens_tools_for_llm() -> list[dict]:
    """Project every 'lens'-tagged ToolDef in default_registry into the LLM's
    function-calling shape. Detailed descriptions from _LEGACY_DESCRIPTIONS
    override the ToolDef.description for the 21 tools that had specialised
    formatting instructions; new tools use their ToolDef.description straight
    from registrations/lens.py."""
    from app.tools.registry import default_registry

    return [
        {
            "name": t.name,
            "description": _LEGACY_DESCRIPTIONS.get(t.name, t.description),
            "input_schema": t.input_schema,
        }
        for t in default_registry.list(tag="lens")
    ]


TOOLS = _lens_tools_for_llm()


def _load_system_prompt() -> str:
    from pathlib import Path
    return (Path(__file__).parent.parent / "prompts" / "system.txt").read_text()


_SYSTEM = _load_system_prompt()
