# Audit 04 - Empty States

Every list, table, and metric card in scope. P0 = throws or renders broken layout on empty.

## Table

| component file:line | route | has defined empty state (Y/N) | what a brand-new workspace renders | severity |
|---|---|---|---|---|
| apps/web/src/app/(app)/agent-identity/page.tsx (tokens/identities lists) | /agent-identity | UNKNOWN | UNKNOWN - no explicit `array.length === 0` guard visible; renders empty grid or crashes on undefined | P0 |
| apps/web/src/app/(app)/integrations/page.tsx (MCP server list) | /integrations | UNKNOWN | UNKNOWN - no explicit empty guard on servers array; modal flow may hide the issue | P0 |
| apps/web/src/app/(app)/projects/page.tsx:260-300 (ListView) | /projects | N | blank flex container (no "No projects yet" copy) | P0 |
| apps/web/src/app/(app)/settings/modules/page.tsx:6 | /settings/modules | N/A | redirect stub; not a rendered page | P0 |
| apps/web/src/app/(app)/theguard/policies/page.tsx (Enforcement Coverage Matrix) | /theguard/policies (coverage tab) | UNKNOWN | UNKNOWN - EnforcementCoverageMatrix behavior on zero installed packs not verified | P0 |
| apps/web/src/app/(app)/dashboard/page.tsx:911 (Spend today KPI) | /dashboard | Y | dash via `data && cost > 0 ? toFixed(2) : dash` (line 855) | P1 |
| apps/web/src/app/(app)/dashboard/page.tsx:917 (Policy blocks today KPI) | /dashboard | Y | dash via `policyBlocksToday ?? 0` (line 429) | P1 |
| apps/web/src/app/(app)/dashboard/page.tsx:520 (Top policy hits list) | /dashboard | Y | empty card via `topPolicyHits.length === 0` guard | P1 |
| apps/web/src/app/(app)/dashboard/page.tsx:549 (Developer near limit) | /dashboard | Y | empty card via `developerNearLimit.length === 0` | P1 |
| apps/web/src/app/(app)/dashboard/page.tsx:706 (Onboarding checklist) | /dashboard | Y | "No agents yet. Follow these steps..." when `agent_health.length === 0` (line 967) | P1 |
| apps/web/src/app/(app)/dashboard/page.tsx:1023 (Agent Health table) | /dashboard | Y | hidden via `data.agent_health.length > 0` | P1 |
| apps/web/src/app/(app)/dashboard/page.tsx:1068 (Needs attention list) | /dashboard | Y | "All clear - no runs need attention." (line 1065) | P1 |
| apps/web/src/app/(app)/governance/page.tsx:449 (Hero status banner) | /governance | Y | Skeleton then "No compliance frameworks active" when totalFrameworks === 0 (line 478) | P1 |
| apps/web/src/app/(app)/governance/page.tsx:646 (Compliance KPI cards) | /governance | Y | dash or descriptive empty per card via installedPacks.length checks | P1 |
| apps/web/src/app/(app)/governance/page.tsx:755 (Frameworks list) | /governance | Y | "No frameworks covered yet..." when installed+bonus both empty | P1 |
| apps/web/src/app/(app)/logs/guard/page.tsx:600 (Sessions table) | /logs/guard | Y | "No sessions found." centered text | P1 |
| apps/web/src/app/(app)/logs/guard/page.tsx:670 (Session reports table) | /logs/guard | Y | copy on empty | P1 |
| apps/web/src/app/(app)/logs/runs/page.tsx:425 (Runs table) | /logs/runs | Y | "No runs" / "Nothing to show for this filter." | P1 |
| apps/web/src/app/(app)/logs/observability/page.tsx:285 (Health card strip) | /logs/observability | Y | dash per card | P1 |
| apps/web/src/app/(app)/logs/observability/page.tsx:310 (DORA card strip) | /logs/observability | Y | dash per card | P1 |
| apps/web/src/app/(app)/logs/observability/page.tsx:350 (Agents grid) | /logs/observability | UNKNOWN | list renders empty rows; no explicit copy | P1 |
| apps/web/src/app/(app)/packs/[slug]/page.tsx:78 (Frameworks chip list) | /packs/[slug] | Y | dash when frameworks empty | P1 |
| apps/web/src/app/(app)/packs/page.tsx:869 (Templates tab) | /packs | Y | "No agent templates match your search." | P1 |
| apps/web/src/app/(app)/secure/_components.tsx:154 (FindingsTable) | /secure and /secure/activity | Y | "No findings yet..." | P1 |
| apps/web/src/app/(app)/secure/activity/page.tsx:180 (Findings table) | /secure/activity | Y | "No findings match your filters." | P1 |
| apps/web/src/app/(app)/secure/page.tsx:71 (Open/CritHigh/Fixed/MTTR KPIs) | /secure | Y | dash during load, 0 when ready | P1 |
| apps/web/src/app/(app)/theguard/discovery/page.tsx:233 (coverage + counts) | /theguard/discovery | Y | 0 percent + 0/0 | P1 |
| apps/web/src/app/(app)/theguard/page.tsx:854 (Tool coverage KPI) | /theguard | Y | dash when totalDevs === 0; sub "no data yet" | P1 |
| apps/web/src/app/(app)/theguard/spend/page.tsx (savings + RTK cards) | /theguard/spend | Y (partial) | 0.00 numeric; UNKNOWN if payload nullable | P1 |
| apps/web/src/app/(app)/workflows/page.tsx:356 (Workflows grid) | /workflows | Y | "No agents yet. Pick a playbook template..." | P1 |
| apps/web/src/app/(app)/dashboard/page.tsx:484 (Guard snapshot card) | /dashboard | Y | dash for pct via `(pct ?? 0)` (line 484, 425) | P2 |
| apps/web/src/app/(app)/theguard/reports/soc2/page.tsx:241 (chain badge) | /theguard/reports/soc2 | Y | badge with dash when chain null | P2 |
| apps/web/src/app/(app)/theguard/team-memory/page.tsx (memory list) | /theguard/team-memory | UNKNOWN | not verified in detail | P2 |
