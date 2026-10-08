"""ConductGuard remote MCP — protocol version and the tools/list catalog served by /guard/mcp."""

from __future__ import annotations



PROTOCOL_VERSION = "2024-11-05"


_TOOLS = [
    {
        "name": "guard_status",
        "description": (
            "Returns current ConductGuard policy status: workspace_id, "
            "workspace_name, your email, number of active rules, and the "
            "policy version timestamp."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "conduct_current_workspace",
        "description": (
            "Return the active workspace this MCP session is scoped to: "
            "workspace_id, workspace_name, and the caller's role in that workspace. "
            "Use when the user asks 'which workspace am I in' or when you (the model) "
            "need to confirm the workspace context before running side-effectful tools. "
            "Read-only; no side effects."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_check",
        "description": (
            "Check the intent about to be executed against team policy. "
            # #997 UX: call once per intent, not per action. Reduces transcript noise.
            "Call ONCE at the start of a task or when scope changes (reads → writes, local → network, "
            "new destination or command family). Do NOT call before every read/write in a batch. "
            "Response: 'ok' or empty means proceed silently — do NOT narrate it. "
            "'BLOCKED — <reason>' means stop and tell the user the rule. "
            "'WARNING — <reason>' means proceed but surface the warning inline. "
            "Pass tool_name as the ACTION FAMILY (e.g. 'bash', 'write_file', 'curl', 'git') "
            "and tool_input as the specific parameters."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name":  {"type": "string", "description": "The action you are about to take (e.g. bash, read_file, write_file, curl, git)"},
                "tool_input": {"type": "object", "description": "Relevant parameters — e.g. {\"command\": \"rm -rf /\"} or {\"file_path\": \"/etc/passwd\"}"},
                "conduct_run_id":   {"type": "string", "description": "Conduct run ID if called from within a workflow run — pass the value from your run context."},
                "conduct_workflow": {"type": "string", "description": "Conduct workflow slug if called from within a workflow run."},
                "prompt": {"type": "string", "description": "Optional. The prompt or action description being checked. Stored in the audit trail for traceability — useful for agentic apps passing context about why an action is being taken."},
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "guard_check_prompt",
        "description": (
            "Prompt-gate variant of guard_check. Callers at the LLM egress "
            "boundary (LiteLLM plugin, LangChain callbacks, custom proxies) "
            "hit this before their prompt reaches the model. Evaluates "
            "proxy-persona rules against the prompt text; returns the same "
            "'ok' / 'WARNING —' / 'BLOCKED —' / 'PENDING approval —' envelope "
            "guard_check does, so response parsers are shared. "
            "MCP is the transport; the proxy PEP is what enforces (Property 8)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt":   {"type": "string", "description": "The outbound prompt text about to be sent to the model."},
                "model":    {"type": "string", "description": "Model identifier, e.g. 'claude-3-5-sonnet', 'gpt-4o'."},
                "provider": {"type": "string", "description": "Upstream provider, e.g. 'anthropic', 'openai', 'bedrock'."},
                "conduct_run_id":   {"type": "string", "description": "Optional. Conduct run ID if called from within a workflow run."},
                "conduct_workflow": {"type": "string", "description": "Optional. Conduct workflow slug if called from within a workflow run."},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "guard_test",
        "description": (
            "Dry-run a single pack against a candidate tool call. "
            "Evaluates only conduct-base + the named pack — workspace custom rules, "
            "overrides, and other installed packs are excluded. Never writes to the "
            "audit chain. Returns 'WOULD-<VERDICT> — <message>' or 'OK — no rule fired'. "
            "Use for pack authoring, CI, and demos. Replaces guard_check(pack=...) which "
            "is deprecated (#1737)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pack":      {"type": "string", "description": "Compliance pack slug to test (e.g. 'conduct-eu-ai-act'). Must be installed for this workspace. 'conduct-base' is rejected — always enforced anyway."},
                "tool_name": {"type": "string", "description": "The action to test (e.g. bash, write_file, curl)."},
                "tool_input": {"type": "object", "description": "Parameters for that action, matching the shape guard_check would receive."},
            },
            "required": ["pack", "tool_name"],
        },
    },
    {
        "name": "guard_sync",
        "description": "Returns current active ruleset (no-op for remote MCP — policy is always live).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_enable",
        "description": (
            "Call this when the user asks to 'enable conductguard', 'load mcp', 'activate guard', "
            "or any similar onboarding request. Confirms ConductGuard is connected, returns the "
            "number of active policy rules, and provides the Project Instruction snippet the user "
            "should paste into their Claude.ai Project settings to make guard_check fire automatically."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_spend",
        "description": (
            "Returns LLM spend through the Conduct Guard Proxy, grouped by provider and model. "
            "Use when the user asks 'how much did I spend on LLMs today?' or 'what's our team's "
            "Claude bill this week?'. Optional 'days' argument (default 1, max 30) widens the "
            "window. Only proxy-routed calls are counted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days (default 1, max 30)"},
            },
            "required": [],
        },
    },
    {
        "name": "guard_local_risks",
        "description": (
            "Returns open local key risk findings — pre-existing real provider API keys "
            "(sk-ant-, sk-, pplx-) detected on developers' machines during conduct guard sync. "
            "Use when the user asks 'do we still have raw API keys on dev laptops?' or for "
            "CISO audit prep. Each finding includes provider, file path, masked fragment, "
            "and which developer it was on."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_activity",
        "description": (
            "ALWAYS call this at the start of every conversation, immediately after the user sends "
            "their first message. Pass a one-line summary of what the user is asking you to do. "
            "This logs session intent to the team's ConductGuard audit trail so admins can see "
            "what work is being done across the team's AI usage."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One-line summary of what the user is asking you to do in this conversation.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category: coding, debugging, review, research, writing, devops, security, other",
                },
                "conduct_run_id":   {"type": "string", "description": "Conduct run ID if called from within a workflow run."},
                "conduct_workflow": {"type": "string", "description": "Conduct workflow slug if called from within a workflow run."},
            },
            "required": ["summary"],
        },
    },
    {
        "name": "guard_recent_activity",
        "description": (
            "Read-only: show recent Guard audit events for the caller in this workspace. "
            "Complements guard_activity (which is write-only). Returns a compact list of "
            "'time  decision  rule_id  tool_call' rows so agents can see what they have done recently."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days":     {"type": "integer", "description": "Window in days (1-30). Default 1.", "default": 1},
                "limit":    {"type": "integer", "description": "Max events to return (1-100). Default 20.", "default": 20},
                "decision": {"type": "string", "description": "Optional filter: allowed / blocked / warned / audited (alias: ok → allowed)"},
                "rule_id":  {"type": "string", "description": "Optional filter to a specific rule_id"},
            },
            "required": [],
        },
    },
    {
        "name": "guard_discover",
        "description": "Show this workspace's discovery findings: installations, possible integrations, freshness, configuration and recent hook evidence. Configuration is not proof of continuous protection or Gateway traffic.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "guard_discover_register",
        "description": "Get setup guidance for a discovered finding. Does not register protection or change governance state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent ID from guard_discover results"},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "conduct_list_agents",
        "description": "List all installed agents in your Conduct workspace.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "conduct_list_projects",
        "description": "List all projects in your Conduct workspace.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "conduct_list_playbooks",
        "description": "List available Conduct playbooks (workflow templates).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "conduct_run_workflow",
        "description": "Trigger a workflow run in Conduct. Returns the run ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "The workflow UUID to run"},
                "payload":     {"type": "object", "description": "Optional trigger payload (key-value pairs)"},
            },
            "required": ["workflow_id"],
        },
    },
    {
        "name": "conduct_get_run",
        "description": "Get the status and result of a workflow run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "run_id":      {"type": "string"},
            },
            "required": ["workflow_id", "run_id"],
        },
    },
]
