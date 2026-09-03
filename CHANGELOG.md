# Changelog

Conduct ships continuously. Per-release notes live in
[GitHub Releases](https://github.com/sseshachala/conductai/releases) —
one per tag, generated from the underlying commits.

The list below is a high-level view of platform milestones. For every
version bump on the CLI, the runtime, the booster, or the API, see the
Releases page.

## Milestones

### 2026-08 · Public source, Apache 2.0
- Main platform repository made public under the
  [Apache License 2.0](./LICENSE) — free for commercial and non-commercial
  use, includes an explicit patent grant from all contributors. Previously
  distributed under FSL-1.1-MIT; relicensed to Apache 2.0 for broader
  enterprise adoption.
- Guard + Router shipping as two product surfaces in one repo.
- Hash-chained audit + signed-configuration moat locked in.
- Cedar interchange arc opened (issue #1193) — Guard Profile v1
  targeting standards-based interoperability.

### 2026-07 · Runtime governance stack
- Guard proxy shipped end-to-end (Portkey / native adapters).
- Per-agent tokens (`cond_agt_*`) — mint at run start, propagate via
  RunContext, single-owner executor.
- Slack Approve/Reject buttons for HITL approval flows.
- Discovery mode — read-only, promote observed rules into enforcement.

### 2026-06 · Compliance packs + policy engine
- 15 compliance packs shipped (OWASP, SOC 2, HIPAA, PCI, EU AI Act).
- Persona-aware rules with `signed_config` verification on every check.
- Guard Verify v2 — adversarial battery + `conduct verify` CLI.

### 2026-05 · First release wave
- Canvas UI, playbook DSL, YAML loader, workspace-scoped audit.
- MCP OAuth on Claude.ai — Guard endpoint at
  `https://api.conductai.ai/guard/mcp`.
- 39 playbooks covering GitHub, Slack, CI/CD, and incident response workflows.

## Version tag conventions

We ship separately-versioned components under prefixed tags:

- `cli/vX.Y.Z` — Conduct CLI (Python).
- `booster-vX.Y.Z` — Agent Booster (Python).
- `booster-v0.X.Y` — legacy Booster tags.
- `conduct-cli/vX.Y.Z` — legacy CLI tags.
- `api/vX.Y.Z` — API service.
- `vX.Y.Z` — platform / marketing versions.

Each tag has release notes on the
[Releases page](https://github.com/sseshachala/conductai/releases).

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). Please describe the **why**
in commit messages — this file gets easier to write when they do.
