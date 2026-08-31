"""
POST /glens/chat/stream  — GLens governance assistant (tool-use + prose)

Sessions / feedback / opener / policy / config / guard_config / spend_config
live in sibling router modules (#1459 split). Helpers used across those
files sit in `_helpers.py`.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.glens.executor import Executor
from app.modules.glens.models import GlensChatSession
from app.tools import registrations as _tool_registrations  # noqa: F401  # side-effect: populate default_registry before TOOLS derives

from ._helpers import _get_session, _parse_workspace_id

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens", tags=["glens"])


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
        "description": "Get discovered AI agents: total count, how many are under Guard, coverage %, high-risk agents, breakdown by framework. Use for 'what agents are running', 'agent coverage', 'unguarded agents', 'risk score' questions.",
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


# ── LLM config resolution (PR C of #1347) ─────────────────────────────────────

def _llm_config(executor):
    """Resolve (client, provider, model) for a Lens session from the workspace
    primitives (issue #1347) and the workspace vault.

    - provider + model come from workspace_llm_primitives; falls back to
      seeded defaults if the workspace has no row yet.
    - api_key is looked up in the workspace vault by provider handle;
      falls back to "unused" (which the client turns into a 401 on first
      call — an operator-fixable error, not silent misuse of a stale key).
    """
    from app.runtime.model_router import resolve_for_workspace
    from app.runtime.llm_client import client_for
    from app.core.credentials import get_credential

    provider, model, reason = resolve_for_workspace(
        db=executor.db,
        workspace_id=executor.workspace_id,
        routing_preference="balanced",
    )

    api_key = "unused"
    if executor.db and executor.workspace_id:
        try:
            creds = get_credential(executor.db, executor.workspace_id, provider)
            api_key = creds.get("api_key") or api_key
        except Exception:
            pass

    log.debug("glens.llm_resolved", provider=provider, model=model, reason=reason)
    return client_for(provider, api_key=api_key), provider, model


# ── Core tool loop ────────────────────────────────────────────────────────────

_APOLOGY_PHRASES = (
    "there is an issue", "unable to retrieve", "i cannot provide",
    "i am unable", "it seems", "i'm unable", "cannot access",
    "having trouble", "experiencing an issue",
)

def _answer_is_apology(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _APOLOGY_PHRASES)


def _has_data(final_msgs: list[dict]) -> bool:
    """Return False only when every tool result was an empty/zero-count response."""
    tool_contents = [m.get("content", "") for m in final_msgs if m.get("role") == "tool"]
    if not tool_contents:
        return False
    for content in tool_contents:
        try:
            r = json.loads(content) if isinstance(content, str) else content
            if isinstance(r, dict):
                if "count" in r and int(r["count"]) > 0:
                    return True
                if "count" not in r:
                    return True  # spend/policy/etc results always have data
            elif isinstance(r, list) and len(r) > 0:
                return True
        except Exception:
            return True
    return False


def _extract_confirm_envelope(final_msgs: list[dict]) -> dict | None:
    """First tool result whose JSON body has confirm_required=True.
    Surfaces the actor envelope (from require_confirmation) to the SSE 'done'
    event so the frontend can render ActionConfirmBubble instead of prose.

    OpenAI/Perplexity shape:  {"role": "tool", "content": "<json>"}
    Anthropic shape:          {"role": "user", "content": [{"type": "tool_result", "content": "<json>"}, ...]}
    """
    def _match(raw) -> dict | None:
        try:
            r = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return None
        if isinstance(r, dict) and r.get("confirm_required") and r.get("approval_request_id"):
            return r
        return None

    for m in final_msgs:
        content = m.get("content", "")
        if m.get("role") == "tool":
            hit = _match(content)
            if hit:
                return hit
        elif m.get("role") == "user" and isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") == "tool_result":
                    hit = _match(blk.get("content", ""))
                    if hit:
                        return hit
    return None


def _build_drilldown(tool_calls: list[tuple[str, dict]]) -> str | None:
    """Build a grounded drilldown URL from the tool calls the LLM actually made."""
    page = "/logs/guard"
    filters: dict[str, str] = {}

    for name, args in tool_calls:
        if name in ("get_event_count", "get_recent_events"):
            if args.get("decision"):
                filters["decision"] = args["decision"]
            if args.get("since"):
                filters["since"] = args["since"]
            if args.get("until"):
                filters["until"] = args["until"]
            if args.get("rule_id"):
                filters["rule_id"] = args["rule_id"]
        elif name == "get_blocked_workflows":
            page = "/theguard/activity"
            filters["decision"] = "blocked"
            if args.get("since"):    filters["since"] = args["since"]
            if args.get("until"):    filters["until"] = args["until"]
            if args.get("workflow_id"): filters["workflow_id"] = args["workflow_id"]
            if args.get("rule_id"):  filters["rule_id"] = args["rule_id"]
        elif name == "list_workflows":
            page = "/workflows"
        elif name == "get_workflow_details":
            wid = args.get("workflow_id")
            page = f"/workflows/{wid}" if wid else "/workflows"
        elif name in ("list_runs",):
            page = "/runs"
            if args.get("workflow_id"): filters["workflow_id"] = args["workflow_id"]
            if args.get("status"):      filters["status"] = args["status"]
            if args.get("since"):       filters["since"] = args["since"]
            if args.get("until"):       filters["until"] = args["until"]
        elif name == "get_run":
            rid = args.get("run_id")
            page = f"/runs/{rid}" if rid else "/runs"
        elif name in ("list_agent_identities", "get_agent_identity_count"):
            page = "/agent-identity"
            if args.get("status") and args["status"] != "all":
                filters["status"] = args["status"]
        elif name in ("get_spend_summary", "get_savings_summary", "get_budgets"):
            page = "/theguard/spend"
        elif name in ("list_policies", "get_guard_config"):
            page = "/theguard/policies"
        elif name in ("get_discovery_summary",):
            page = "/theguard/discovery"
        elif name in ("get_compliance_status", "get_framework_coverage"):
            page = "/theguard/compliance"
        elif name in ("list_pending_approvals", "get_approval"):
            page = "/theguard/approvals"
            if args.get("status") and args["status"] != "all":
                filters["status"] = args["status"]
        elif name in ("list_installed_packs", "browse_marketplace", "get_pack_details"):
            slug = args.get("slug")
            page = f"/packs/{slug}" if slug else "/packs"
        elif name in ("list_integrations", "get_integration_status"):
            page = "/integrations"
        elif name in ("list_members", "get_member"):
            page = "/theguard/team"
            if args.get("role"):
                filters["role"] = args["role"]
        elif name in ("get_audit_events", "search_audit_log"):
            page = "/audit"
            if args.get("actor_email"):   filters["actor"] = args["actor_email"]
            if args.get("action"):        filters["action"] = args["action"]
            if args.get("resource_type"): filters["resource_type"] = args["resource_type"]
            if args.get("since"):         filters["since"] = args["since"]
            if args.get("until"):         filters["until"] = args["until"]
        elif name == "list_projects":
            page = "/projects"
        elif name == "get_project":
            page = f"/projects/{args.get('id_or_slug')}" if args.get("id_or_slug") else "/projects"
        elif name in ("list_alerts", "get_alert"):
            page = "/observability/alerts"
            if args.get("severity"):   filters["severity"] = args["severity"]
            if args.get("event_type"): filters["event_type"] = args["event_type"]
        elif name == "list_run_events":
            rid = args.get("run_id")
            page = f"/runs/{rid}" if rid else "/runs"

    if not filters and page == "/logs/guard":
        return None
    if "since" in filters and "until" not in filters:
        filters["until"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if filters:
        qs = "&".join(f"{k}={v}" for k, v in filters.items())
        return f"{page}?{qs}"
    return page


def _guarded_openai_completion(executor: Executor, provider: str, model: str,
                                client, messages: list[dict], system: str,
                                tools: list[dict] | None, max_tokens: int):
    """In-process guarded LLM call for Lens — routes through the LLMClient.

    Same composable policy engine as the HTTP proxy, no self-HTTP hop.
    Provider + model come from _llm_config() (workspace primitives)."""
    from app.guard.gateway import guarded_client_call, GuardedLLMBlocked as _Blocked

    try:
        return guarded_client_call(
            client=client,
            workspace_id=executor.workspace_id,
            provider=provider, model=model,
            messages=messages, system=system,
            tools=tools, max_tokens=max_tokens,
            ai_tool="lens",
            clerk_user_id="system:lens",
            agent_identity_id=executor.agent_identity_id,
            prompt_summary="lens.resolve_tools",
        )
    except _Blocked as blk:
        raise Exception(f"Guard blocked Lens call: {blk.detail}") from blk


def _resolve_tools(messages: list[dict], system: str, executor: Executor) -> tuple[list[dict], str | None, list[tuple[str, dict]]]:
    """Phase 1: Execute tool calls. Returns (final_msgs, early_text, tool_calls_made).

    Each LLM turn goes through Guard's in-process `guarded_llm_call` (#1254) —
    same policy + audit path as the HTTP proxy. Tool dispatch itself goes
    through `lens_adapter.dispatch` (#1227) so Lens shares the same
    ToolRegistry as the MCP HTTP/stdio surfaces. When the LLM emits N
    tool_use blocks in a single turn (Lens commonly does 2-4), they run
    concurrently via `dispatch_tool_blocks` — SQLAlchemy handles concurrent
    sessions on separate connections so this scales cleanly to any tool
    count the DB pool can sustain.
    """
    from app.mcp.lens_adapter import dispatch as lens_dispatch
    from app.mcp.server import MCPContext
    from app.runtime.llm_client import LLMToolUseBlock
    from app.runtime.tool_dispatch import dispatch_tool_blocks

    client, provider, model = _llm_config(executor)
    log.info("glens.llm_call", provider=provider, model=model)
    msgs = list(messages)
    tool_calls_made: list[tuple[str, dict]] = []

    lens_ctx = MCPContext(
        workspace_id=executor.workspace_id,
        clerk_user_id="system:lens",
        surface="lens",
    )

    def _bound_dispatcher(name: str, args_json: str) -> str:
        return lens_dispatch(name, args_json, lens_ctx)

    for _ in range(5):
        resp = _guarded_openai_completion(
            executor, provider, model, client,
            messages=msgs, system=system, tools=TOOLS, max_tokens=512,
        )
        tool_blocks = [b for b in resp.content if isinstance(b, LLMToolUseBlock)]
        text = next((b.text for b in resp.content if hasattr(b, "text") and b.text), "")

        if not tool_blocks:
            return msgs, text or "I couldn't find relevant data to answer that.", tool_calls_made

        msgs.extend(client.make_assistant_turn(resp))
        for b in tool_blocks:
            tool_calls_made.append((b.name, b.input))
        results = dispatch_tool_blocks(tool_blocks, _bound_dispatcher)
        for name_and_input, (_id, result) in zip(
            [(b.name, b.input) for b in tool_blocks],
            results,
        ):
            log.debug("glens.tool", name=name_and_input[0], result_len=len(result))
        msgs.extend(client.make_tool_results_turn(results))

    return msgs, None, tool_calls_made


def _stream_synthesis(msgs: list[dict], system: str, executor: Executor, on_token,
                       lens_session_token: str | None = None) -> str:
    """Phase 2: stream the final synthesis. Guard-enforced end to end.

    Routes through `guarded_client_stream` → `LLMClient.stream()`. Same
    policy engine + audit as Phase 1. Vendor-neutral (env-var selection +
    per-workspace credential vault, same as every other LLMClient
    consumer)."""
    from app.guard.gateway import guarded_client_stream

    client, provider, model = _llm_config(executor)
    log.info("glens.stream_synthesis", provider=provider, model=model)
    text = guarded_client_stream(
        client=client,
        workspace_id=executor.workspace_id,
        provider=provider, model=model,
        messages=msgs, system=system, max_tokens=1024,
        on_token=on_token,
        ai_tool="lens",
        clerk_user_id="system:lens",
        agent_identity_id=executor.agent_identity_id,
        prompt_summary="lens.synthesis",
    )
    return text or "Could not complete the analysis."


# ── Session helpers used only by the stream endpoint ─────────────────────────

def _should_refresh_summary(messages: list[dict]) -> bool:
    user_count = sum(1 for m in messages if m.get("role") == "user")
    return user_count % 5 == 0 and len(messages) > 10


def _bg_save_session(session_id: str, messages: list[dict], title: str | None) -> None:
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        sess = db.query(GlensChatSession).filter(GlensChatSession.id == uuid.UUID(session_id)).first()
        if sess:
            sess.messages = json.dumps(messages)
            if title:
                sess.title = title[:60]
            sess.updated_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        log.warning("glens.session.save_failed", session_id=session_id, error=str(exc))
    finally:
        db.close()


def _build_llm_messages(session_messages: list[dict]) -> list[dict]:
    """Extract clean user/assistant turns for LLM context (last 20)."""
    result = []
    for m in session_messages:
        if m["role"] == "system":
            continue
        if m["role"] == "assistant":
            try:
                content = json.loads(m["content"]).get("answer", m["content"])
            except Exception:
                content = m["content"]
            result.append({"role": "assistant", "content": content})
        else:
            result.append({"role": m["role"], "content": m["content"]})
    return result[-20:]


# ── Chat stream ───────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    page_context: str | None = None


@router.post("/chat/stream")
async def glens_chat_stream(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    logger = log.bind(workspace_id=workspace_id)

    session = None
    if req.session_id:
        session = _get_session(db, req.session_id, ws_uuid)
    if not session:
        session = GlensChatSession(workspace_id=ws_uuid, title=req.message[:60], messages=json.dumps([]))
        db.add(session)
        db.flush()
        db.commit()

    # Mint session-scoped Lens token — #1218 Step 3b.3.
    # Fresh session with no token OR pre-migration session (token_hash NULL):
    # mint here. Existing session with a live token: overwrite (previous raw
    # token loses access, which is fine — single stream per session).
    # Raw token held in closure state and passed to guarded_completion;
    # never persisted, never returned to the client.
    from app.modules.glens import tokens as _lens_tokens
    _lens_session_token = _lens_tokens.mint_for_session(db, session)

    # Mint a session-scoped AgentIdentity so every Lens LLM egress carries a
    # real `agent_identity_id` through PolicyContext (SpendCap +
    # ThroughputCap activate on the composable engine). Idempotent: only
    # mint if the session doesn't already have one. Plaintext token is
    # discarded — Lens calls are in-process, no HTTP boundary needs it.
    if not getattr(session, "agent_identity_id", None):
        from app.modules.agent_identity.router import mint_agent_identity as _mint_ai
        _identity, _plain = _mint_ai(
            db, workspace_id, f"lens-session-{str(session.id)[:8]}"
        )
        session.agent_identity_id = _identity.id
        db.add(session)
        db.commit()

    session_messages = json.loads(session.messages)
    session_messages.append({"role": "user", "content": req.message})
    session_id_str = str(session.id)
    executor = Executor(db, workspace_id, agent_identity_id=session.agent_identity_id)

    _now = datetime.now(timezone.utc)
    today = _now.strftime("%Y-%m-%d")
    # Pre-format the human-readable date so the LLM doesn't reformat and drift
    # (gpt-4o-mini fabricated "August 26" when today was "2026-08-27").
    today_display = _now.strftime("%A, %B %-d, %Y") + " UTC"
    system = _SYSTEM.format(today=today, today_display=today_display)
    llm_messages = _build_llm_messages(session_messages)

    loop = asyncio.get_running_loop()
    event_q: asyncio.Queue[dict] = asyncio.Queue()

    async def _run_work() -> None:
        from app.modules.glens.grounding import check_grounded
        try:
            # Phase 1: resolve tool calls (fast, non-streaming)
            final_msgs, early_text, tool_calls = await asyncio.to_thread(_resolve_tools, llm_messages, system, executor)
            drilldown = _build_drilldown(tool_calls) if _has_data(final_msgs) else None
            confirm_envelope = _extract_confirm_envelope(final_msgs)

            if early_text:
                answer = early_text
                tool_results = [msg.get("content", "") for msg in final_msgs if msg.get("role") == "tool"]
                check_grounded(answer, tool_results, skill="governance")
                if drilldown:
                    answer += f"\n\n[View all →]({drilldown})"
                for char in answer:
                    await event_q.put({"type": "token", "text": char})
                    await asyncio.sleep(0)
                await event_q.put({"type": "done", "answer": answer, "confirm_envelope": confirm_envelope})
                return

            # Phase 2: stream synthesis (tools already resolved)
            def on_token(t: str):
                loop.call_soon_threadsafe(event_q.put_nowait, {"type": "token", "text": t})

            answer = await asyncio.to_thread(_stream_synthesis, final_msgs, system, executor, on_token)
            tool_results = [msg.get("content", "") for msg in final_msgs if msg.get("role") == "tool"]
            check_grounded(answer, tool_results, skill="governance")
            if drilldown and not _answer_is_apology(answer):
                link = f"\n\n[View all →]({drilldown})"
                for char in link:
                    await event_q.put({"type": "token", "text": char})
                    await asyncio.sleep(0)
                answer += link
            await event_q.put({"type": "done", "answer": answer, "confirm_envelope": confirm_envelope})
        except Exception as e:
            # If it's a Guard block, surface the rule_id to logs + telemetry.
            # #1286 wired Lens through the same policy engine as the HTTP
            # proxy, so any rule that fires now affects Lens.
            _err_type = type(e).__name__
            _err_detail = str(e)
            logger.error(
                "glens.stream.failed",
                error=_err_detail,
                error_type=_err_type,
                exc_info=True,
            )
            _short = _err_detail if len(_err_detail) <= 200 else _err_detail[:200] + "…"
            await event_q.put({"type": "error", "message": f"{_err_type}: {_short}"})

    async def generate():
        task = asyncio.create_task(_run_work())
        yield f"data: {json.dumps({'type': 'thinking', 'label': 'Checking your governance data...'})}\n\n"
        try:
            while True:
                evt = await asyncio.wait_for(event_q.get(), timeout=60)

                if evt.get("type") == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': evt['message']})}\n\n"
                    break

                elif evt.get("type") == "token":
                    yield f"data: {json.dumps({'type': 'token', 'text': evt['text']})}\n\n"

                elif evt.get("type") == "done":
                    answer = evt["answer"]
                    # Persist envelopes alongside the answer so session
                    # restore (#1480 PR 12) can rehydrate the right bubble
                    # kind — otherwise refresh loses ActionConfirmBubble /
                    # RunBubble and shows the LLM's prose only.
                    persisted: dict[str, Any] = {"answer": answer, "skill": "governance"}
                    if evt.get("confirm_envelope"):
                        persisted["confirm_envelope"] = evt["confirm_envelope"]
                    session_messages.append({
                        "role": "assistant",
                        "content": json.dumps(persisted),
                    })
                    capped = session_messages[-50:]
                    background_tasks.add_task(_bg_save_session, session_id_str, capped, None)

                    done_payload = {"type": "done", "session_id": session_id_str, "skill": "governance", "answer": answer}
                    if evt.get("confirm_envelope"):
                        done_payload.update(evt["confirm_envelope"])
                    yield f"data: {json.dumps(done_payload)}\n\n"
                    break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Request timed out. Please try again.'})}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(generate(), media_type="text/event-stream")
