# Conduct Documentation

Conduct is a YAML playbook platform that turns AI agents into reusable team automations — with a FastAPI backend, Next.js canvas UI, Redis worker, cross-provider LLM proxy (Guard), and 22+ pre-built playbooks covering GitHub, Slack, CI/CD, and incident response.

Docs are organized **by goal, not by file shape**. Pick your path below.

---

## By persona

- **Solo dev evaluating** — `pip install conduct-cli`, run one playbook end-to-end.
  → [Start](start.md) → [Examples](examples.md) → [Automate](automate.md)

- **Team lead onboarding a team** — bring Guard to the whole team, wire in CI, install a pack of playbooks.
  → [ConductGuard Quickstart](modules/conductguard/QUICKSTART.md) → [Team onboarding](modules/conductguard/team_onboarding.md) → [Automate](automate.md) → [Examples](examples.md)

- **Security buyer doing due diligence** — trust boundaries, hash-chained audit, compliance coverage, fail modes.
  → [Threat model](threat-model.md) → [Audit log verification](audit-log-verification.md) → [Guard rule packs](reference/guard-rule-packs.md) → [Enforcement coverage](modules/conductguard/enforcement_coverage.generated.md) → [ADR-0001 (trust boundaries)](adr/ADR-0001-guard-enforcement-surfaces-and-trust-boundaries.md) → [ADR-0003 (fail-open vs fail-closed)](adr/ADR-0003-fail-open-versus-fail-closed-semantics.md)

---

## Start by goal

- **I'm brand new — get me running** → [Start](start.md)
- **I want to run Conduct locally on the codebase** → [Operate → Developer setup](modules/conductguard/developer_setup.md)
- **I want to write a playbook** → [Concepts → Playbooks](mental-models/08-playbooks.md) + [Playbook DSL ADR](adr/ADR-0004-playbook-dsl-versus-external-orchestration-frameworks.md)
- **I want to see 37 working examples** → [Examples](examples.md)
- **I want to govern AI tool usage on my team** → [Operate → ConductGuard Quickstart](modules/conductguard/QUICKSTART.md)
- **I want to wire Conduct into CI, MCP, or my own tools** → [Automate](automate.md)
- **I want to understand the architecture** → [Orientation → ARCHITECTURE](ARCHITECTURE.md)
- **I want to add a policy rule / compliance pack** → [Policy → Enforcement coverage](modules/conductguard/enforcement_coverage.generated.md)
- **I want to integrate a third-party tool** → [Integrations](#integrations)

---

## Start

New to Conduct. Get from zero to a working install.

- [Start](start.md) — install `conduct-cli`, log in, install 30+ playbooks, first agent run, first `playbook.yaml`
- [Developer setup](modules/conductguard/developer_setup.md) — local dev environment, dependencies, first run against the Conduct codebase
- [ConductGuard Quickstart](modules/conductguard/QUICKSTART.md) — install Guard, sync policy, first governed AI tool call

---

## Reference

Stable contracts and vocabulary. Read these when you need the *exact* answer.

- [Vocabulary](vocabulary.md) — canonical terms used across the codebase
- [API versioning](api-versioning.md) — how API versions are declared, deprecated, and served
- [Policy decision contract](policy-decision-contract.md) — allow / warn / block / audit semantics
- [Guard token model](specs/GUARD_TOKEN_MODEL.md) — token types (`cond_agt_*`, `cond_run_*`, `cond_cred_*`), lifetimes, scopes
- [Guard capability inventory](modules/conductguard/CAPABILITY_INVENTORY.md) — what Guard does, mapped to controls
- [Guard rule packs](reference/guard-rule-packs.md) — every rule in every shipping pack (183 rules across 15 packs)
- [Playbook block reference](reference/blocks.md) — every block type, required fields, examples

---

## Concepts

Mental models. How the pieces fit together. Read these once, refer back rarely.

- [1. Execution engine](mental-models/01-execution-engine.md)
- [2. Brain block](mental-models/02-brain-block.md)
- [3. Guard proxy](mental-models/03-guard-proxy.md)
- [4. Policy engine](mental-models/04-policy-engine.md)
- [5. Memory](mental-models/05-memory.md)
- [6. DSL compiler](mental-models/06-dsl-compiler.md)
- [7. Agent identity](mental-models/07-agent-identity.md)
- [8. Playbooks](mental-models/08-playbooks.md)
- [9. Pricing](mental-models/09-pricing.md)
- [10. Auth & crypto](mental-models/10-auth-crypto.md)
- [11. Database schema](mental-models/11-database-schema.md)
- [12. Data flow](mental-models/12-data-flow.md)

---

## Orientation

Where things sit. Trust boundaries. Failure modes. Read before making architectural changes.

- [ARCHITECTURE](ARCHITECTURE.md) — top-down system view
- [Guard mental model](guard-mental-model.md) — how Guard thinks about tool calls
- [Guard false-positive strategy](guard-fp-strategy.md) — how we tune rule precision
- [Threat model](threat-model.md) — attack surface, mitigations
- [Module security threat model](modules/security/threat-model.md) — per-module threat analysis

---

## Operate

Running Conduct. Day-two ops: onboard a team, respond to an incident, tune a rule.

- [ConductGuard overview](modules/conductguard/overview.md) — what Guard is, who it's for
- [ConductGuard README](modules/conductguard/README.md) — module entry point
- [Runbook](modules/conductguard/RUNBOOK.md) — incident response, common ops
- [Team onboarding](modules/conductguard/team_onboarding.md) — bring a team onto Guard
- [Audit log verification](audit-log-verification.md) — verify the hash-chained audit trail
- [Guard module spec](modules/guard.md) — v0.3 fleet-management model

---

## Automate

Wire Conduct into your other tools. CI, MCP, agents.

- [Automate](automate.md) — CLI, MCP, CI, hooks, HTTP API, webhooks
- [ConductGuard MCP](modules/conductguard/conductguard_mcp.md) — MCP server spec (Claude Code, Cursor, Codex)

---

## Policy

Ship policy. Compliance mappings, coverage evidence, permission model, spend controls.

- [AI governance playbooks](modules/conductguard/ai_governance_playbooks.md) — how Guard implements common governance patterns
- [Enforcement coverage](modules/conductguard/enforcement_coverage.generated.md) — generated evidence: which surface enforces which rule
- [Hook coverage](modules/conductguard/hook_coverage.md) — PreToolUse / PostToolUse hook matrix
- [Roles & permissions](modules/conductguard/roles_permissions.md) — RBAC seed data, permission names
- [Spend controls](modules/conductguard/spend_controls.md) — budgets, hard caps, alerts

---

## Integrations

Third-party systems Conduct plugs into.

- [Proliferate](integrations/proliferate.md) — LLM key distribution + rotation
- [Cedar adapter — spec](cedar-adapter-spec.md) — Cedar policy import contract
- [Cedar adapter — usage](cedar-adapter-usage.md) — how to import Cedar policies
- [Okta + Conduct](reference/okta-plus-conduct.md) — SSO / SCIM / group sync
- [Okta tracking](reference/okta-tracking.md) — audit trail for Okta-provisioned identities

---

## Examples

- [Examples](examples.md) — 37 pre-built playbooks grouped by what they do: code review, security scan + auto-fix, dependencies, incidents, releases, AI governance, autopilot, testing, docs, NetOps.

---

## ADRs

Decisions with tradeoffs written down. Read before proposing to change the same thing.

- [Index](adr/README.md)
- [ADR-0001 — Guard enforcement surfaces & trust boundaries](adr/ADR-0001-guard-enforcement-surfaces-and-trust-boundaries.md)
- [ADR-0002 — Policy pack schema & applicability contract](adr/ADR-0002-policy-pack-schema-and-applicability-contract.md)
- [ADR-0003 — Fail-open vs fail-closed semantics](adr/ADR-0003-fail-open-versus-fail-closed-semantics.md)
- [ADR-0004 — Playbook DSL vs external orchestration frameworks](adr/ADR-0004-playbook-dsl-versus-external-orchestration-frameworks.md)

---

## Not in this index

- `docs/demo-scripts/` — marketing/demo scripts, not user docs
- `docs/team-os/` — internal team standards (auth, migrations, security)
- `docs/mental-models/` files that don't yet exist in this list — none; all 12 are indexed above

## Contributing

New page? Add it to the section that matches the **goal** it serves, not the file type. If your page doesn't fit any section, that's a signal the taxonomy needs a new section — open an issue against #1525 rather than adding an "Other" pile.
