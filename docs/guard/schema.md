# Agentic Tool-Call Policy Schema v1

*Formerly "Guard Rule Schema" — same shape, sharper name.* This is the schema for a distinct policy category: rules that govern what an AI agent is allowed to do when it invokes a tool (file edit, shell, HTTP, MCP tool call, workflow action).

**Why the category matters:** OPA/Rego is generic policy. Cedar is authorization. Kyverno is K8s admission. Sentinel is Terraform. **Agentic Tool-Call Policy is its own shape** — the actor is an autonomous AI agent, the object is a tool invocation, decisions land in milliseconds pre-execution, and portability across enforcement surfaces (proxy, hooks, MCP, runtime) is table-stakes. This schema is what that shape looks like.

Guard rules speak **two dialects**: JSON (runtime evaluation) and Cedar (portability / interchange). Both are semantically equivalent — you can round-trip your policies in either direction with zero information loss.

- **Machine-readable JSON Schema:** [`schemas/conduct-guard-rule.v1.json`](../../schemas/conduct-guard-rule.v1.json)
- **Import Cedar:** `POST /guard/registry/import-cedar` (Cedar JSON → Guard pack)
- **Export Cedar:** `GET /guard/registry/packs/{slug}/cedar` (Guard pack → Cedar text) — or click **⤓ Cedar** on any pack tile at [/packs](/packs)

## Why two dialects

Different audiences read policies differently:

- **Engineers + runtime** want JSON — grep-friendly, machine-generatable, embeds cleanly in pack files
- **Auditors + security teams** want Cedar — human-readable, standard syntax, portable to AWS Verified Permissions and any Cedar-consuming ecosystem
- **You** want no lock-in — bring your existing Cedar policies in; take your Guard packs out whenever you leave

## Anatomy of a rule

Every Guard rule matches on **what** (tool, path, prompt pattern) and decides **how** (block / warn / allow / audit / inject / approval). Metadata (severity, frameworks, iso_control) rides along for audit surfaces.

```json
{
  "id": "pci_pan_guard",
  "description": "Block card number patterns (PCI DSS Req 3)",
  "match_tool": "edit,write,bash",
  "match_pattern": "\\b4[0-9]{12}(?:[0-9]{3})?\\b|\\b5[1-5][0-9]{14}\\b",
  "action": "block",
  "message": "Card number detected — never log or store PANs in plaintext.",
  "recommendation": "Tokenise PAN before storage. Use a PCI-compliant tokenisation service.",
  "severity": "critical",
  "persona_affinity": ["agent"],
  "frameworks": ["PCI_DSS:3.4", "SOC2:CC6.1", "GDPR:Art32"],
  "iso_control": "A.8.11",
  "enforcement": {
    "version": 1,
    "proxy": "not_supported",
    "hook": "conditional",
    "mcp": "conditional",
    "runtime": "not_supported",
    "guarantee": "Blocks matching actions on supported surfaces.",
    "requires": [
      "A supported pre-tool hook is installed and invoked before the action",
      "The agent calls MCP guard_check before acting"
    ],
    "known_limitations": [
      "MCP cannot enforce actions the agent doesn't submit to guard_check"
    ]
  }
}
```

The **same rule** rendered as Cedar:

```cedar
@id("pci_pan_guard")
@description("Block card number patterns (PCI DSS Req 3)")
@message("Card number detected — never log or store PANs in plaintext.")
@recommendation("Tokenise PAN before storage. Use a PCI-compliant tokenisation service.")
@severity("critical")
@iso_control("A.8.11")
@compliance("PCI_DSS:3.4", "SOC2:CC6.1", "GDPR:Art32")
forbid (
    principal is Agent,
    action in [Action::"edit", Action::"write", Action::"bash"],
    resource
)
when {
    context.prompt matches "\\b4[0-9]{12}(?:[0-9]{3})?\\b|\\b5[1-5][0-9]{14}\\b"
};
```

## Fields

### Rule (required)

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable identifier. Unique within pack. Referenced by overrides. |
| `action` | enum | `block` \| `warn` \| `allow` \| `audit` \| `inject` \| `approval` |

### Rule (optional)

| Field | Type | Notes |
|---|---|---|
| `description` | string | Human summary — Cedar `@description`. |
| `match_tool` | string | Comma-separated tool names (`edit,write,bash`). Empty or `*` = all. |
| `match_pattern` | regex string | Matched against tool_input.prompt / body. |
| `match_path_pattern` | regex string | Matched against tool_input.path (file ops). |
| `message` | string | Shown to user on match. Cedar `@message`. |
| `recommendation` | string | Remediation guidance. Cedar `@recommendation`. |
| `severity` | enum | `low` \| `medium` \| `high` \| `critical`. Cedar `@severity`. |
| `persona_affinity` | string[] | `agent` and/or `proxy`. Defaults to both if omitted. |
| `frameworks` | string[] | Compliance tags (`PCI_DSS:3.4`, `SOC2:CC6.1`, `ISO_42001:8.24`, `MITRE_ATLAS:AML.T0051`, `OWASP_AGENTIC:A01`). Cedar `@compliance`. |
| `iso_control` | string | ISO 27001/42001 control ID. Cedar `@iso_control`. |
| `enforcement` | object | Surface-by-surface enforcement capability (see below). |

### Enforcement metadata

Per surface, the rule declares whether it can enforce (`hard`), advise (`conditional`), or is inapplicable (`not_supported`).

| Surface | What it means |
|---|---|
| `proxy` | Guard LLM proxy — enforced on egress before hitting Anthropic/OpenAI/etc. |
| `hook` | Pre-tool hooks in Claude Code / Cursor / Codex — enforced before local tool call fires. |
| `mcp` | MCP `guard_check` — enforced when agent voluntarily calls it. |
| `runtime` | Conduct workflow runtime — enforced during YAML playbook execution. |

### Pack (bundles rules)

| Field | Type | Notes |
|---|---|---|
| `slug` | string | URL-safe identifier (lowercase, hyphens). Required. |
| `name` | string | Display name. Required. |
| `version` | semver | `1.1.0` etc. Required. |
| `tier` | enum | `free` \| `paid` \| `enterprise`. |
| `description` | string | Pack summary. |
| `ui` | object | Optional `{icon, subtitle, tags}` for the /packs tile. |
| `rules` | rule[] | At least one. Required. |

## Framework tag conventions

The `frameworks` array is free-form but **strongly encouraged** to follow these prefixes for compliance surface parity:

| Prefix | Example | Standard |
|---|---|---|
| `PCI_DSS:` | `PCI_DSS:3.4` | PCI Data Security Standard requirement |
| `SOC2:` | `SOC2:CC6.1` | SOC 2 Trust Services Criteria |
| `ISO_27001:` | `ISO_27001:A.8.24` | ISO 27001 Annex A control |
| `ISO_42001:` | `ISO_42001:8.24` | ISO 42001 (AI management) control |
| `GDPR:` | `GDPR:Art32` | GDPR article |
| `HIPAA:` | `HIPAA:164.308` | HIPAA Security Rule section |
| `NIST_AI_RMF:` | `NIST_AI_RMF:MG-2.6` | NIST AI Risk Management Framework |
| `MITRE_ATLAS:` | `MITRE_ATLAS:AML.T0051` | MITRE ATLAS adversarial ML technique |
| `OWASP_AGENTIC:` | `OWASP_AGENTIC:A01` | OWASP Agentic Top 10 |
| `SR_11_7:` | `SR_11_7:V.A.1` | Federal Reserve model risk |

## Cedar interchange

The Cedar rendering preserves every rule field via annotations (`@id`, `@description`, `@message`, `@severity`, `@iso_control`, `@compliance`, `@recommendation`). Reverse import (`POST /guard/registry/import-cedar`) parses `forbid`/`permit` blocks + annotations back into Guard rule JSON.

Round-trip is lossless for schema v1. Bring your existing Cedar policies from AWS Verified Permissions, Dogwood, or any IAM stack that speaks Cedar JSON.

## v1.1 additions (extensible match + annotations)

Two optional additions keep v1 backward compat while giving room to grow.

### Extensible `match` map

Instead of hardcoding `match_tool`, `match_pattern`, `match_path_pattern`, put every dimension under a `match` object. Runtime reads whichever keys it understands and **matches when every populated dimension matches** the invocation.

```json
{
  "id": "block_prod_writes",
  "action": "block",
  "match": {
    "tool":         "write,edit,bash",
    "pattern":      "PROD_SECRET",
    "path_pattern": "^prod/config\\.yaml$",
    "http_method":  "POST",
    "mcp_tool":     "guard_check"
  }
}
```

v1 top-level `match_tool` / `match_pattern` / `match_path_pattern` stay valid — they become sugar that folds into `match.tool` etc. at eval time. Custom dimensions (e.g. `mcp_server`, `webhook_source`) are also allowed; unknown keys are ignored by surfaces that don't understand them.

### Namespaced `annotations` map

Free-form metadata namespaced by key. Runtime ignores unknown namespaces; exporters pass them through.

```json
{
  "id": "block_prod_writes",
  "action": "block",
  "annotations": {
    "cedar":       { "principal_type": "Agent" },
    "opa":         { "package": "conduct.pci" },
    "kyverno":     { "match_kinds": ["Pod"] },
    "custom.acme": "internal-tracker-#1234"
  }
}
```

Use this to carry framework-specific metadata around your rules without polluting the core shape. Cedar exporter emits them as `@annotation`; OPA exporter (future) as package doc comments; import from other systems keeps their metadata intact.

## How this schema maps to other policy languages

Agentic Tool-Call Policy has its own shape, but the vocabulary overlaps with adjacent standards. Here's how our fields correspond so teams already using other engines can see the alignment.

| Concept | Ours | OPA/Rego | Kyverno | Sentinel | Cedar | XACML | MITRE ATLAS |
|---|---|---|---|---|---|---|---|
| Rule identifier | `id` | package + rule name | policy metadata name | policy name | policy id | PolicyId | technique ID (e.g. `AML.T0051`) |
| Decision | `action` (block/warn/allow/audit/inject/approval) | `deny` / `allow` sets | `validate.deny` / `mutate` | `main = rule { ... }` bool | `forbid` / `permit` | `Effect="Deny"/"Permit"` | control category |
| Subject/actor | `persona_affinity` + `match.mcp_tool` | `input.subject` | resource kind | `input.subject` | `principal is <Type>` | `Subject` | technique target |
| Object/resource | `match.tool` + `match.path_pattern` | `input.resource` | `match.resources.kinds` | `input.resource` | `resource` | `Resource` | attack surface |
| Match condition | `match.pattern` (regex) | `contains` / `startswith` in Rego expr | `match.resources.selector` | `matches` function | `when { ... }` clause | `Condition` element | detection signature |
| Severity | `severity` (low/medium/high/critical) | annotation | policy.severity | metadata | `@severity` annotation | `Obligation` | severity rating |
| Compliance mapping | `frameworks[]` (`PCI_DSS:3.4` etc.) | annotation | policy.categories | metadata | `@compliance` annotation | `Obligation` reference | technique IDs |
| Metadata roundtrip | `annotations.<ns>` | package doc | annotations | scope description | `@<name>` annotation | attributes | technique references |
| Enforcement surface | `enforcement.{proxy,hook,mcp,runtime}` | evaluator context | policy webhook | Terraform run stage | authorization boundary | PDP context | detection layer |

**What this table is saying:** the underlying concepts are the same across the industry. What differs is the *shape* of the primary object being governed: OPA governs arbitrary JSON input; Kyverno governs K8s resources; Sentinel governs Terraform plans; Cedar governs authorization requests. **Ours governs agentic tool invocations** — an object shape none of the above are optimized for.

**What we don't try to do:** we're not building a general-purpose policy engine. Runtime enforcement stays Conduct-specific. What ships is a portable *representation* — via Cedar for interchange, JSON Schema for tooling, and annotations for round-tripping foreign metadata.

## Versioning

Schema version = `v1` (with v1.1 additions above). Backward-incompatible changes will publish `v2` at a new `$id` and both stay available. Rule packs may declare a `$schema` reference to the specific version they target; runtime defaults to latest.

## Extending

Adding a new field to v1:
1. Add to `schemas/conduct-guard-rule.v1.json` (mark it optional so old rules validate)
2. Update the JSON→Cedar exporter to emit a matching `@` annotation
3. Update the Cedar→JSON importer to parse the annotation back
4. Update this doc's field table

Removing or renaming = v2. Don't break v1 users.
