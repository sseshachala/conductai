# Audit 03 - Computed vs Hardcoded

Metrics, grades, status badges, and deltas NOT derived from a live query.

## Table

| value | route | file:line | source (query / constant / mock / static map) | severity |
|---|---|---|---|---|
| ASI-03 status = "active" (unconditional) | /theguard/compliance | apps/api/app/modules/guard/routers/verify.py:180-181 | HARDCODED constant. `if asi in ("ASI-03", "ASI-04"): return "active"` regardless of any live data. | P0 |
| ASI-04 status = "active" (unconditional) | /theguard/compliance | apps/api/app/modules/guard/routers/verify.py:180-181 | HARDCODED constant. Same branch as ASI-03. | P0 |
| ASI-06 status = derived from guard_active AND events_24h > 0 | /theguard/compliance | apps/api/app/modules/guard/routers/verify.py:182-185 | Partially computed. Does not read hash-chain integrity state; can return "active" even when GET /guard/verify/chain reports valid=False. | P0 |
| ASI-07 status = "partial" (unconditional) | /theguard/compliance | apps/api/app/modules/guard/routers/verify.py:186-187 | HARDCODED constant. Ignores whether any agent_role_id or member tokens actually exist. | P0 |
| ASI-10 status = "partial" (unconditional) | /theguard/compliance | apps/api/app/modules/guard/routers/verify.py:192-193 | HARDCODED constant. Ignores actual session scanning / violations_count data. | P0 |
| industry avg dollar-15K each | /governance | apps/web/src/app/(app)/governance/page.tsx:628 | HARDCODED literal string in the KpiCard sub slot. Not fetched, not configurable. | P0 |
| Score weightings +30/+15/+5 for enforcement_mode etc. | /theguard/compliance (Grade) | apps/api/app/modules/guard/routers/verify.py:145-172 | HARDCODED weights. Grade is computed live from Guard config, but the weights themselves are constants. | P1 |
| ASI-01/02/05/06/08/09 base status branches | /theguard/compliance | apps/api/app/modules/guard/routers/verify.py:178-191 | STATIC MAP dispatched by ASI ID. Map itself is hardcoded; leaf status is (partially) derived from a small set of config booleans. | P1 |
| Fictional Meridian Devices support description with dollar-135.50 / dollar-105 | /packs (demo pack description) | apps/web/src/app/(app)/packs/page.tsx:246 | HARDCODED demo pack description string in a demo pack seed. | P2 |
| Rules sync to every developer machine within 60 seconds | /theguard/policies | apps/web/src/app/(app)/theguard/policies/page.tsx:1175 | HARDCODED literal in copy. Not derived from a config value. | P2 |
| 5 devs all covered | /(marketing)/blog/launch-hero | apps/web/src/app/(marketing)/blog/launch-hero/page.tsx:84 | HARDCODED literal in a marketing hero screenshot, not live data. | P2 |
| Average cost of a prod incident dollar-15K to dollar-50K | /public/mockups/guard-landing.html | apps/web/public/mockups/guard-landing.html:798 | HARDCODED literal in a mockup HTML file. Same dollar-15K referenced in the live governance page. | P2 |
| Grade thresholds A>=85, B>=65, C>=45, D>=25, F<25 | /theguard/compliance (indirect) | apps/api/app/modules/guard/routers/verify.py:53-58 (_GRADES tuple) | HARDCODED constant tuple. | P2 |
| GRADE_BG/COLOR/BD and VERDICT_BG/COLOR/BD color maps | /theguard/compliance | apps/web/src/app/(app)/theguard/compliance/page.tsx:50-60 | STATIC MAPS. Cosmetic. | P2 |
| TOOL_LABEL display-name map (Claude/Cursor/Windsurf/etc.) | /theguard | apps/web/src/app/(app)/theguard/page.tsx:645-648 | STATIC MAP. Any tool key not in the map falls through to raw slug. Cosmetic. | P2 |

## Explicit answers

### 1. Is Governance Grade computed? From what inputs, with what formula?

Yes, computed. Endpoint: GET /guard/verify/evidence at apps/api/app/modules/guard/routers/verify.py:100+. Grade letter mapping: _GRADES = [(85,"A"),(65,"B"),(45,"C"),(25,"D"),(0,"F")] (verify.py:53-58), applied in _grade(score) (verify.py:60-64).

Score assembly (verify.py:145-172):

| Component | Points | Read from |
|---|---|---|
| enforcement_mode = "block" | +30 | GuardConfig.enforcement_mode |
| enforcement_mode = "warn" | +15 | GuardConfig.enforcement_mode |
| enforcement_mode = "audit" | +5 | GuardConfig.enforcement_mode |
| fail_mode = "fail_closed" | +15 | GuardConfig.fail_mode |
| deny_on_error = true | +10 | GuardConfig.deny_on_error |
| signing key present | +15 | GuardSigningKey row exists for workspace |
| policy_count >= 5 | +20 | count of active SkillPack policies |
| 0 < policy_count < 5 | +10 | same |
| events_24h > 0 | +10 | count of GuardAuditEvent with ts >= now - 24h |

Grade = _grade(sum_of_the_above). Max score = 100. Coverage % = round(active_controls_count / 10 * 100) where active_controls_count = sum(1 for c in controls if c.status == "active") (verify.py:207-208). Passed = grade in ("A","B").

### 2. Is OWASP ASI-01..ASI-10 status computed per control, or a static map?

Static per-ASI dispatch (verify.py:176-194) with mixed computation per branch:

| ASI | Source | Verdict |
|---|---|---|
| ASI-01 Prompt Injection | "active" if guard_active else "missing" | partially computed (one boolean) |
| ASI-02 Insecure Tool Use | "active" if guard_active else "missing" | partially computed (same boolean) |
| ASI-03 Excessive Agency | "active" unconditional | HARDCODED |
| ASI-04 Unauthorized Escalation | "active" unconditional | HARDCODED |
| ASI-05 Trust Boundary Violation | "active" if guard_active else "missing" | partially computed (same boolean) |
| ASI-06 Insufficient Logging | "active" if guard_active AND events_24h > 0 else "partial" if guard_active else "missing" | partially computed |
| ASI-07 Insecure Identity | "partial" unconditional | HARDCODED |
| ASI-08 Policy Bypass | "active" if fail_mode == "fail_closed" else "partial" | partially computed |
| ASI-09 Supply Chain Integrity | "active" if signing_key else "missing" | partially computed |
| ASI-10 Behavioral Anomaly | "partial" unconditional | HARDCODED |

Four ASIs (ASI-03, ASI-04, ASI-07, ASI-10) are hardcoded literals. ASI-01/02/05 all key off the same guard_active boolean, so they always agree.

### 3. Does ASI-06 (Insufficient Logging) read actual hash-chain state?

No. ASI-06 status source: verify.py:182-185. It reads guard_active (config) and events_24h (count of audit events in the last 24h). It does not query the hash chain, does not read GuardChainState, and does not call the chain-verification path.

Chain state comes from a completely separate endpoint: GET /guard/verify/chain (verify.py:235-264). That endpoint walks the full GuardAuditEvent table and recomputes SHA-256 per row.

The banner "Chain broken - 25167 chained events from 7/6/2026" on /logs/guard (apps/web/src/app/(app)/logs/guard/page.tsx:404-407) reads chainStatus.valid from GET /guard/verify/chain. Meanwhile ASI-06 on /theguard/compliance (apps/web/src/app/(app)/theguard/compliance/page.tsx:326) reads status from GET /guard/verify/evidence with the formula above.

Result: the two endpoints read different data. ASI-06 can display "active - SHA-256 hash chain" while GET /guard/verify/chain returns valid=False. Two surfaces of the same product disagree about the same underlying fact. This is a P0 contradiction and is the direct cause of the reported symptom.

### 4. Where does the dollar-15K per-incident figure originate?

Hardcoded literal string. Single canonical source: apps/web/src/app/(app)/governance/page.tsx:628 renders the template literal `${fmtInt(kpis.blocks_mtd)} risk events intercepted - industry avg $15K each`. The blocks_mtd value is live (from GET /governance/kpis); the $15K string is a hardcoded literal in the JSX template. Not fetched from config, not tenant-configurable, not stored in the DB. A second occurrence exists in a static mockup at apps/web/public/mockups/guard-landing.html:798 ($15K-$50K), but that HTML file is not served as a live surface.

### 5. Delta calculation for AI ACTIVITY TODAY 423 (down 98%) and RISK INTERCEPTED TODAY 6 (down 100%)

Formula (server-side, apps/api/app/routers/governance.py:470-476, _kpi()):

    if avg_7d <= 0:
        return KpiValue(value=value, avg_7d=None, delta_pct=None)
    delta = round((value - avg_7d) / avg_7d * 100)

Rendering (client, apps/web/src/app/(app)/governance/page.tsx:633-654, KpiCard delta prop): delta is passed straight from kpis.events_today.delta_pct / kpis.blocked_today.delta_pct.

Arithmetic check with the stated inputs:

- 423 vs 7d avg 516 -> (423 - 516) / 516 * 100 = -18.02 -> round() = -18%, not -98%. If the UI displays "down 98%" with these inputs, either (a) avg_7d was near 8.5 (making delta about 4876%, still not 98) which is implausible, or (b) the value shown for the input is not the value actually passed to the formula, or (c) the shown delta is stale relative to the shown value. The formula is arithmetically correct; the on-screen delta cannot be reproduced from the on-screen inputs. P0.
- 6 vs 7d avg 14.7 -> (6 - 14.7) / 14.7 * 100 = -59.18 -> round() = -59%, not -100%. -100% would require value = 0. Cannot be reproduced. P0.

Both delta claims fail an arithmetic self-consistency check against the values displayed alongside them.
