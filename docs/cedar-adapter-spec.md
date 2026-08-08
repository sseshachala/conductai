# Cedar Adapter Spec (v0)

Status: Phase 0 draft — 2026-08-08
Owner: TBD
Branch: `epic/1035-cedar`

## What this is

A one-way import path from Cedar policies into Guard's native JSON pack format. Optional companion export path (Phase 3) renders our packs as Cedar for readability.

Not a Cedar runtime. Runtime evaluation stays in `policy_engine.py` on our JSON format.

## Two input formats we accept

### 1. Cedar JSON representation (Phase 1 target)

Cedar publishes a JSON schema for policies. Easier to parse (just `json.loads`), less ambiguous, and the format AWS Verified Permissions exports natively.

```json
{
  "effect": "permit",
  "principal": { "op": "==", "entity": { "type": "User", "id": "alice" } },
  "action": { "op": "==", "entity": { "type": "Action", "id": "view" } },
  "resource": { "op": "in", "entity": { "type": "Album", "id": "vacation" } },
  "conditions": [
    {
      "kind": "when",
      "body": {
        "===": [{ ".": { "left": { "Var": "context" }, "attr": "authenticated" } }, { "Value": true }]
      }
    }
  ],
  "annotations": {
    "id": "read-authenticated-view",
    "compliance": "SOC2:CC7.3"
  }
}
```

### 2. Cedar text grammar (Phase 1.5 stretch)

The human-readable Cedar syntax. Requires a real parser. Not blocking for Phase 1.

```cedar
@id("read-authenticated-view")
@compliance("SOC2:CC7.3")
permit (
    principal == User::"alice",
    action == Action::"view",
    resource in Album::"vacation"
) when {
    context.authenticated == true
};
```

## Output: our JSON pack rule shape

Same shape as existing rules in `conduct-owasp.json`, `conduct-soc2.json`, etc.

```json
{
  "id": "read-authenticated-view",
  "description": "...",
  "match_tool": "*",
  "match_pattern": "...",
  "action": "audit",
  "message": "...",
  "persona_affinity": ["agent"],
  "frameworks": ["SOC2:CC7.3"],
  "severity": "medium",
  "enforcement": { ... }
}
```

## Mapping table

Coverage decisions per Cedar construct.

### Effects

| Cedar | Our JSON |
|---|---|
| `permit(...)` with no `@advice` annotation | `"action": "audit"` |
| `permit(...) @advice("warn")` | `"action": "warn"` |
| `permit(...) @advice("approval")` | `"action": "approval"` |
| `forbid(...)` | `"action": "block"` |
| `forbid(...) @advice("inject")` | `"action": "inject"` |

### Scope elements

**Principal:**

| Cedar | Our JSON |
|---|---|
| `principal` (unrestricted) | no persona filter |
| `principal is SecurityAdmin` | `"persona_affinity": ["security"]` |
| `principal is Developer` | `"persona_affinity": ["developer"]` |
| `principal is Agent` | `"persona_affinity": ["agent"]` |
| `principal is Viewer` | `"persona_affinity": ["viewer"]` |
| `principal == User::"xyz"` | REJECTED — user-specific rules not in scope for MVP |

**Action:**

| Cedar | Our JSON |
|---|---|
| `action` (unrestricted) | `"match_tool": "*"` |
| `action == Action::"Bash"` | `"match_tool": "Bash"` |
| `action in [Action::"Bash", Action::"Write"]` | `"match_tool": "Bash,Write"` |
| `action in Action::"admin"` (action group) | REJECTED — action groups not in scope for MVP |

**Resource:** ignored for MVP. Our matchers do not have resource semantics today. Recorded as annotation for future use.

### When / unless conditions

| Cedar | Our JSON |
|---|---|
| `context.prompt matches "regex"` | `"match_pattern": "regex"` |
| `context.path matches "regex"` | `"match_path_pattern": "regex"` |
| `context.tokens_before > 5000` | `"match_tokens_before_gt": 5000` |
| `context.risk_tier == "tier_3"` | `"match_agent_risk_tier": "tier_3"` |
| `context.ai_tool == "cursor"` | `"match_ai_tool": "cursor"` |
| `context.model matches "gpt-.*"` | `"match_model": "gpt-.*"` |
| `context.mcp_server == "postgres"` | `"match_mcp_server": "postgres"` |
| Compound with `&&` | multiple matchers on same rule (all must match) |
| Compound with `\|\|` | REJECTED for MVP — requires rule splitting |
| `unless { ... }` | REJECTED for MVP — negation not directly supported |

### Annotations

| Cedar | Our JSON |
|---|---|
| `@id("rule-slug")` | `"id": "rule-slug"` |
| `@description("...")` | `"description": "..."` |
| `@compliance("SOC2:CC7.3")` | `"frameworks": ["SOC2:CC7.3"]` |
| `@compliance("SOC2:CC7.3", "HIPAA:164.312")` | `"frameworks": [...]` |
| `@severity("high")` | `"severity": "high"` |
| `@iso_control("A.5.15")` | `"iso_control": "A.5.15"` |
| `@advice(...)` | maps to action (see Effects table) |
| `@message("...")` | `"message": "..."` |
| `@recommendation("...")` | `"recommendation": "..."` |

Unknown annotations are preserved in a `_cedar_annotations` field for round-trip fidelity.

### Not supported (adapter rejects with clear error)

- **Dogwood temporal clauses** (`formerly within 1h`, `since`, `once`, aggregations) — require Guard's native temporal support, not yet shipped
- **Cedar extension functions** (`ip()`, `decimal()`, custom `matches()`) — case by case
- **Entity hierarchies** (`principal in Group::"..."` with parent chains) — our persona affinity is flat
- **User-specific rules** (`principal == User::"xyz"`) — packs are workspace-scoped, not user-scoped
- **`unless` clauses** — negation must be expressed as `!` inside a `when`
- **`\|\|` in conditions** — split into multiple rules
- **`if-then-else`** — not applicable to our matcher model
- **Templates + template linking** — not applicable
- **Set operations beyond `contains`** — case by case

Each rejection returns a specific error with the offending Cedar snippet and the reason.

## Error taxonomy

```python
class CedarAdapterError(Exception): pass
class UnsupportedCedarFeature(CedarAdapterError): pass
class InvalidCedarSyntax(CedarAdapterError): pass
class CedarMappingAmbiguity(CedarAdapterError): pass
```

Every error includes:
- `feature`: what Cedar construct caused it
- `location`: line/column if parseable
- `snippet`: the offending Cedar text
- `hint`: workaround suggestion

## API surface

### Python module

```python
# apps/api/app/modules/guard/cedar_adapter/__init__.py

def cedar_json_to_pack(cedar_json: dict, pack_metadata: dict) -> dict:
    """Convert a single Cedar JSON policy to a Guard pack rule."""

def cedar_json_bundle_to_pack(policies: list[dict], pack_metadata: dict) -> dict:
    """Convert a list of Cedar JSON policies to a full Guard pack."""

def cedar_text_to_json(cedar_text: str) -> list[dict]:
    """Parse Cedar text syntax and return Cedar JSON policies (Phase 1.5)."""

def pack_to_cedar_text(pack: dict) -> str:
    """Render a Guard pack in Cedar text syntax (Phase 3)."""
```

### HTTP endpoint

```
POST /guard/registry/import-cedar
  Body: { "format": "cedar_json" | "cedar_text", "content": "...", "pack_name": "...", "pack_slug": "..." }
  Response: { "pack_slug": "...", "rules_imported": N, "rules_rejected": M, "rejections": [ ... ] }
```

### CLI command

```
conduct import-cedar my-policy.cedar --pack-name "My Cedar Policy" --pack-slug my-cedar
```

## Registry UI

New "Import" button on `/registry` page. Two options:
1. Paste Cedar text or Cedar JSON
2. Upload a `.cedar` or `.json` file

Import flow:
1. Parse / validate (adapter runs)
2. Preview: show what will import, what will be rejected, with per-rule diagnostics
3. Confirm: pack is created with the imported rules
4. Install: normal pack installation flow

## Optional validation with cedar CLI

If `cedar-policy-cli` is installed on the server, we can shell out at import time to run:
- `cedar validate --schema schema.cedar --policy-file input.cedar` — schema validation
- `cedar-policy-symcc analyze --policies input.cedar` — symbolic analysis (find shadowed / conflicting rules)

Not required for MVP. Nice-to-have that adds Cedar's formal guarantees at the boundary without adding runtime cost.

## Testing strategy

**Golden test corpus:**
- Cedar's own example repository (`cedar-examples`)
- AWS Verified Permissions sample policies
- Dogwood examples
- Hand-crafted edge cases (nested when, all annotation types, various operators)

**Assertions per test:**
- Adapter produces expected pack rule
- Rejections have correct error type and hint
- Round-trip (JSON → adapter → pack → export → Cedar text) preserves semantic behavior on a test evaluation

## Out of scope for this arc

- Cedar as a runtime evaluator
- Dogwood temporal support
- SymCC integration (deferred pending customer demand)
- Multi-policy set-level analysis (deferred)
- Template linking (deferred)

## What ships this session

Phase 0 = this document plus a stub Python module. Phase 1 = the actual Cedar JSON mapper with tests. Phases 2-4 in follow-up sessions.
