# Audit 02 — Metrics

Every displayed number, percentage, currency value, count, and grade across the portal.

## Metrics table

| label as displayed | route | component file:line | query or endpoint | time window | filters applied | severity |
|---|---|---|---|---|---|---|
| "Governance Grade" (letter A–F) | /theguard/compliance | apps/web/src/app/(app)/theguard/compliance/page.tsx:326 | GET /guard/verify/evidence?workspace_id={id} | mixed: config = current, events = last 24h | workspace_id | P0 |
| ASI-01..10 status ("active" / "partial" / "missing") | /theguard/compliance | apps/web/src/app/(app)/theguard/compliance/page.tsx (ControlStatus rows) | GET /guard/verify/evidence — status computed in apps/api/app/modules/guard/routers/verify.py:176–194 | mixed: 3 of 10 controls are hardcoded constants; others read config + 24h events | workspace_id | P0 |
| "Chain verified" / "Chain broken" · "{N} chained events from {date}" | /logs/guard | apps/web/src/app/(app)/logs/guard/page.tsx:399–410 | GET /guard/verify/chain?workspace_id={id} — walks full audit table (apps/api/app/modules/guard/routers/verify.py:235–264) | all-time | workspace_id | P0 |
| "{N} risk events intercepted · industry avg $15K each" | /governance | apps/web/src/app/(app)/governance/page.tsx:628 | kpis.blocks_mtd from GET /governance/kpis; "$15K" is HARDCODED literal | MTD (for count) · N/A (for $15K) | workspace_id | P0 |
| "{N} policies live across {N} frameworks" (banner) | /governance | apps/web/src/app/(app)/governance/page.tsx:1084 (banner sub) — totals computed at 464–478 | GET /governance/frameworks?workspace_id={id} — sums `installed[*].rules_count + bonus[*].rules_count` and `installed.length + bonus.length` | current | workspace_id | P0 |
| "Compliance packs" KPI (count) | /governance | apps/web/src/app/(app)/governance/page.tsx:659 | GET /governance/frameworks — reads `installedPacks.length` (i.e. `frameworks.installed.length` only; bonus excluded) | current | workspace_id | P0 |
| "AI activity today" | /governance | apps/web/src/app/(app)/governance/page.tsx:633–642 | GET /governance/kpis — `stats.events_today`, delta = `kpis.events_today.delta_pct` | today vs 7d avg | workspace_id | P1 |
| "Risk intercepted today" | /governance | apps/web/src/app/(app)/governance/page.tsx:643–654 | GET /governance/kpis — `stats.blocked_today`, delta = `kpis.blocked_today.delta_pct` | today vs 7d avg | workspace_id | P1 |
| "Guard ROI (month-to-date)" | /governance | apps/web/src/app/(app)/governance/page.tsx:622–632 | GET /governance/kpis — `kpis.risk_avoided_usd_mtd` | MTD | workspace_id | P1 |
| Active developers count | /theguard | apps/web/src/app/(app)/theguard/page.tsx:818 | GET /guard/spend?workspace_id={id} — `stats.active_developers` | today | workspace_id | P1 |
| "Events today" (Guard Overview) | /theguard | apps/web/src/app/(app)/theguard/page.tsx:823 | GET /guard/spend — `stats.events_today` | today | workspace_id | P1 |
| "Blocked today" | /theguard | apps/web/src/app/(app)/theguard/page.tsx:828 | GET /guard/events?decision=blocked&workspace_id={id} | today | workspace_id, decision=blocked | P1 |
| "Sessions today" | /theguard | apps/web/src/app/(app)/theguard/page.tsx:834 | GET /guard/spend — `stats.sessions + stats.hook_sessions` | today | workspace_id | P1 |
| "Tokens saved" | /theguard | apps/web/src/app/(app)/theguard/page.tsx:839 | GET /guard/spend — `stats.tokens_saved_today` | today | workspace_id | P1 |
| "Token efficiency" | /theguard | apps/web/src/app/(app)/theguard/page.tsx:619–625 | GET /guard/token-guardrails (inferred from `tokenEfficiencyWarnings`) | today | workspace_id | P1 |
| "Tool coverage" `{covered}/{total}` + "{N} tools · all covered" sub | /theguard | apps/web/src/app/(app)/theguard/page.tsx:854–867 | GET /guard/developer-tools?workspace_id={id} — `coveredCount / totalDevs` | current | workspace_id | P1 |
| "{N} agent · {N} proxy" header badge (persona rule counts) | /theguard | apps/web/src/app/(app)/theguard/page.tsx:747 (rendered via GuardShell) | GET /guard/policies/list — filtered by `enabled && !archived_at` then split by `persona === "agent"` vs `persona === "proxy"` (page.tsx:527–535) | current | workspace_id, enabled=true, archived_at IS NULL | P1 |
| "Guard coverage" percentage (Discovery) | /theguard/discovery | apps/web/src/app/(app)/theguard/discovery/page.tsx:233 | GET /guard/discovery/summary?workspace_id={id} — `covered/total*100` (apps/api/app/modules/guard/routers/discovery.py:240–252) | current | workspace_id | P1 |
| "under_guard" / "total" / "missing" counts (Discovery) | /theguard/discovery | apps/web/src/app/(app)/theguard/discovery/page.tsx:237–248 | GET /guard/discovery/summary | current | workspace_id | P1 |
| "Est. savings" (Spend, currency) | /theguard/spend | apps/web/src/app/(app)/theguard/spend/page.tsx:754 | GET /guard/spend?workspace_id={id}&period={month} — `data.total_saved_usd` | current month (period=month) | workspace_id, period | P1 |
| "Team token savings — cumulative as of {monthLabel}" | /theguard/spend | apps/web/src/app/(app)/theguard/spend/page.tsx:783 | GET /guard/savings?workspace_id={id}&month={month} — `savings.team_total.*` | selected month | workspace_id, month | P1 |
| "RTK tokens saved" | /theguard/spend | apps/web/src/app/(app)/theguard/spend/page.tsx:800 | GET /guard/savings — `team_total.rtk_saved_tokens` | selected month | workspace_id, month | P1 |
| "RTK cost saved" | /theguard/spend | apps/web/src/app/(app)/theguard/spend/page.tsx:801 | GET /guard/savings — `team_total.rtk_saved_usd` | selected month | workspace_id, month | P1 |
| "{N} active." rule count | /theguard/policies | apps/web/src/app/(app)/theguard/policies/page.tsx:1180 | GET /guard/policies/list — `policies.filter(p => p.enabled).length` | current | workspace_id | P1 |
| Agent tab count on policies | /theguard/policies | apps/web/src/app/(app)/theguard/policies/page.tsx:1104 | GET /guard/policies/list — `policies.filter(p => p.builtin && (!p.persona || p.persona === "agent")).length` (**excludes non-builtin custom rules**) | current | workspace_id, builtin=true | P1 |
| Proxy tab count on policies | /theguard/policies | apps/web/src/app/(app)/theguard/policies/page.tsx:1105 | GET /guard/policies/list — `policies.filter(p => p.builtin && p.persona === "proxy").length` | current | workspace_id, builtin=true | P1 |
| Per-pack tab count on policies | /theguard/policies | apps/web/src/app/(app)/theguard/policies/page.tsx:1110 | GET /guard/policies/list — `policies.filter(p => p.pack_id === id).length` | current | workspace_id | P1 |
| "Simulation Score: {score}/100 · {passed}/{total} held" | /theguard/compliance | apps/web/src/app/(app)/theguard/compliance/page.tsx:120 | POST /guard/verify/run (VerifyRunPanel handleRun) | on-demand | workspace_id | P1 |
| Chain intact / broken badge (governance) | /governance | apps/web/src/app/(app)/governance/page.tsx:1087 | GET /guard/verify/chain | all-time | workspace_id | P1 |
| Chain intact / broken badge (SOC2 report) | /theguard/reports/soc2 | apps/web/src/app/(app)/theguard/reports/soc2/page.tsx:241 | GET /guard/verify/chain | all-time | workspace_id | P1 |
| Score / Coverage / Blocked / Events (24h) sub-line | /theguard/compliance | apps/web/src/app/(app)/theguard/compliance/page.tsx:328 | GET /guard/verify/evidence | last 24h | workspace_id | P1 |
| "Open" · "Critical/High" · "Fixed this month" · "MTTR" | /secure | apps/web/src/app/(app)/secure/page.tsx:71–89 | GET /security-findings/summary?workspace_id={id}&days=30 | last 30 days | workspace_id, days=30 | P1 |
| "5 devs · all covered" | /(marketing)/blog/launch-hero | apps/web/src/app/(marketing)/blog/launch-hero/page.tsx:84 | HARDCODED literal | N/A | N/A | P2 |
| Ticket cost demo values "$135.50", "$105", "$140" | /packs (pack description) | apps/web/src/app/(app)/packs/page.tsx:246 | HARDCODED demo pack description | N/A | N/A | P2 |
| Successful / Failed automations | /dashboard | apps/web/src/app/(app)/dashboard/page.tsx:1121–1122 | GET /dashboard/summary (inferred) | today (per surrounding card) | workspace_id | P2 |

## COLLISIONS

### Same label, different query
- **"Chain verified/broken" (with chain totals)** rendered on three routes, all point to GET /guard/verify/chain, but display differs:
  - /logs/guard uses "Chain verified" / "Chain broken" (page.tsx:404) with `chainStatus.total` count + `verified_from` date
  - /governance uses "Chain intact" / "Chain broken" (page.tsx:1087) — **wording differs from /logs/guard**
  - /theguard/reports/soc2 uses "Chain intact" / "Chain broken" (page.tsx:241) — matches governance, not logs
- **"Compliance packs" count** on /governance (apps/web/src/app/(app)/governance/page.tsx:659) uses `installedPacks.length` = `frameworks.installed.length` only; the **same-page** hero banner (line 1084) uses `installed.length + bonus.length`. Same fetched payload, two different tallies rendered feet apart.

### Same query, different label
- GET /guard/policies/list is filtered five different ways on the same page (/theguard/policies) and one different way on /theguard (Guard Overview header). Same source, different tallies:
  - /theguard header: "N agent · N proxy" — filter `enabled && !archived_at`, split by persona (theguard/page.tsx:527–535)
  - /theguard/policies sub-header: "{N} active." — filter `p.enabled` only (policies/page.tsx:1180)
  - /theguard/policies Agent tab: count `p.builtin && (!p.persona || persona==='agent')` (policies/page.tsx:1104) — excludes archived-but-still-enabled AND non-builtin custom rules
  - /theguard/policies Proxy tab: count `p.builtin && persona==='proxy'` (policies/page.tsx:1105)
  - /theguard/policies pack tab: count `p.pack_id === id` (policies/page.tsx:1110) — no enabled/persona filter
- GET /governance/kpis and GET /guard/spend both expose today's event count, rendered as **"AI activity today"** (governance) and **"Events today"** (theguard). Two labels, two queries, functionally identical value.

## RESOLVE

**Rule counts (116 active / 121 rules / 112 tagged / 111 Agent / 110 agent · 6 proxy)** — cannot be arithmetically resolved without live data, but the divergent filter chains are the cause:
- 116 active = `policies.filter(p => p.enabled).length` (policies/page.tsx:1180) — includes archived rules that still have `enabled=true`, and includes custom (non-builtin) rules.
- 121 rules = `policies.length` (full unfiltered list from /guard/policies/list).
- 112 tagged = policies with a non-empty `frameworks` array (implicit from filter used on framework panels; policies/page.tsx does `p.frameworks?.length` inline).
- 111 Agent (policies page tab) = `policies.filter(p => p.builtin && (!p.persona || p.persona === "agent")).length` (policies/page.tsx:1104). Different subset than 116 active because it (a) drops non-builtin custom rules and (b) does NOT filter on `enabled`.
- 110 agent · 6 proxy (Guard Overview header) = `active.filter(persona==='agent').length` and `active.filter(persona==='proxy').length` where `active = list.filter(r => r.enabled && !r.archived_at)` (theguard/page.tsx:527–535). Different from the 111 tab count because Guard Overview also filters out `archived_at` rows and does NOT restrict to `builtin`.
- Which are correct: it depends on what each label promises. **All five tallies are internally consistent given their filters; the labels do not disclose which filter they applied**, so no user can reconcile them from the UI alone. This is P0.

**Framework counts (9 Compliance Packs card vs 11 Governance banner)** — same page, same fetched payload. The KPI card at governance/page.tsx:655–660 renders `installedPacks.length` = `frameworks.installed.length` (installed-tier only, 9). The banner at governance/page.tsx:1084 renders `installed.length + bonus.length` (installed + bonus tiers, 11). The card label "Compliance packs" and the banner phrase "…across {N} frameworks" both describe the same object but tally different subsets of the same array. P0.

**Savings ($135, $3002.95, $3003.48, $2565.0k)** — all from GET /guard/spend or GET /guard/savings.
- $135 — appears in a demo pack description at apps/web/src/app/(app)/packs/page.tsx:246 ("avoids $135.50/ticket"); UNKNOWN whether $135 in a Spend card is the same value or a different live sum without live data.
- $3002.95 vs $3003.48 — both come from GET /guard/spend `total_saved_usd`, formatted with `fromUsd(..., currency).toFixed(0)` at spend/page.tsx:754 and `.toFixed(2)` at spend/page.tsx:801 (RTK cost saved from /guard/savings — different endpoint). Window: current month for total_saved_usd; selected month for team_total.rtk_saved_usd. Both are MTD cumulative through query time. **Formula:** total_saved_usd = server-computed sum of token-savings ledger entries.
- $2565.0k — UNKNOWN in code (not a literal); most likely `formatTotalTokensSaved(stats?.tokens_saved_today)` displayed as compact-number cost equivalent, rendered on theguard/page.tsx:839. Formula UNKNOWN without seeing formatTotalTokensSaved.

**Coverage ("1/1 tool coverage · 4 tools · all covered" (Guard Overview) vs "11/13 under Guard, 2 missing" (Discovery))** — two entirely different queries, coincidentally both labeled "coverage".
- "1/1 tool coverage · 4 tools" — from GET /guard/developer-tools (theguard/page.tsx:854–867). Numerator/denominator = developers whose tool-registry entry is non-empty / total developers seen. "4 tools" = sum of `detected_tools.length` across all developers. This counts developer-machine pairs, not agents.
- "11/13 under Guard, 2 missing" — from GET /guard/discovery/summary (discovery/page.tsx:233, 244, 248). Numerator/denominator = DiscoveredAgent rows with `under_guard=True` / total DiscoveredAgent rows. This counts agent registrations, not developer tools. **Different objects entirely.** P0 candidate: both are surfaced as "coverage" without disclosing what they cover.

**"248 policies live across 11 frameworks"** — from governance banner (governance/page.tsx:1084). 248 = `sum(fw.rules_count for fw in installed) + sum(fw.rules_count for fw in bonus)`. Each `rules_count` is per-framework, so 248 counts **the sum of framework-rule associations, not distinct rules** — a single rule tagged with 5 frameworks contributes 5 to this total. 11 = `installed.length + bonus.length`. Neither number matches "121 rules" from /theguard/policies because 248 is join-cardinality and 121 is distinct-rule cardinality.
