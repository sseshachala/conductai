# Cedar Adapter — User Guide

Guard accepts policies in [Cedar](https://www.cedarpolicy.com/), the AWS-blessed
open standard used by AWS Verified Permissions and (via Dogwood) Amazon Bedrock
AgentCore. You author policies in Cedar. Guard converts them to its native
pack format at import time. Runtime evaluation is unchanged.

**One-way import today**, plus one-way export for readability. See the
[spec doc](./cedar-adapter-spec.md) for the mapping table and error taxonomy.

---

## Quick start

### 1. Author your Cedar policy

Save this as `my-policy.json`:

```json
{
  "effect": "forbid",
  "principal": { "op": "is", "entity_type": "Developer" },
  "action":    { "op": "==", "entity": { "id": "Bash" } },
  "conditions": [
    {
      "kind": "when",
      "body": {
        "matches": [
          { ".": { "left": { "Var": "context" }, "attr": "prompt" } },
          { "Value": "chmod\\s+777|curl\\s+.*\\|\\s*sh" }
        ]
      }
    }
  ],
  "annotations": {
    "id": "block-dangerous-bash",
    "severity": "critical",
    "compliance": "OWASP:LLM06"
  }
}
```

### 2. Preview the conversion

```bash
conduct import-cedar my-policy.json \
  --pack-slug my-cedar-import \
  --pack-name "My Cedar Import"
```

You'll see:

```
Cedar policy import
  Rules imported: 1
  Rules rejected: 0

This was a preview. Re-run with --install to create the pack in your workspace.
```

### 3. Install for real

```bash
conduct import-cedar my-policy.json \
  --pack-slug my-cedar-import \
  --pack-name "My Cedar Import" \
  --install
```

Output:

```
Cedar policy import
  Rules imported: 1
  Rules rejected: 0

Installed: my-cedar-import@1.0.0 (1 rule(s))
```

The pack is now in your workspace's active policy. `conduct guard sync` on
any developer machine will pick it up on the next poll.

---

## Input formats

### Cedar JSON representation (Phase 1)

The [Cedar JSON policy format](https://docs.cedarpolicy.com/policies/json-format.html)
is what we accept today. AWS Verified Permissions exports this natively. It is
less ambiguous than the text grammar and easier to author programmatically.

Two shapes accepted:

- **Single policy** — one JSON object with `effect`, `principal`, `action`,
  `conditions`, `annotations`.
- **Bundle** — a JSON array of policy objects. Each is converted independently.
  Invalid policies are collected in `_rejections` rather than aborting the import.

### Cedar text grammar (Phase 1.5, not yet shipped)

Human-readable Cedar syntax (`permit(...) when { ... };`) is on the roadmap.
Until then, convert Cedar text to Cedar JSON with the AWS `cedar-policy-cli`:

```bash
cedar translate-policy --format json < my-policy.cedar > my-policy.json
```

---

## Supported constructs

See the [mapping table in cedar-adapter-spec.md](./cedar-adapter-spec.md#mapping-table)
for the complete list. Summary:

| Cedar construct | Guard equivalent |
|---|---|
| `permit(...)` | positive action (default `audit`; use `@advice("warn")` for warn) |
| `forbid(...)` | `block` action |
| `principal is <PersonaType>` | persona filter (`security`, `developer`, `agent`, `viewer`, `admin`) |
| `action == Action::"X"` | tool match (single) |
| `action in [Action::"X", Action::"Y"]` | tool match (comma list) |
| `context.prompt matches "regex"` | pattern match on request payload |
| `context.path matches "regex"` | pattern match on file path |
| `context.tokens_before > N` | numeric threshold on prior tokens |
| `context.risk_tier == "tier_3"` | agent identity tier filter (per #1037) |
| `context.ai_tool == "cursor"` | filter by AI surface |
| `context.model matches "gpt-4.*"` | filter by model name |
| `&&` in conditions | multiple matchers on the same rule |
| `@id("...")` | rule identifier |
| `@description("...")` | human description |
| `@message("...")` | operator-facing block/warn message |
| `@compliance("SOC2:CC7.3", "HIPAA:164.312")` | framework annotations |
| `@severity("high")` | severity |
| `@iso_control("A.5.15")` | ISO 27001 control ID |

## What is rejected

Every rejection returns a structured error naming the feature, the offending
snippet, and a suggested workaround.

- **Cedar temporal clauses** (`formerly within 1h`, `since`, `once`,
  aggregations from Dogwood) — Guard has no runtime temporal support yet.
- **`unless` clauses** — express negation inside a `when` with `!`.
- **`||` in conditions** — split into multiple separate `permit`/`forbid` policies.
- **`principal == User::"xyz"`** — packs are workspace-scoped, not user-scoped.
  Use `principal is <PersonaType>` for role-based rules.
- **`principal in <Group>`** — entity hierarchies are out of scope. Use
  persona typing instead.
- **`action in Action::"admin"` (action groups)** — use `action in [Action::"X",
  Action::"Y"]` (explicit list) instead.
- **Unknown operators** or **unsupported comparison targets** — see the mapping
  table for supported context attributes.

---

## Cedar text export

Every installed pack renders as Cedar text syntax for readability.

### API

```
GET /guard/registry/packs/{slug}/cedar
GET /guard/registry/packs/{slug}/cedar?version=2.2.0
```

Returns `text/plain` Cedar syntax. Latest version by default.

### UI

On any pack detail page in the Registry (`/packs/<slug>`), click **View as Cedar**.

Runtime evaluation still uses the JSON representation. The Cedar rendering is
for CISO review, RFP responses, and any reviewer who prefers Cedar syntax.

---

## API reference

### Import

```
POST /guard/registry/import-cedar
Content-Type: application/json
Authorization: Bearer <token>
X-Workspace-Id: <workspace_uuid>

{
  "format": "cedar_json",
  "policies": [ ... Cedar policies ... ],
  "pack_slug": "my-pack",
  "pack_name": "My Cedar Pack",
  "pack_version": "1.0.0",
  "pack_description": "Optional",
  "preview_only": true
}
```

Response:

```json
{
  "pack_slug": "my-pack",
  "rules_imported": 3,
  "rules_rejected": 1,
  "rejections": [
    {
      "index": 2,
      "error": {
        "error": "UnsupportedCedarFeature",
        "message": "unless clauses not supported for MVP.",
        "feature": "unless_clause",
        "hint": "Express negation inside a when using !."
      }
    }
  ],
  "pack": { "slug": "my-pack", "name": "...", "rules": [ ... ], "_rejections": [ ... ] },
  "installed": false
}
```

`preview_only: false` creates the SkillPack row and installs it in your
workspace. The `pack` field is only populated in preview mode.

---

## Examples

Runnable examples in [docs/examples/cedar/](./examples/cedar/):

1. **[01-block-dangerous-bash.json](./examples/cedar/01-block-dangerous-bash.json)** —
   Single `forbid` rule with regex pattern.
2. **[02-warn-on-secrets-in-writes.json](./examples/cedar/02-warn-on-secrets-in-writes.json)** —
   `permit` with `@advice("warn")`, multiple framework annotations.
3. **[03-tier3-requires-approval.json](./examples/cedar/03-tier3-requires-approval.json)** —
   Risk-tier filter (uses `context.risk_tier` from agent identity alignment).
4. **[04-multi-policy-bundle.json](./examples/cedar/04-multi-policy-bundle.json)** —
   Bundle of three policies. Shows audit, block, and warn actions in one import.

Try any of them:

```bash
conduct import-cedar docs/examples/cedar/04-multi-policy-bundle.json \
  --pack-slug example-bundle \
  --pack-name "Example Bundle"
```

---

## FAQ

**Can I use Cedar as the runtime evaluator?**
Not today. Guard's runtime uses the JSON pack format. Cedar is the authored
input, JSON is the evaluated output. If you need Cedar semantics at runtime
(SymCC static analysis, formal proofs), file a feature request. Until then,
authoring in Cedar plus running in JSON gives you 90% of the value with zero
runtime risk.

**Can I round-trip Cedar → JSON → Cedar and get my original file back?**
No. Round-trip is lossy for two reasons: our JSON schema drops resource fields
we don't yet interpret, and the text-format cedar exporter emits a canonical
form that may reorder annotations. The **semantics** round-trip; the **text**
does not.

**What about Dogwood temporal clauses?**
Rejected with a clear error today. Guard has no runtime temporal support yet
(spend caps and rate limits are separate subsystems, not temporal-clause based).
When Guard adds temporal matchers natively, we will add Dogwood temporal support
at the same time.

**Can I validate a Cedar policy with `cedar-policy-cli` before importing?**
Yes, and we recommend it for policies destined for production. `cedar validate`
gives you AWS's formal grammar check. Our adapter runs its own validation
during import, but Cedar's is stricter.

---

## What is on the roadmap

- **Phase 1.5** — Cedar text grammar support (accept `.cedar` files directly
  without pre-conversion to JSON).
- **Phase 5** — Cedar RFC upstream (propose a `matches()` extension function
  to the Cedar working group so the regex support is standardized rather than
  Guard-specific).
- **Phase 6** — Optional `cedar validate` + SymCC analysis at import time
  (formal check plus shadowed-policy detection using AWS's own tools).
- **Runtime Cedar** — if customer demand supports it, adopt Cedar as the
  runtime evaluator via PyO3 or WASM bindings.

See [#1035 on GitHub](https://github.com/sseshachala/conductai/issues/1035) for
the tracking epic.
