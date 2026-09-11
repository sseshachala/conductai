# Move to `sseshachala/conduct-internal`

Files removed from this public repo in the same commit. Restore them into
`sseshachala/conduct-internal` at the same paths so nothing is lost.

Recover with:

```bash
git -C ~/projects/marshal show HEAD^:PATH > ~/projects/conduct-internal/PATH
```

## Root strategy / spec docs

- `NORTHSTAR.md`
- `NORTHSTAR_GOVERNANCE.md`
- `SPEC.md`
- `REVIEW.md`
- `ROLES.md`
- `DESIGN.md`
- `UNIFIED_RULE_SPEC.md.bak`

## Internal audits and modernization progress

- `audit/` (7 files)
- `docs/modernization/progress.md`

## Customer-flavored demo scripts

- `docs/demo-scripts/00-series-bible.md`
- `docs/demo-scripts/981-threat-modeler.md`
- `docs/demo-scripts/982-guard-and-security-loop.md`
- `docs/demo-scripts/984-fix-this-code.md`
- `docs/demo-scripts/E1-shoot-solo.md`
- `docs/demo-scripts/E1-the-140-dollar-ticket.md`
- `docs/demo-scripts/meridian-dispatch.pack.yaml`

## Competitor / capability comparison

- `docs/modules/conductguard/CAPABILITY_INVENTORY.md`

## Session and memory leaks

- `.claude/session-2026-05-31.md`
- `.claude/projects/-Users-sudhiseshachala-projects-marshal/memory/project_oss_contributions.md`

## Internal tooling that leaks customer codenames

- `scripts/scrub-history.sh` — hard-codes the "Venky" codename it scrubs

## Sanitized in place (kept public with vendor branding removed)

- `apps/api/playbooks/nemo-guardrails-demo.yaml` — dropped HPE PCAI / Unleash AI / local PDF path
- `apps/api/playbooks/self-driving-network-approval-demo.yaml` — dropped "HPE / Aruba" doubling
- `apps/api/playbooks/registry.yaml` — dropped `hpe` / `pcai` tags
- `packages/conduct-nemo-guard/examples/support-bot/README.md` + `config.yml` — dropped HPE PCAI screencast lines
- `.gitignore` — dropped `docs/venky/` codename patterns
- `CONTRIBUTING.md`, `SUPPORT.md`, `docs/README.md`, `docs/specs/GUARD_TOKEN_MODEL.md`, `docs/modules/conductguard/QUICKSTART.md`, `docs/modules/conductguard/README.md`, `docs/modules/conductguard/RUNBOOK.md` — pruned broken links to removed docs
- `apps/api/eval/report.py`, `apps/api/app/modules/guard/detectors/normalizer.py` — dropped stale doc references in comments
- `.claude/agents/team-lead.md`, `.claude/agents/runtime-engineer.md` — replaced `NORTHSTAR` with `roadmap`

## Not removed (public founder story, keep)

- `apps/web/src/app/(marketing)/about/page.tsx` — Xervmon reference is Sudhi's founder bio

## Not touched

- `apps/web/src/app/(marketing)/pricing/page.tsx` — pricing page is already public on the marketing site; no conflict.

## History note

Files are removed from HEAD only. `git log` still contains them. This is
normal for OSS repos. If a real secret ever needs to be scrubbed from
history, use `git filter-repo` and force-push — that breaks every open
clone, so only do it for true secrets, not for internal docs.

Delete this file after conduct-internal has the content restored.
