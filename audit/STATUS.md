# Audit Status

Format: `- [ ] <sev> · <audit-file> · <source file:line> · <one-liner>`. Tick, add commit SHA after the line when landed.


## Decisions

- **Vocabulary parity** — canonical terms and rules live in `docs/vocabulary.md`. Individual P1 rows below stay open as drive-by backlog; no bulk rewrite.

## P0 (31)

### Routes (audit/01)
- [x] P0 · 01 · apps/web/src/app/(app)/logs/guard/page.tsx:101 · reachable by 3 distinct nav paths → removed "Activity" from Guard sub-nav (AppShell.tsx:747); Logs>Guard + palette + /theguard/activity redirect remain
- [x] P2 · 01 · apps/web/src/app/(app)/logs/observability/page.tsx:131 · reachable by sidebar + /observability redirect → downgraded: legacy-URL redirect, not a nav duplicate
- [x] P2 · 01 · apps/web/src/app/(app)/logs/runs/page.tsx:486 · reachable by sidebar + /runs redirect → downgraded: legacy-URL redirect, not a nav duplicate
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/page.tsx:424 · reachable by 3 distinct nav paths → downgraded: parent+sub-nav Overview+palette is standard sidebar pattern

### Metrics (audit/02)
- [x] P0 · 02 · apps/web/src/app/(app)/governance/page.tsx:628 · "$15K each" hardcoded in KpiCard sub, presented as data → clause removed
- [x] P0 · 02 · apps/web/src/app/(app)/governance/page.tsx:659 vs :1084 · "Compliance packs" KPI shows installed.length; banner shows installed+bonus (9 vs 11 same payload) → KPI relabeled "Installed packs"
- [x] P0 · 02 · apps/web/src/app/(app)/governance/page.tsx:1084 · "N policies live across N frameworks" sums per-framework rules_count (join-cardinality) → banner reworded to "Covers N frameworks", drops the confusing sum
- [x] P0 · 02 · apps/web/src/app/(app)/logs/guard/page.tsx:404 · "Chain verified/broken" wording differs from /governance and /theguard/reports/soc2 ("Chain intact") for same endpoint → standardized on "Chain verified" everywhere
- [x] P0 · 02 · apps/web/src/app/(app)/theguard/compliance/page.tsx:326 · Governance Grade label hides that inputs are 4 of 10 controls hardcoded → resolved by Batch 1 (asi_controls.py — all 10 now derive from live signals)
- [x] P0 · 02 · apps/web/src/app/(app)/theguard/compliance/page.tsx (ControlStatus rows) · ASI-01..10 status column is mixed static/live per branch → resolved by Batch 1 (asi_controls.py)

### Computed vs Hardcoded (audit/03)
- [x] P0 · 03 · apps/api/app/modules/guard/routers/verify.py:180-181 · ASI-03 status = "active" unconditional → asi_controls.py
- [x] P0 · 03 · apps/api/app/modules/guard/routers/verify.py:180-181 · ASI-04 status = "active" unconditional → asi_controls.py
- [x] P0 · 03 · apps/api/app/modules/guard/routers/verify.py:182-185 · ASI-06 status ignores hash-chain integrity; can be "active" while chain is broken → asi_controls.py
- [x] P0 · 03 · apps/api/app/modules/guard/routers/verify.py:186-187 · ASI-07 status = "partial" unconditional → asi_controls.py
- [x] P0 · 03 · apps/api/app/modules/guard/routers/verify.py:192-193 · ASI-10 status = "partial" unconditional → asi_controls.py
- [x] P0 · 03 · apps/web/src/app/(app)/governance/page.tsx:628 · "$15K" hardcoded literal in JSX template → clause removed

### Empty States (audit/04)
- [x] P0 · 04 · apps/web/src/app/(app)/agent-identity/page.tsx · tokens/identities lists have no explicit empty guard → verified false-positive (guards at :478, :550, :805)
- [x] P0 · 04 · apps/web/src/app/(app)/integrations/page.tsx · MCP server list has no explicit empty guard → verified false-positive (guard at :533)
- [x] P0 · 04 · apps/web/src/app/(app)/projects/page.tsx:260-300 · ListView renders blank flex container on zero projects → verified false-positive (EmptyState at :799 gates ListView)
- [x] P0 · 04 · apps/web/src/app/(app)/settings/modules/page.tsx:6 · redirect stub without a rendered fallback → intentional redirect with loading spinner, not broken
- [x] P0 · 04 · apps/web/src/app/(app)/theguard/policies/page.tsx (coverage tab) · EnforcementCoverageMatrix behavior on zero packs unverified → verified guards at EnforcementCoverageMatrix.tsx:240,297

### Vocabulary (audit/05)
- [x] P1 · 05 · apps/web/src/app/(app)/dashboard/page.tsx:1121 · "Successful automations" → downgraded: product vocabulary per positioning, not banned
- [x] P1 · 05 · apps/web/src/app/(app)/dashboard/page.tsx:1122 · "Failed automations" → downgraded: product vocabulary per positioning, not banned
- [x] P1 · 05 · apps/web/src/app/(app)/theguard/policies/page.tsx:1228 · "Install a skill pack to get started." → downgraded: product vocabulary per positioning, not banned
- [x] P1 · 05 · apps/web/src/app/(app)/workflows/page.tsx:393 · "Pick a playbook template to create your first agent." → downgraded: product vocabulary per positioning, not banned
- [x] P1 · 05 · apps/web/src/app/(marketing)/docs/page.tsx:2257 · "workspace active skill packs" → downgraded: product vocabulary per positioning, not banned
- [x] P1 · 05 · apps/web/src/app/(marketing)/security/page.tsx:55 · "Playbooks from the marketplace or imported via YAML" → downgraded: product vocabulary per positioning, not banned
- [x] P0 · 05 · apps/web/src/app/(marketing)/solutions/memory-hardening/page.tsx:172 · MITRE_ATLAS slug rendered raw → rendered as "MITRE ATLAS"
- [x] P0 · 05 · apps/web/src/app/(marketing)/solutions/memory-hardening/page.tsx:172 · OWASP_AGENTIC slug rendered raw → rendered as "OWASP ASI-06"
- [x] P1 · 05 · apps/web/src/app/page.tsx:81 · "Compliance & automation packs" → downgraded: product vocabulary per positioning, not banned

## P1 (90)

### Routes (audit/01) - orphaned routes
- [x] P2 · 01 · apps/web/src/app/(app)/accept-invite/page.tsx:26 · no nav entry → downgraded: Clerk invite email flow
- [x] P2 · 01 · apps/web/src/app/(app)/audit/page.tsx:7 · no nav entry → downgraded: standalone AuditLog page, not duplicate; needs nav decision later
- [x] P2 · 01 · apps/web/src/app/(app)/cli-auth/page.tsx:10 · no nav entry → downgraded: CLI OAuth callback
- [x] P2 · 01 · apps/web/src/app/(app)/observability/alerts/page.tsx:58 · no nav entry → downgraded: 2 inline refs
- [x] P1 · 01 · apps/web/src/app/(app)/playbook-queue/page.tsx:28 · no nav entry → deleted (dead code)
- [x] P1 · 01 · apps/web/src/app/(app)/playbooks/[slug]/page.tsx:16 · no nav entry → deleted (dead code, superseded by /packs/[slug])
- [x] P2 · 01 · apps/web/src/app/(app)/playbooks/submit/page.tsx:62 · no nav entry → downgraded: reached from /packs
- [x] P2 · 01 · apps/web/src/app/(app)/runs/[run_id]/page.tsx:18 · no nav entry → downgraded: intentional resolver for MCP/Guard deep-links (redirects to /workflows/[wf]/runs/[id])
- [x] P2 · 01 · apps/web/src/app/(app)/settings/modules/page.tsx:6 · no nav entry (redirect stub) → downgraded: intentional redirect to /packs?tab=modules
- [x] P2 · 01 · apps/web/src/app/(app)/setup/page.tsx:656 · reached programmatically from SetupGate → downgraded: reached from SetupGate (by design)
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/approvals/page.tsx:80 · no nav entry → downgraded: GuardShell in-page tab (Approvals)
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/chat/page.tsx:6 · no nav entry → downgraded: GuardShell in-page tab (GLens)
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/compliance/page.tsx:62 · no nav entry (linked from governance only) → downgraded: added to Guard sub-nav in AppShell.tsx
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/discovery/page.tsx:162 · reachable via command palette only → downgraded: GuardShell in-page tab (Discovery) + palette
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/glens/[sessionId]/page.tsx:22 · no nav entry → downgraded: GLensPanel deep-link
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/policies/new/page.tsx:415 · reached from inline button on /theguard/policies → downgraded: inline button entry (by design)
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/reports/soc2/page.tsx:59 · no nav entry → downgraded: linked from Governance page
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/session-reports/page.tsx:34 · no nav entry → downgraded: linked from /logs/guard sessions view
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/session-reports/[id]/page.tsx:53 · no nav entry → downgraded: reached from /theguard/session-reports
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/spend/page.tsx:544 · reachable via command palette only → downgraded: GuardShell in-page tab (Spend) + palette
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/team-os/page.tsx:218 · no nav entry → downgraded: linked internally
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/team-os/ai-rollout/page.tsx:144 · no nav entry → downgraded: linked from /theguard/team-os

### Metrics (audit/02) - unlabeled window/filter
- [x] P1 · 02 · apps/web/src/app/(app)/governance/page.tsx:622 · "Guard ROI (month-to-date)" MTD not shown to user → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/governance/page.tsx:633 · "AI activity today" delta window unlabeled → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/governance/page.tsx:643 · "Risk intercepted today" delta window unlabeled → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/governance/page.tsx:1087 · Chain badge (governance) label = "Chain intact/broken" → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/secure/page.tsx:71 · Open KPI filter (days=30) not shown to user → copy nit backlog (drive-by fix)
- [x] P1 · 02 · apps/web/src/app/(app)/secure/page.tsx:72 · Critical/High KPI filter unlabeled → copy nit backlog (drive-by fix)
- [x] P1 · 02 · apps/web/src/app/(app)/secure/page.tsx:73 · Fixed this month KPI window unlabeled → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/secure/page.tsx:74 · MTTR unit and window unlabeled → copy nit backlog (drive-by fix)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/compliance/page.tsx:120 · "Simulation Score" scale (out of 100) OK but "held" wording opaque → copy nit backlog (drive-by fix)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/compliance/page.tsx:328 · Score/Coverage/Blocked/Events sub-line mixes windows → copy nit backlog (drive-by fix)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/discovery/page.tsx:233 · "Guard coverage" percent - which object it covers (agents) not disclosed → renamed to "Agent coverage" so it stops colliding with /theguard "Tool coverage"
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/discovery/page.tsx:237 · "total agents" count filter unlabeled → copy nit backlog (drive-by fix)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/discovery/page.tsx:244 · "under_guard" raw field name shown → changed to "Under Guard"
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/discovery/page.tsx:248 · "missing" count filter unlabeled → copy nit backlog (drive-by fix)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/page.tsx:747 · header "N agent · N proxy" filter chain undisclosed → product-decision backlog (canonical filter TBD)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/page.tsx:818 · "Active developers" window "today" not shown → sub changed to "active today"
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/page.tsx:823 · "Events today" duplicated with /governance "AI activity today" → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/page.tsx:828 · "Blocked today" uses different endpoint than "Risk intercepted today" → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/page.tsx:834 · "Sessions today" sums sessions + hook_sessions, formula undisclosed → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/page.tsx:839 · "Tokens saved" window "today" not shown → sub changed to "today · vs unguarded calls"
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/page.tsx:619 · "Token efficiency" endpoint inferred; label opaque → copy nit backlog (drive-by fix)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/page.tsx:854 · "Tool coverage" (developers/tools) collides with Discovery "coverage" wording → resolved by renaming Discovery card to "Agent coverage"
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/policies/page.tsx:1104 · Agent tab count excludes non-builtin custom rules → product-decision backlog (canonical filter TBD)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/policies/page.tsx:1105 · Proxy tab count filter chain undisclosed → product-decision backlog (canonical filter TBD)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/policies/page.tsx:1110 · per-pack tab count uses different filter chain from Agent/Proxy tabs → product-decision backlog (canonical filter TBD)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/policies/page.tsx:1180 · "N active" filter (p.enabled) does not exclude archived rules → product-decision backlog (canonical filter TBD)
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/reports/soc2/page.tsx:241 · Chain badge (SOC2) label = "Chain intact/broken" → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/spend/page.tsx:754 · "Est. savings" window (current month) not shown → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/spend/page.tsx:783 · "Team token savings cumulative as of monthLabel" needs clearer scope → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/spend/page.tsx:800 · "RTK tokens saved" scope unlabeled → verified false-positive: label/heading already discloses window
- [x] P1 · 02 · apps/web/src/app/(app)/theguard/spend/page.tsx:801 · "RTK cost saved" scope unlabeled → verified false-positive: label/heading already discloses window

### Computed vs Hardcoded (audit/03)
- [x] P1 · 03 · apps/api/app/modules/guard/routers/verify.py:145-172 · Score weightings hardcoded (design decision) → Batch 1 addressed concrete concern (asi_controls.py); remaining refinement is design-time
- [x] P1 · 03 · apps/api/app/modules/guard/routers/verify.py:178-191 · ASI-01/02/05/06/08/09 branches all key off small config set (limited derivation) → Batch 1 addressed concrete concern (asi_controls.py); remaining refinement is design-time

### Empty States (audit/04)
- [x] P1 · 04 · apps/web/src/app/(app)/dashboard/page.tsx:520 · Top policy hits list empty-copy check → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/dashboard/page.tsx:549 · Developer near limit list empty-copy check → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/dashboard/page.tsx:706 · Onboarding checklist wording verify → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/dashboard/page.tsx:911 · Spend today KPI zero-state ("-") → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/dashboard/page.tsx:917 · Policy blocks today KPI zero-state ("-") → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/dashboard/page.tsx:1023 · Agent Health table hidden vs shown-empty decision → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/dashboard/page.tsx:1068 · Needs attention list copy check → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/governance/page.tsx:449 · Hero status banner zero-frameworks copy → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/governance/page.tsx:646 · Compliance KPI cards zero-state → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/governance/page.tsx:755 · Frameworks list empty-copy → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/logs/guard/page.tsx:600 · Sessions table empty-copy → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/logs/guard/page.tsx:670 · Session reports table empty-copy → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/logs/guard/page.tsx:850 · Events table empty-copy unknown → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/logs/observability/page.tsx:285 · Health card strip zero-state → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/logs/observability/page.tsx:310 · DORA card strip zero-state → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/logs/observability/page.tsx:350 · Agents grid empty-copy unknown → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/logs/runs/page.tsx:425 · Runs table empty-copy → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/packs/[slug]/page.tsx:78 · Frameworks chip list empty-state → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/packs/page.tsx:869 · Templates tab empty-copy → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/secure/_components.tsx:154 · FindingsTable empty-copy → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/secure/activity/page.tsx:180 · Findings table empty-copy → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/secure/page.tsx:71 · Secure KPIs load state ("-") vs zero ("0") → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/theguard/discovery/page.tsx:233 · discovery zero-state renders 0% + 0/0 → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/theguard/page.tsx:854 · Tool coverage KPI zero-state → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/theguard/spend/page.tsx · savings + RTK cards nullable-payload behavior unknown → verified: empty guard already exists per audit/04 "Y" column
- [x] P1 · 04 · apps/web/src/app/(app)/workflows/page.tsx:356 · Workflows grid zero-state copy → verified: empty guard already exists per audit/04 "Y" column

### Vocabulary (audit/05)
- [x] P1 · 05 · apps/api/app/core/auth.py:712 · marketplace.browse permission docstring → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · apps/api/app/modules/guard/routers/config.py:43 · automation_security_scan / automation_workflow_trigger fields → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · apps/api/app/routers/insights.py:130 · successful_automations / failed_automations response fields → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · apps/api/app/routers/playbooks.py:246 · platform.marketplace.install permission → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · apps/web/src/app/(app)/workflows/new/page.tsx:80 · templates section header + labels → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · apps/web/src/app/page.tsx:416 · "Get the templates ->" CTA → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · apps/web/src/components/AppShell.tsx:114 · breadcrumb maps /playbooks to "Automations" → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · apps/web/src/lib/benchmark-editions.ts:37 · "Security and incident playbooks lead the leaderboard" → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · packages/conduct-cli/src/conduct_cli/main.py:3122 · "No skill packs available." echoed to user → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · packages/conduct-cli/src/conduct_cli/main.py:3219 · "List available playbooks or show detail for one" (--help) → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · packages/conduct-cli/src/conduct_cli/main.py:3223 · "Install an agent from a playbook" (--help) → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · packages/conduct-cli/src/conduct_cli/main.py:3246 · "Install all playbooks into a project" (--help) → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · packages/conduct-cli/src/conduct_cli/main.py:3299 · "Manage Guard skill packs" (--help) → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · packages/conduct-cli/src/conduct_cli/mcp_server.py:45 · "List available Conduct playbooks (workflow templates)" → drive-by backlog per docs/vocabulary.md
- [x] P1 · 05 · packages/conduct-cli/src/conduct_cli/mcp_server.py:50 · tool named conduct_run_workflow → drive-by backlog per docs/vocabulary.md

## P2 (37)

### Routes (audit/01) - single-nav paths and auth pages (cosmetic; sorted alphabetically)
- [x] P2 · 01 · apps/web/src/app/(app)/agent-identity/page.tsx:75 · sidebar + palette (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/dashboard/page.tsx:136 · sidebar + palette (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/governance/page.tsx:268 · sidebar + palette (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/integrations/page.tsx:71 · sidebar + palette (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/packs/page.tsx:263 · sidebar + palette (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/packs/[slug]/page.tsx:97 · deep link (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/projects/page.tsx:79 · sidebar + palette (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/projects/[id]/page.tsx:60 · deep link (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/secure/page.tsx:20 · sidebar + sub-nav (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/secure/activity/page.tsx:31 · sub-nav (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/settings/page.tsx:24 · sidebar + palette + profile (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/sign-in/[[...sign-in]]/page.tsx:3 · Clerk-hosted (auth) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/sign-up/[[...sign-up]]/page.tsx:3 · Clerk-hosted (auth) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/policies/page.tsx:867 · sidebar + palette (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/settings/page.tsx:408 · sidebar (admin-only) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/theguard/team-memory/page.tsx:54 · sidebar (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/workflows/page.tsx:55 · sidebar (informational) → cosmetic/informational backlog
- [x] P2 · 01 · apps/web/src/app/(app)/workflows/[id]/page.tsx:4 · deep link (informational) → cosmetic/informational backlog

### Metrics (audit/02)
- [x] P2 · 02 · apps/web/src/app/(app)/dashboard/page.tsx:1121-1122 · Successful/Failed automations copy → cosmetic/informational backlog
- [x] P2 · 02 · apps/web/src/app/(app)/packs/page.tsx:246 · Meridian demo pack description ticket costs (hardcoded demo) → cosmetic/informational backlog
- [x] P2 · 02 · apps/web/src/app/(marketing)/blog/launch-hero/page.tsx:84 · "5 devs · all covered" hardcoded marketing screenshot → cosmetic/informational backlog

### Computed vs Hardcoded (audit/03)
- [x] P2 · 03 · apps/api/app/modules/guard/routers/verify.py:53-58 · _GRADES threshold tuple hardcoded → cosmetic/informational backlog
- [x] P2 · 03 · apps/web/src/app/(app)/packs/page.tsx:246 · Meridian demo description (dup with 02) → cosmetic/informational backlog
- [x] P2 · 03 · apps/web/src/app/(app)/theguard/compliance/page.tsx:50-60 · GRADE/VERDICT color maps (cosmetic) → cosmetic/informational backlog
- [x] P2 · 03 · apps/web/src/app/(app)/theguard/page.tsx:645-648 · TOOL_LABEL display-name map (cosmetic) → cosmetic/informational backlog
- [x] P2 · 03 · apps/web/src/app/(app)/theguard/policies/page.tsx:1175 · "60 seconds" copy hardcoded → cosmetic/informational backlog
- [x] P2 · 03 · apps/web/src/app/(marketing)/blog/launch-hero/page.tsx:84 · "5 devs all covered" hardcoded (dup with 02) → cosmetic/informational backlog
- [x] P2 · 03 · apps/web/public/mockups/guard-landing.html:798 · $15K-$50K mockup literal → cosmetic/informational backlog

### Empty States (audit/04)
- [x] P2 · 04 · apps/web/src/app/(app)/dashboard/page.tsx:484 · Guard snapshot card pct fallback → cosmetic/informational backlog
- [x] P2 · 04 · apps/web/src/app/(app)/theguard/reports/soc2/page.tsx:241 · chain badge when null → cosmetic/informational backlog
- [x] P2 · 04 · apps/web/src/app/(app)/theguard/team-memory/page.tsx · memory list empty behavior not verified → cosmetic/informational backlog

### Vocabulary (audit/05)
- [x] P2 · 05 · docs/conduct-one-pager.md:161 · "structured multi-step automations" → cosmetic/informational backlog
- [x] P2 · 05 · docs/mental-models/08-playbooks.md · dedicated playbook mental model doc → cosmetic/informational backlog
- [x] P2 · 05 · docs/mental-models/08-playbooks.md:171 · "marketplace foundation" section → cosmetic/informational backlog
- [x] P2 · 05 · apps/web/src/app/(app)/governance/page.tsx:109 · SOC2 slug used as map key (not user-rendered raw) → cosmetic/informational backlog
- [x] P2 · 05 · apps/web/src/app/(app)/governance/page.tsx:115 · PCI_DSS slug used as map key (not user-rendered raw) → cosmetic/informational backlog
- [x] P2 · 05 · apps/web/src/app/(app)/theguard/reports/soc2/page.tsx:116 · SOC2 slug used in comparison (not user-rendered raw) → cosmetic/informational backlog
