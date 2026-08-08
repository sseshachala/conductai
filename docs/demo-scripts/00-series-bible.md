# Conduct Demo Series — bible

One enterprise, five episodes, one Guard. Each episode ends on a hook into the next.

## Cast

- **Meridian Devices** — fictional laptop vendor + support org (HP stand-in)
- **Sarah** — Sr Director, Customer Support & Services Delivery IT (buyer)
- **Marcus** — VP Engineering (champion)
- **Diana** — Compliance / GRC lead (beneficiary)
- **Sierra AI + ChatGPT** — Meridian's AI stack for ticket resolution
- **Northwind Outfitters** — SMB customer, 340 laptops, depot-tier contract (E1 protagonist)

## Unit economics (frame for the whole series)

| Resolution path | Cost per ticket |
|---|---|
| On-site dispatch | $140 |
| Remote session | $30-40 |
| AI-only | cents |

Meridian has already bought Sierra + ChatGPT capability. They can't scale the AI tier because they can't govern consequential actions per-customer. Guard is the ceiling remover.

## Season arc — Day 0 → Day 30

| # | Title | Runtime | Ends on |
|---|---|---|---|
| **E1** | The $140 Ticket | 3:00 | Sarah sees the first receipt: $135.50 saved on one ticket. Cue: "multiply by four million." |
| **E2** | The Customer Asks for the Log | 3:30 | Northwind's IT team requests audit trail. Diana exports per-tenant hash-chained receipts in one click. |
| **E3** | Fix This Code | 3:00 | News event breaks; two rules push overnight. Sarah's phone stops ringing. (Adapts 984) |
| **E4** | The Audit Cabinet | 3:00 | SOC 2 CC7.3 closed from operations, not a PDF. Deloitte call moves up 3 weeks. (Adapts 982) |
| **E5** | The Board Slide | 2:30 | One slide. Coverage 92%, MTTR -78%, dollars saved by policy. Season close. |

## Episode template

1. Cold open — a human moment (0:00-0:20)
2. The pain in their words (0:20-0:50)
3. Guard capability that solves it (0:50-1:20)
4. Live UI walkthrough (1:20-2:15)
5. Dashboard KPI payoff (2:15-2:45)
6. Next-episode tease (2:45-3:00)

## E1 spec — locked

**Aha:** entitlement-aware dispatch. Sierra wants to dispatch a technician to Northwind Store 7 in Boulder ($140). Guard checks Northwind's contract → depot-tier only → blocks dispatch, suggests mail-in RMA. Sierra reroutes. Cost drops to $4.50 shipping.

**Guard mapping — two surfaces:**
- **MCP (cooperative, primary):** Sierra calls `guard_check(intent="dispatch.rma", tenant="northwind", cost=140)` before firing the tool. Guard returns BLOCKED + suggests `rma.mail_in`. Sierra retries.
- **Proxy (hard boundary, fallback):** `dispatch.meridian.com/api/rma` sits behind Conduct proxy. Same policy fires at network layer if MCP check is skipped.

**Policy shape:**
```yaml
# meridian.dispatch.entitlement_check
when:
  intent: dispatch.rma
require:
  tenant.entitlement_tier: onsite
on_deny:
  action: block
  suggest: rma.mail_in
  reason: "{{tenant.name}} entitlement is {{tenant.entitlement_tier}} — dispatch requires onsite"
  receipt:
    cost_avoided_usd: 135.50
```

**What E1 needs to work:**
1. Tenant metadata in Guard (nightly CRM sync; seed 3 tenants for demo)
2. Cost model: `dispatch.rma = $140`, `rma.mail_in = $4.50` (constants in the pack)
3. Small UI add: `receipt.cost_avoided_usd` column on `/theguard/activity` + rollup card on `/theguard/reports`

**Deliverables when we write E1:**
1. Full 3-minute script (this file's E1 spec, expanded to beat-by-beat)
2. `meridian-dispatch.yaml` policy pack (seed data + rules, runnable)
3. GH issue for the receipt column + cost-avoided rollup card

## Not doing

- Real HP branding — series stays fictional through E1 minimum
- Regulated verticals for E1 — SMB/mid-market first for simplicity
- New Guard primitives — everything runs on shipped code
