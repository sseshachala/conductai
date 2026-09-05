# Conduct Guard Rule Schema v1

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

## Versioning

Schema version = `v1`. Backward-incompatible changes will publish `v2` at a new `$id` and both stay available. Rule packs may declare a `$schema` reference to the specific version they target; runtime defaults to latest.

## Extending

Adding a new field to v1:
1. Add to `schemas/conduct-guard-rule.v1.json` (mark it optional so old rules validate)
2. Update the JSON→Cedar exporter to emit a matching `@` annotation
3. Update the Cedar→JSON importer to parse the annotation back
4. Update this doc's field table

Removing or renaming = v2. Don't break v1 users.
