# Policy Engine

![Policy engine mental model](images/04-policy-engine.svg)

## What it does
Evaluates security rules per workspace + persona. Assembles rules from skill packs + workspace overrides + custom rules, caches the result, and returns a decision per LLM call.

## Location
`apps/api/app/modules/guard/policy_engine.py`

## Rule sources (evaluated in order)

```
1. Skill packs (conduct-base + installed packs)
   → base rules shipped with Conduct (always on)
   → optional packs: conduct-soc2, conduct-hipaa, etc.

2. Workspace overrides (GuardRuleOverride)
   → disable a pack rule
   → change action (BLOCK → WARN)
   → add custom message

3. Workspace custom rules (WorkspaceCustomRule)
   → rules the workspace wrote themselves
   → take precedence over pack rules on ID collision
```

## Personas

| Persona | Used by | Enforcement |
|---|---|---|
| `proxy` | Guard proxy (LLM gateway) | Pre-call BLOCK only; all traffic |
| `agent` | Runtime executor | Strict; fail-closed on error |

## Rule shape

```json
{
  "id": "no-pii-in-prompt",
  "persona": "proxy",
  "match_provider": "anthropic",
  "match_model": ".*",
  "match_prompt": "(SSN|social security|credit card)",
  "action": "block",
  "message": "PII detected in prompt",
  "severity": "high"
}
```

Match fields are optional. Missing field = match all. All present fields must match (AND logic). First rule match wins.

## Policy cache

```
GuardPolicyCache:
  workspace_id, persona, payload (flattened rules JSON), version_hash, computed_at

Invalidated on:
  - Pack install / remove
  - Rule override change
  - Custom rule add / edit / delete
  - Persona config change
```

Cache miss → recompute from DB → cache result. Cache hit → return immediately (no DB query per LLM call).

## Decision flow

```
compute_policy(workspace_id, persona) → rule_list

For each rule in rule_list:
  match_provider? → exact match on "anthropic" / "openai" / "perplexity"
  match_model?    → regex on model name
  match_prompt?   → regex on request body prompt text
  match_tool?     → skip (hook rules, not LLM call rules)

  If all present fields match:
    → return {action, rule_id, message}
    STOP (first match wins)

No match → ALLOW
```

## Enforcement modes

| Mode | Effect |
|---|---|
| `block` | 403 returned, call not forwarded, audit event written |
| `warn` | Audit event written, call forwarded |
| `allow` | Audit event written, call forwarded |
| Policy error | 403, fail-closed — never forward on uncertainty |

## Connects to
- **Guard proxy**: calls `compute_policy` on every LLM request
- **Skill packs**: catalog of rule templates
- **Workspace config**: enforcement_mode, fail_mode, runtime_persona
- **Audit events**: every decision logged to guard_audit_events
