# Audit 01 — Routes & Navigation

Scope: every route under `apps/web/src/app/(app)/**` (Next.js App Router). Sidebar + command palette + Guard sub-nav + Secure sub-nav + Logs sub-nav enumerated. Sub-tabs enumerated inside pages.

## Routes table

| route | component file:line | nav paths that reach it | duplicate of | orphaned (Y/N) | severity |
|---|---|---|---|---|---|
| /logs/guard | apps/web/src/app/(app)/logs/guard/page.tsx:101 | Sidebar → Govern → Guard → Activity (AppShell.tsx:747)  \| Sidebar → Observe → Logs → Guard (AppShell.tsx:962)  \| Command palette → GOVERN → Guard·Activity (AppShell.tsx:150)  \| Redirect from /theguard/activity (theguard/activity/page.tsx:2) | — (3 distinct sidebar/palette paths + 1 redirect) | N | P0 |
| /logs/observability | apps/web/src/app/(app)/logs/observability/page.tsx:131 | Sidebar → Observe → Logs → Observability (AppShell.tsx:964)  \| Redirect from /observability (observability/page.tsx:2) | — | N | P0 |
| /logs/runs | apps/web/src/app/(app)/logs/runs/page.tsx:486 | Sidebar → Observe → Logs → Runs (AppShell.tsx:963)  \| Redirect from /runs (runs/page.tsx:2) | — | N | P0 |
| /theguard | apps/web/src/app/(app)/theguard/page.tsx:424 | Sidebar → Govern → Guard (AppShell.tsx:734)  \| Sidebar → Govern → Guard → Overview sub-nav (AppShell.tsx:744)  \| Command palette → GOVERN → Guard·Overview (AppShell.tsx:146) | — | N | P0 |
| /accept-invite | apps/web/src/app/(app)/accept-invite/page.tsx:26 | (none) | — | Y | P1 |
| /audit | apps/web/src/app/(app)/audit/page.tsx:7 | (none) | — | Y | P1 |
| /cli-auth | apps/web/src/app/(app)/cli-auth/page.tsx:10 | (none) | — | Y | P1 |
| /observability/alerts | apps/web/src/app/(app)/observability/alerts/page.tsx:58 | (none) | — | Y | P1 |
| /playbook-queue | apps/web/src/app/(app)/playbook-queue/page.tsx:28 | (none) | — | Y | P1 |
| /playbooks/[slug] | apps/web/src/app/(app)/playbooks/[slug]/page.tsx:16 | (none) | — | Y | P1 |
| /playbooks/submit | apps/web/src/app/(app)/playbooks/submit/page.tsx:62 | (none) | — | Y | P1 |
| /runs/[run_id] | apps/web/src/app/(app)/runs/[run_id]/page.tsx:18 | (none — legacy resolver, replaced by /workflows/[id]/runs/[run_id]) | — | Y | P1 |
| /settings/modules | apps/web/src/app/(app)/settings/modules/page.tsx:6 | (none — redirect stub) | /settings | Y | P1 |
| /setup | apps/web/src/app/(app)/setup/page.tsx:656 | (none — reached programmatically from SetupGate) | — | Y | P1 |
| /theguard/approvals | apps/web/src/app/(app)/theguard/approvals/page.tsx:80 | (none) | — | Y | P1 |
| /theguard/chat | apps/web/src/app/(app)/theguard/chat/page.tsx:6 | (none) | — | Y | P1 |
| /theguard/compliance | apps/web/src/app/(app)/theguard/compliance/page.tsx:62 | (none in sidebar/palette; linked internally from governance) | — | Y | P1 |
| /theguard/discovery | apps/web/src/app/(app)/theguard/discovery/page.tsx:162 | Command palette → GOVERN → Guard·Discovery (AppShell.tsx:149) | — | N | P1 |
| /theguard/glens/[sessionId] | apps/web/src/app/(app)/theguard/glens/[sessionId]/page.tsx:22 | (none) | — | Y | P1 |
| /theguard/policies/new | apps/web/src/app/(app)/theguard/policies/new/page.tsx:415 | (none — reached from /theguard/policies inline button) | — | Y | P1 |
| /theguard/reports/soc2 | apps/web/src/app/(app)/theguard/reports/soc2/page.tsx:59 | (none) | — | Y | P1 |
| /theguard/session-reports | apps/web/src/app/(app)/theguard/session-reports/page.tsx:34 | (none) | — | Y | P1 |
| /theguard/session-reports/[id] | apps/web/src/app/(app)/theguard/session-reports/[id]/page.tsx:53 | (none) | — | Y | P1 |
| /theguard/spend | apps/web/src/app/(app)/theguard/spend/page.tsx:544 | Command palette → GOVERN → Guard·Spend (AppShell.tsx:147) | — | N | P1 |
| /theguard/team-os | apps/web/src/app/(app)/theguard/team-os/page.tsx:218 | (none) | — | Y | P1 |
| /theguard/team-os/ai-rollout | apps/web/src/app/(app)/theguard/team-os/ai-rollout/page.tsx:144 | (none) | — | Y | P1 |
| /agent-identity | apps/web/src/app/(app)/agent-identity/page.tsx:75 | Sidebar → Workspace → Agent ID (AppShell.tsx:1032)  \| Command palette → WORKSPACE → Agent ID (AppShell.tsx:152) | — | N | P2 |
| /dashboard | apps/web/src/app/(app)/dashboard/page.tsx:136 | Sidebar → Dashboard (AppShell.tsx:707)  \| Command palette → OBSERVE → Dashboard (AppShell.tsx:143) | — | N | P2 |
| /governance | apps/web/src/app/(app)/governance/page.tsx:268 | Sidebar → Govern → Runtime Governance (AppShell.tsx:727)  \| Command palette → GOVERN → Runtime Governance (AppShell.tsx:145) | — | N | P2 |
| /integrations | apps/web/src/app/(app)/integrations/page.tsx:71 | Sidebar → Workspace → Integrations (AppShell.tsx:1025)  \| Command palette → WORKSPACE → Integrations (AppShell.tsx:151) | — | N | P2 |
| /packs | apps/web/src/app/(app)/packs/page.tsx:263 | Sidebar → Build → Registry (AppShell.tsx:935)  \| Command palette → BUILD → Registry (AppShell.tsx:142) | — | N | P2 |
| /packs/[slug] | apps/web/src/app/(app)/packs/[slug]/page.tsx:97 | Sidebar → Build → Registry → [pack] | — | N | P2 |
| /projects | apps/web/src/app/(app)/projects/page.tsx:79 | Sidebar → Build → Projects (AppShell.tsx:826)  \| Command palette → BUILD → Projects (AppShell.tsx:140) | — | N | P2 |
| /projects/[id] | apps/web/src/app/(app)/projects/[id]/page.tsx:60 | Sidebar → Build → Projects → [project] (AppShell.tsx:864) | — | N | P2 |
| /secure | apps/web/src/app/(app)/secure/page.tsx:20 | Sidebar → Govern → Secure (AppShell.tsx:775)  \| Sidebar → Govern → Secure → Overview sub-nav (AppShell.tsx:785) | — | N | P2 |
| /secure/activity | apps/web/src/app/(app)/secure/activity/page.tsx:31 | Sidebar → Govern → Secure → Findings (AppShell.tsx:786) | — | N | P2 |
| /settings | apps/web/src/app/(app)/settings/page.tsx:24 | Sidebar → Workspace → Settings (AppShell.tsx:1039)  \| Command palette → WORKSPACE → Settings·Environments (AppShell.tsx:153)  \| Profile menu → Settings (AppShell.tsx:1520) | — | N | P2 |
| /sign-in/[[...sign-in]] | apps/web/src/app/(app)/sign-in/[[...sign-in]]/page.tsx:3 | (none — Clerk-hosted) | — | Y (auth) | P2 |
| /sign-up/[[...sign-up]] | apps/web/src/app/(app)/sign-up/[[...sign-up]]/page.tsx:3 | (none — Clerk-hosted) | — | Y (auth) | P2 |
| /theguard/policies | apps/web/src/app/(app)/theguard/policies/page.tsx:867 | Sidebar → Govern → Guard → Policies (AppShell.tsx:745)  \| Command palette → GOVERN → Guard·Policies (AppShell.tsx:148) | — | N | P2 |
| /theguard/settings | apps/web/src/app/(app)/theguard/settings/page.tsx:408 | Sidebar → Govern → Guard → Settings (AppShell.tsx:748, admin-only) | — | N | P2 |
| /theguard/team-memory | apps/web/src/app/(app)/theguard/team-memory/page.tsx:54 | Sidebar → Govern → Guard → Team Memory (AppShell.tsx:746) | — | N | P2 |
| /workflows | apps/web/src/app/(app)/workflows/page.tsx:55 | Sidebar → Build → Agents (AppShell.tsx:921) | — | N | P2 |
| /workflows/[id] | apps/web/src/app/(app)/workflows/[id]/page.tsx:4 | Sidebar → Build → Canvas (AppShell.tsx:928, when id present)  \| Deep-linked from /workflows list | — | N | P2 |

12 additional findings truncated.

Note on truncated rows (all P2, all reachable via a single deep-link path from a parent list, no severity issue):
`/logs` (redirect to /logs/guard), `/observability` (redirect to /logs/observability), `/runs` (redirect to /logs/runs), `/theguard/activity` (redirect to /logs/guard), `/workflows/new`, `/workflows/[id]/runs`, `/workflows/[id]/runs/[run_id]`, `/workflows/[id]/settings`, and 4 dynamic children.

## Sidebar sub-nav (AppShell.tsx)

- Guard sub-nav (lines 744–748): Overview → /theguard · Policies → /theguard/policies · Team Memory → /theguard/team-memory · **Activity → /logs/guard (label ≠ URL)** · Settings → /theguard/settings (adminOnly)
- Secure sub-nav (lines 785–786): Overview → /secure · Findings → /secure/activity
- Logs sub-nav (lines 962–964): Guard → /logs/guard · Runs → /logs/runs · Observability → /logs/observability

## Command palette (AppShell.tsx:140–153)

BUILD: Projects · Canvas · Registry — OBSERVE: Dashboard · Runs — GOVERN: Runtime Governance · Guard·Overview · Guard·Spend · Guard·Policies · Guard·Discovery · Guard·Activity — WORKSPACE: Integrations · Agent ID · Settings·Environments.

## In-page tab bars

| route | file:line | tabs |
|---|---|---|
| /agent-identity | apps/web/src/app/(app)/agent-identity/page.tsx:13-18 | tokens · run_tokens · identities · integrations |
| /settings | apps/web/src/app/(app)/settings/page.tsx:18-23 | credentials · members · preferences · proxy |
| /theguard/policies | apps/web/src/app/(app)/theguard/policies/page.tsx (pageView) | policy-list · coverage |
| /workflows/[id]/runs/[run_id] | apps/web/src/app/(app)/workflows/[id]/runs/[run_id]/page.tsx:51 | summary · trace · ai-trace · files · approvals · cost |
| /logs/guard | apps/web/src/app/(app)/logs/guard/page.tsx:415 | events (Flight Recorder) · sessions · tools · session_reports |
