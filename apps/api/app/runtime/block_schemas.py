"""
Block schema registry — single source of truth for all block types.

Drives:
  - API: GET /meta/block-schemas (canvas reads this to render fields)
  - DSL: compile-time validation of YAML block configs
  - Runtime: pre-execution config sanity check (future)

Field types:
  text, textarea, select, toggle, number, tags, model_select, code, object
"""

from __future__ import annotations
from typing import Any

FieldDef = dict[str, Any]
BlockDef = dict[str, Any]

# ── Shared field helpers ──────────────────────────────────────────────────────

def _f(
    key: str,
    label: str,
    type: str,
    *,
    required: bool = False,
    placeholder: str = "",
    hint: str = "",
    options: list[dict] | None = None,
    default: Any = None,
    read_only: bool = False,
) -> FieldDef:
    d: FieldDef = {"key": key, "label": label, "type": type, "required": required}
    if placeholder:
        d["placeholder"] = placeholder
    if hint:
        d["hint"] = hint
    if options is not None:
        d["options"] = options
    if default is not None:
        d["default"] = default
    if read_only:
        d["readOnly"] = True
    return d


# ── Model options (kept here so frontend doesn't need to hardcode) ────────────

MODEL_OPTIONS = [
    {"value": "claude-opus-4-7",          "label": "Claude Opus 4.7"},
    {"value": "claude-sonnet-4-6",        "label": "Claude Sonnet 4.6"},
    {"value": "claude-haiku-4-5-20251001","label": "Claude Haiku 4.5"},
]

# ── Trigger subtypes ─────────────────────────────────────────────────────────

_REPO = _f("config.repo", "Repository", "text", required=True, placeholder="owner/repo",
           hint="GitHub repository that fires this trigger")
_BRANCH = _f("config.branch_filter", "Branch filter", "text",
             placeholder="main", hint="Leave blank for all branches")
_BRANCH_PATTERN = _f("config.branch_pattern", "Branch pattern", "text",
                     placeholder="release/*", hint="Glob pattern — e.g. release/*")
_WORKFLOW_NAME = _f("config.workflow_name", "Workflow name", "text",
                    placeholder="CI", hint="GitHub Actions workflow file or display name")
_VERCEL_PROJECT = _f("config.project_name", "Project name", "text",
                     placeholder="my-vercel-project", hint="Vercel project name (blank = any)")
_CRON = _f("config.cron", "Cron expression", "text", required=True,
           placeholder="0 9 * * 1-5", hint="Standard cron — e.g. 0 9 * * 1-5 for weekdays 09:00 UTC")

TRIGGER_SUBTYPES: dict[str, dict] = {
    "manual": {
        "label": "Manual run",
        "fields": [],
    },
    "github_issue_labeled": {
        "label": "GitHub — issue labeled",
        "fields": [
            _REPO,
            _f("config.label", "Label", "text", required=True,
               placeholder="autopilot-ready", hint="Issue label that fires this trigger"),
        ],
    },
    "github_issue_opened": {
        "label": "GitHub — issue opened",
        "fields": [_REPO],
    },
    "github_pr_opened": {
        "label": "GitHub — PR opened",
        "fields": [_REPO, _BRANCH],
    },
    "github_pr_updated": {
        "label": "GitHub — PR updated",
        "fields": [_REPO, _BRANCH],
    },
    "github_pr_merged": {
        "label": "GitHub — PR merged",
        "fields": [_REPO, _BRANCH],
    },
    "github_pr_review_requested": {
        "label": "GitHub — PR review requested",
        "fields": [_REPO],
    },
    "github_push": {
        "label": "GitHub — push to branch",
        "fields": [_REPO, _BRANCH_PATTERN],
    },
    "github_issue_comment": {
        "label": "GitHub — issue commented",
        "fields": [_REPO],
    },
    "github_workflow_run": {
        "label": "GitHub — CI run completed",
        "fields": [_REPO, _WORKFLOW_NAME],
    },
    "deployment.succeeded": {
        "label": "Vercel — deployment succeeded",
        "fields": [_VERCEL_PROJECT],
    },
    "deployment.ready": {
        "label": "Vercel — deployment ready",
        "fields": [_VERCEL_PROJECT],
    },
    "deployment.failed": {
        "label": "Vercel — deployment failed",
        "fields": [_VERCEL_PROJECT],
    },
    "webhook": {
        "label": "Inbound webhook",
        "fields": [],
    },
    "schedule": {
        "label": "Schedule",
        "fields": [_CRON],
    },
}

# ── Block schema registry ─────────────────────────────────────────────────────

BLOCK_SCHEMAS: dict[str, BlockDef] = {
    "trigger": {
        "label": "Trigger",
        "icon": "zap",
        "fields": [
            _f("config.event_type", "Event type", "trigger_select", required=True),
        ],
        "subtypes": TRIGGER_SUBTYPES,
    },

    "brain": {
        "label": "Brain",
        "icon": "brain",
        "fields": [
            _f("config.model", "Model", "model_select", required=True,
               options=MODEL_OPTIONS, default="claude-sonnet-4-6"),
            _f("config.mode", "Mode", "select", required=False,
               options=[
                   {"value": "single",  "label": "Single turn"},
                   {"value": "agentic", "label": "Agentic (multi-turn)"},
               ], default="single"),
            _f("config.description", "Prompt / task", "textarea",
               hint="What should this brain block do?"),
            _f("config.label", "Label", "text",
               hint="Display name shown on canvas"),
        ],
    },

    "tool": {
        "label": "Tool",
        "icon": "wrench",
        "fields": [
            _f("config.integration", "Integration", "integration_select", required=True,
               hint="Service this tool block calls (github, slack, linear, …)"),
            _f("config.action", "Action", "text", required=True,
               placeholder="fetch_issue",
               hint="Integration action to run"),
            _f("config.params", "Params", "object",
               hint="Key-value pairs passed to the action"),
            _f("config.label", "Label", "text"),
        ],
    },

    "output": {
        "label": "Output",
        "icon": "send",
        "fields": [
            _f("config.integration", "Channel", "select", required=True,
               options=[
                   {"value": "slack",  "label": "Slack"},
                   {"value": "email",  "label": "Email"},
                   {"value": "github", "label": "GitHub comment"},
                   {"value": "log",    "label": "Log only"},
               ]),
            _f("config.template", "Message template", "textarea",
               hint="Jinja2 — reference {{state_key}} or {{inputs.x}}"),
            _f("config.label", "Label", "text"),
        ],
    },

    "logic": {
        "label": "Logic",
        "icon": "git-branch",
        "fields": [
            _f("config.condition", "Condition", "text", required=True,
               placeholder="{{run_tests.passed}} == true",
               hint="Jinja2 expression — evaluates to pass/fail branch"),
            _f("config.label", "Label", "text"),
        ],
    },

    "for_each": {
        "label": "For Each",
        "icon": "repeat",
        "fields": [
            _f("config.for_each", "Iterate over", "text", required=True,
               placeholder="{{fetch_prs.items}}",
               hint="Expression resolving to a list — each element runs the connected block"),
            _f("config.item_var", "Item variable", "text",
               placeholder="item",
               default="item",
               hint="Name available as {{item}} in downstream blocks (default: item)"),
            _f("config.label", "Label", "text"),
        ],
    },

    "approval": {
        "label": "Approval",
        "icon": "check-circle",
        "fields": [
            _f("config.message", "Approval message", "textarea",
               hint="Prompt shown to the approver"),
            _f("config.approver", "Approver", "text",
               placeholder="@username or team",
               hint="Who receives the approval request"),
            _f("config.timeout_hours", "Timeout (hours)", "number",
               default=24, hint="Auto-reject after this many hours"),
            _f("config.label", "Label", "text"),
        ],
    },

    "memory": {
        "label": "Memory",
        "icon": "database",
        "fields": [
            _f("config.action", "Action", "select", required=True,
               options=[
                   {"value": "read",  "label": "Read"},
                   {"value": "write", "label": "Write"},
               ]),
            _f("config.key", "Memory key", "text", required=True,
               placeholder="my_memory_key",
               hint="Namespaced key stored per workspace + playbook"),
            _f("config.value", "Value (write only)", "text",
               hint="Jinja2 expression — required when action=write"),
            _f("config.label", "Label", "text"),
        ],
    },

    "guard": {
        "label": "Guard",
        "icon": "shield",
        "fields": [
            _f("config.enforcement_mode", "Enforcement mode", "select",
               options=[
                   {"value": "monitor", "label": "Monitor"},
                   {"value": "block",   "label": "Block"},
               ], default="monitor"),
            _f("config.label", "Label", "text"),
        ],
    },

    "mcp": {
        "label": "MCP",
        "icon": "plug",
        "fields": [
            _f("config.server", "MCP server", "text", required=True,
               placeholder="github",
               hint="MCP server name registered in your credentials"),
            _f("config.tool", "Tool", "text", required=True,
               placeholder="create_issue",
               hint="Tool name exposed by the MCP server"),
            _f("config.params", "Params", "object",
               hint="Key-value pairs forwarded to the MCP tool"),
            _f("config.label", "Label", "text"),
        ],
    },

    "sandbox": {
        "label": "Sandbox",
        "icon": "terminal",
        "fields": [
            _f("config.provider", "Provider", "select", required=True,
               options=[
                   {"value": "e2b",   "label": "E2B"},
                   {"value": "modal", "label": "Modal"},
               ]),
            _f("config.image", "Container image", "text",
               placeholder="python:3.12-slim",
               hint="Docker image to use for this sandbox (E2B sandbox template or Modal image)"),
            _f("config.command", "Command", "textarea",
               placeholder="python run.py",
               hint="Shell command to run inside the sandbox"),
            _f("config.timeout", "Timeout (seconds)", "number", default=120),
            _f("config.label", "Label", "text"),
        ],
    },
}


def get_schema(block_type: str) -> BlockDef | None:
    """Return the schema for a single block type, or None if unknown."""
    return BLOCK_SCHEMAS.get(block_type)


def get_required_keys(block_type: str, event_type: str | None = None) -> list[str]:
    """
    Return the list of required config keys for a block type.
    For trigger blocks, also includes the subtype's required fields.
    """
    schema = BLOCK_SCHEMAS.get(block_type)
    if not schema:
        return []

    keys: list[str] = [
        f["key"] for f in schema.get("fields", []) if f.get("required")
    ]

    if block_type == "trigger" and event_type:
        subtype = TRIGGER_SUBTYPES.get(event_type, {})
        keys += [f["key"] for f in subtype.get("fields", []) if f.get("required")]

    return keys


def validate_yaml_block(block_type: str, yaml_data: dict) -> list[str]:
    """
    Check a raw YAML block dict for missing required fields.

    Only validates block types whose required fields are NOT already enforced
    by the Pydantic Block model (currently: sandbox).  Returns a list of
    missing YAML-level field names (empty list = valid).

    Intentionally conservative: only checks top-level YAML keys (no deep
    params.x paths) so it never breaks playbooks that use valid alternate
    shapes (e.g. slash-format tool actions resolved by Pydantic).
    """
    # Block types already fully validated by Pydantic._validate_by_type — skip.
    PYDANTIC_VALIDATED = {"brain", "tool", "logic", "approval", "memory", "output", "mcp"}
    if block_type in PYDANTIC_VALIDATED:
        return []

    schema = BLOCK_SCHEMAS.get(block_type)
    if not schema:
        return []

    missing = []
    for field in schema.get("fields", []):
        if not field.get("required"):
            continue
        key = field["key"]
        yaml_key = key.removeprefix("config.")
        if "." in yaml_key:
            continue  # skip deeply nested paths (params.x)
        val = yaml_data.get(yaml_key) or (yaml_data.get("config") or {}).get(yaml_key)
        if not val:
            missing.append(yaml_key)

    return missing
