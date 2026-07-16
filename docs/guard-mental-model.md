# ConductGuard — Mental Model

## Three enforcement surfaces

```
┌─────────────────────┬──────────────────────────┬───────────────────────────┐
│  Hook (Claude Code) │  MCP (claude.ai / Cursor)│  Proxy (LLM API gateway)  │
├─────────────────────┼──────────────────────────┼───────────────────────────┤
│ Fires on every tool │ Agent calls guard_check  │ Every LLM API call passes │
│ call (Bash, Read,   │ before acting. Returns   │ through api.conductai.ai  │
│ Write, etc.)        │ ALLOWED/BLOCKED/WARNING. │ before reaching Anthropic.│
├─────────────────────┼──────────────────────────┼───────────────────────────┤
│ Where policy lives  │                          │                           │
│ ~/.conduct/         │ ~/.conduct/policy.json   │ DB → guard_policy_cache   │
│   policy.json       │ (same file, same sync)   │ (server-side, per persona)│
├─────────────────────┼──────────────────────────┼───────────────────────────┤
│ Who evaluates       │                          │                           │
│ pretooluse.py       │ guardmcp.py              │ proxy.py / policy_engine  │
│ check_policy()      │ _check_policy() — same   │ compute_policy() →        │
│ local, no network   │ local JSON, no network   │ server DB query + cache   │
└─────────────────────┴──────────────────────────┴───────────────────────────┘
```

---

## Policy JSON shape (the thing that travels)

```json
{
  "version": "v3-abc123",
  "fail_mode": "fail_closed",
  "signature": "<hmac-sha256>",
  "rules": [
    {
      "rule_id":           "no-git-push-main",
      "match_tool":        "bash",          // Bash | Read | Write | * — maps via tool_groups
      "match_ai_tool":     "claude",        // claude | cursor | copilot | * — which editor
      "match_pattern":     "git push.*main",// regex on command / input
      "match_path_pattern":"secrets/",      // regex on file_path / path fields
      "match_tokens_before_gt": 100000,     // context window size check
      "action":            "block",         // block | warn | approval | audit
      "message":           "No pushes to main"
    }
  ]
}
```

Rules are ordered. **First match wins.**  
`match_tool` absent = rule applies to all tools (proxy uses this for LLM-call rules).

---

## Hook surface — `pretooluse.py`

**When**: Claude Code fires before every tool call (Bash, Read, Write, Edit, …)

```
Claude triggers tool
        ↓
pretooluse.py gets (tool_name, tool_input) via stdin
        ↓
_maybe_sync_policy()          ← throttled, every 60s max
  ├─ daemon alive? → localhost:7878/policy  (< 1ms)
  └─ no daemon    → api.conductai.ai/guard/policies/sync
        ↓
verify HMAC signature         ← reject if tampered; audit event fired
        ↓
check_policy(tool_name, tool_input)
  for rule in rules:
    match match_tool? match_ai_tool? match_pattern? match_path_pattern? tokens?
    first match → (action, rule_id, message)
        ↓
action=block  → print msg, exit(2)    ← Claude sees tool BLOCKED
action=warn   → print msg, exit(0)    ← Claude warned, continues
action=allow  → exit(0) silently
advisory_mode → everything → "audited", nothing blocked
        ↓
post_event() → local journal → drain daemon → api/guard/events  (async, no wait)
```

**Bash special handling**: `check_policy` extracts `argv[0] + subcommand + flags` only,
strips quoted argument values — so `--body "git push"` doesn't trigger a git-push rule.

**Fail-closed gate**: if `fail_mode=fail_closed` and no local policy.json exists → block all.

**Budget gate**: cached 5min from `/guard/spend/budget-check`. Hard cap = block all tools.

---

## MCP surface — `guardmcp.py`

**When**: AI agents on claude.ai / Cursor / Windsurf call `guard_check` (honor system — prompted via Project Instructions).

```
Agent is about to act
        ↓
Agent calls guard_check(tool_name, tool_input)
        ↓
_check_policy() — reads same ~/.conduct/policy.json
  same rule matching logic as hook
        ↓
Returns JSON: { "decision": "ALLOWED|BLOCKED|WARNING", "rule": "...", "message": "..." }
        ↓
Agent decides whether to proceed (Claude respects it; others may not)
        ↓
Audit event → api/guard/events (fire-and-forget)
```

**Key difference from hook**: No OS-level enforcement. Hook exits(2) and Claude Code physically
blocks. MCP returns text — the agent must choose to honor it.  
**Policy sync**: every 5 min (vs 60s for hook). Same local JSON file.

---

## Proxy surface — `proxy.py` + `policy_engine.py`

**When**: CONDUCT_LLM_PROXY env var set. Every LLM API call goes through the proxy endpoint
before reaching Anthropic/OpenAI/Perplexity.

```
Agent/brain makes LLM call → api.conductai.ai/guard/proxy/*
        ↓
Auth: cond_live_* token → resolve workspace_id
        ↓
compute_policy(db, workspace_id, persona="proxy")
  └─ _build_rules():
       1. installed skill packs (latest version) → rules[]
       2. workspace custom rules merged on top   → rule_id collision: workspace wins
       3. workspace overrides: disable or change action per rule_id
  └─ cached in guard_policy_cache (Redis invalidation on policy change)
        ↓
_evaluate_request(body, rules):
  only rules WITHOUT match_tool are evaluated here   ← proxy-applicable rules
  (match_tool rules are hook-event rules, skipped)
  match_pattern on prompt content
        ↓
decision=BLOCK → 400 with guard_block error; estimate tokens for audit
decision=WARN  → pass through, flag in audit
decision=ALLOW → forward to upstream (Anthropic/OpenAI/Perplexity)
        ↓
Audit: _audit_event() in background task → guard_events table
```

**Key difference**: Policy is assembled server-side from DB (skill packs + overrides), not a
flat JSON file. Cache invalidation via Redis pub/sub on every policy change.  
Rules without `match_tool` = LLM-content rules (prompt injection, PII, topic bans).  
Rules with `match_tool` = tool-event rules, only enforced by hook/MCP.

---

## What changes per surface — just the rules

| Dimension         | Hook                     | MCP                    | Proxy                        |
|-------------------|--------------------------|------------------------|------------------------------|
| Policy source     | `~/.conduct/policy.json` | same file              | DB → cache (server)          |
| Sync cadence      | 60s (or daemon)          | 5 min                  | on every policy save + Redis |
| Rule filter       | all rules                | all rules              | only rules without match_tool|
| Enforcement       | OS: exit(2) blocks Claude| return value (honor)   | HTTP 400 blocks call         |
| What gets matched | tool name + command text | tool name + input JSON | LLM prompt body              |
| Persona           | n/a (flat rules)         | n/a                    | `"proxy"` persona            |
| Audit             | journal → drain daemon   | direct HTTP POST       | background task              |

**Rule authoring rule of thumb**:  
- `match_tool: bash` + `match_pattern` → enforced only by hook (tool-event rule)  
- no `match_tool` + `match_pattern` → enforced only by proxy (LLM-content rule)  
- both present → hook enforces, proxy skips  
