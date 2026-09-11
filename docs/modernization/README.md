# ConductAI modernization

External audit + implementation plan delivered 2026-09-11. Baseline commit:
`c918c6e051c0718eb7e61659b61fc1b8987fe3d6`.

Main has moved past that baseline. See [`progress.md`](./progress.md) for what's
already closed and what's still open.

## Files

| File | What it is |
|---|---|
| [`plan.md`](./plan.md) | Full 828-line modernization plan (decision, findings, contracts, migrations, work packages, definition of done). |
| [`findings.json`](./findings.json) | 44 structured findings with `source_paths`, `source_urls`, `implementation_tasks`, `status`. **Static snapshot at baseline** — do not edit. Track status in `progress.md`. |
| [`task-plan.json`](./task-plan.json) | 16 ordered tasks (T00–T15) with dependencies and verification requirements. Static. |
| [`route-parity.json`](./route-parity.json) | Seed manifest — 122 pages + 5 route handlers. Working file: annotate as pages migrate. |
| [`api-parity-seed.json`](./api-parity-seed.json) | 339 API surface entries. Runtime OpenAPI is authoritative for mounted contracts; this is the seed. |
| [`repository-inventory.json`](./repository-inventory.json) | 1,561 tracked entries at baseline. Static reference. |
| [`checksums.sha256`](./checksums.sha256) | Integrity check for the delivered audit package. |
| [`evidence/npm-audit.json`](./evidence/npm-audit.json) | 7 npm vulns (6 high, 1 moderate) — source for Q03. |
| [`evidence/validation-results.json`](./evidence/validation-results.json) | What the audit itself verified locally. |
| [`evidence/offline-check-results.json`](./evidence/offline-check-results.json) | 6 offline probes that confirmed insecure/fault behaviors. |
| [`progress.md`](./progress.md) | **Working** — status per finding, updated as PRs merge. |
| [`decisions.md`](./decisions.md) | **Working** — ADRs for choices made during modernization (empty at start). |

## How to use this

1. Read [`plan.md`](./plan.md) end-to-end before touching a slice — the contracts
   in §4–§6 override cosmetic instincts.
2. Pick a finding from `findings.json` or a task from `task-plan.json`.
3. Verify the finding against **current code** — main has moved. `progress.md`
   flags what's already closed.
4. Implement in a scoped PR. Reference the finding ID in the commit message
   (e.g. `fix(sec): S04 — ...`).
5. Update `progress.md` on merge.
6. If you make a non-obvious choice, log it in `decisions.md` — the audit
   explicitly asks for this.

## What's out of scope (deliberately)

The audit recommended a full-repo staged modernization spanning T00–T15
(~3–4 months of focused team work). We're not committing to that as a single
initiative. Findings get picked up individually as their business priority
justifies the fix — the plan is a shared vocabulary and a source of truth for
what "done" means, not a Gantt.
