# ConductGuard — Hook & Tool Coverage

ConductGuard intercepts AI tool calls by registering hooks into Claude Code's hook system. This document explains how the hooks work, which events fire, and what each decision type means.

---

## Hook Architecture

```
Claude Code
    │
    ├── PreToolUse hook  ─── fires BEFORE the tool executes
    │       │
    │       ├── Exit 0  → tool runs normally
    │       ├── Exit 2  → tool is BLOCKED; message shown to user
    │       └── Exit other → hook error (tool blocked, error logged)
    │
    └── PostToolUse hook ─── fires AFTER the tool executes
            │
            └── Records tokens, cost, session summary to API
```

Both hooks call the same script: `~/.conductguard/hook.py`

The hook reads `event_type` from stdin JSON to determine which path to execute.

---

## PreToolUse — What It Checks

Every tool call passes through two checks in order:

### 1. Spend budget check

Calls `/guard/spend/budget-check` with:
- `workspace_id`
- `clerk_user_id` (for per-developer cap enforcement)
- `monthly_cost_usd` (current month spend)

If `hard_blocked: true`, the hook exits 2 with a user-friendly message:

```
Your team's monthly AI budget of $50.00 has been reached.
New tool calls are paused until the limit is raised.
Contact your security team.
```

### 2. Policy rule check

Evaluates the tool call against the cached policy set (`~/.conductguard/config.json`). Rules are matched in order:

| Field | Match logic |
|---|---|
| `match_tool` | Exact match on tool name (e.g. `bash`) |
| `match_pattern` | Substring or regex match on the tool's input |
| `match_path_pattern` | Glob match on any file path in the input |

First matching rule wins. Actions:

| Action | Exit code | Effect |
|---|---|---|
| `block` | 2 | Tool is blocked; message shown to user |
| `warn` | 0 | Tool runs; warning logged to audit |
| `audit` | 0 | Tool runs; event logged silently |
| `approve` | 0 | Tool runs; explicitly approved |

---

## PostToolUse — What It Records

After a tool call completes, the hook sends an audit event to `/guard/events` with:

- `tool_call` — tool name
- `input_summary` — truncated tool input
- `decision` — allow / block / warn
- `rule_id`, `rule_message` — if a rule matched
- `tokens_before`, `tokens_after`, `tokens_saved` — token counts
- `cost_usd_before`, `cost_usd_after` — cost in USD
- `tool_use_id` — Claude's internal tool use ID
- `hook_session_id` — the Claude Code session ID
- `duration_ms` — hook execution time

---

## AI Tools Covered

| Tool | Hook mechanism | Notes |
|---|---|---|
| **Claude Code** | Native PreToolUse/PostToolUse | Full coverage, all tool calls |
| **Codex CLI** | Native PreToolUse/PostToolUse | Same hook format |
| **Cursor** | `conductguard-mcp` MCP server | See [conductguard-mcp](conductguard_mcp.md) |
| **Gemini CLI** | `conductguard-mcp` MCP server | Experimental |

---

## Tool Call Types Intercepted

All tool calls that Claude Code makes are intercepted — not just file writes or shell commands. This includes:

| Tool name | What it does |
|---|---|
| `bash` | Shell command execution |
| `edit` / `write` | File writes |
| `read` | File reads |
| `glob` / `grep` | File searches |
| `web_search` / `web_fetch` | Web access |
| `computer` | Computer use (screenshots, clicks) |
| Custom MCP tools | Any tool registered via MCP |

---

## Policy Rule Matching — Examples

**Block `rm -rf` commands:**
```
match_tool: bash
match_pattern: rm -rf
action: block
message: Destructive delete blocked by team policy. Use git rm or move to trash.
```

**Block writes to `.env` files:**
```
match_tool: write
match_path_pattern: **/.env*
action: block
message: Writing to .env files is blocked. Store secrets in the credential vault.
```

**Warn on force push:**
```
match_tool: bash
match_pattern: git push.*--force
action: warn
message: Force push detected. Make sure you've coordinated with your team.
```

---

## Hook Sync Cadence

Policies are pulled from the server and written to `~/.conductguard/config.json` every 60 seconds by the background sync process. The hook reads from this local cache — no network call is made during the per-tool-call PreToolUse check (except for the spend budget check, which is a fast HTTP call).
