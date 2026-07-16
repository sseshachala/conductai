# ACD-0001: Three-Surface Policy Interception

**Status:** Accepted  
**Date:** 2026-07-01  
**Patent claim:** Dual-surface interception (hook + proxy)

---

## Decision

Enforce Guard policies at three distinct surfaces: the OS-level hook, the MCP tool protocol, and the LLM API proxy. Each surface is independent — a policy violation is caught at whichever surface sees the action first.

```
Agent action
     │
     ├─► Hook (PreToolUse) ──────► OS-level block before tool executes
     │   Fires on: Bash, Read, Write, Edit, any Claude Code tool
     │   Enforcement: exit(2) — physically stops execution
     │
     ├─► MCP guard_check ─────────► Return value (agent must honor)
     │   Fires on: conduct_run_workflow, any MCP tool call
     │   Enforcement: JSON {"decision": "BLOCKED"} in response
     │
     └─► LLM Proxy ───────────────► HTTP 400 before token is consumed
         Fires on: every API call to Anthropic/OpenAI/Gemini
         Enforcement: request never reaches provider
```

---

## Context

A single enforcement surface creates bypass paths. An API proxy catches LLM calls but misses file writes. A hook catches local tool calls but misses agents running in cloud sandboxes that call the API directly. An MCP layer catches tool dispatch but only if the agent calls it.

Three surfaces with overlapping coverage means an action must bypass all three to escape enforcement. In practice, most actions are caught at the first surface they touch.

---

## Alternatives Rejected

**Proxy-only enforcement**: Catches LLM calls, misses filesystem, Bash, Git. An agent running `rm -rf` never touches the LLM proxy.

**Hook-only enforcement**: Catches local Claude Code tool calls, misses agents on remote sandboxes (E2B, Modal) that call provider APIs directly without going through the hook process.

**MCP-only enforcement**: Honor-system. The agent must call `guard_check` voluntarily. No OS-level mechanism prevents bypassing it.

**Single unified surface**: Would require routing all three action types through one choke point — adds latency, creates a single point of failure, and requires all three action categories to share one protocol.

---

## Consequences

- Policy must be expressed in terms that all three surfaces can evaluate — no surface-specific rule language
- Hook rules use `match_tool` to scope to tool types; proxy rules omit `match_tool` (LLM-content rules); MCP rules use `match_tool: workflow`
- Audit events from all three surfaces land in the same `guard_audit_events` table under a shared schema
- A rule with `match_tool: bash` is enforced only by the hook — the proxy skips it deliberately
- Adding a fourth surface (IDE extension, CI runner) requires only plugging into `check_policy()` and posting to `/guard/events`
