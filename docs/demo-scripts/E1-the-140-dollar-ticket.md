# E1 — The $140 Ticket

**Runtime:** 3:00 · **Series:** Conduct Demo Series · **Bible:** `00-series-bible.md`

**Frame:** Meridian's AI stack (Sierra + ChatGPT) can already resolve tickets. The ceiling isn't capability — it's authority. E1 shows Guard turn one $140 dispatch into a $4.50 mail-in, on one ticket, with a receipt.

---

## 0:00 — 0:20 · Cold open

**Visual:** Slow zoom on a Meridian support console. A ticket sits open: `#48213 · Northwind Outfitters · Store 7, Boulder, CO · Laptop won't boot`.

**Sarah (VO):**
> "This ticket is going to cost me a hundred and forty dollars. I have four million like it a year. And the AI is already smart enough to close it — it just isn't allowed to."

**Cut to:** Sarah at her desk, mid-forties, tired. Sierra AI panel open on her second monitor.

---

## 0:20 — 0:50 · The pain in their words

**Sarah (to camera):**
> "We bought Sierra last year. We bought ChatGPT the year before. Both work. On-site tech to Northwind's store is a hundred and forty bucks. A remote session is thirty-five. AI-only is cents.
>
> But I can't let Sierra fire a dispatch. Northwind bought depot-tier — mail-in only. If Sierra sends a truck, we eat the cost. If it sends the wrong customer a truck, I'm on a call with their CIO on Monday.
>
> So we route every ticket through a human. Which means the AI tier is worth… nothing."

**Lower third:** `$140 · $35 · ¢¢ — Meridian's three tiers, one gate.`

---

## 0:50 — 1:20 · Guard capability

**Cut:** Marcus at a whiteboard. Two boxes: `Sierra AI` and `dispatch.meridian.com`. Between them, a diamond labeled **Guard**.

**Marcus:**
> "Sierra doesn't need to be smarter. It needs a place to ask 'am I allowed to do this, for this customer, right now.'
>
> Guard is that place. Two ways in: Sierra can call `guard_check` before it fires — cooperative. Or if it doesn't, the dispatch API sits behind our proxy — same rule, hard boundary. Either way, the answer is the same, and the receipt is the same."

**Lower third:** `Capability ≠ Authority. Guard is where authority lives.`

---

## 1:20 — 2:15 · Live UI walkthrough

**Screen:** Sierra AI console. Ticket #48213 loaded. Sierra proposes: `dispatch.rma → Store 7, Boulder`.

**Beat 1 (1:20-1:35):** Sierra fires `guard_check(intent="dispatch.rma", tenant="northwind", cost=140)`. Response panel drops in:

```
BLOCKED · meridian.dispatch.entitlement_check
Northwind Outfitters entitlement is depot — dispatch requires onsite.
Suggest: rma.mail_in
Receipt: cost_avoided_usd = 135.50
```

**Beat 2 (1:35-1:55):** Sierra re-plans. New action: `rma.mail_in → prepaid label to Store 7`. Second `guard_check` — this time `ALLOWED`. Ticket closes. Total spend: $4.50 shipping.

**Beat 3 (1:55-2:15):** Cut to Guard's `/theguard/activity` feed. Row appears:

| Time  | Actor      | Intent          | Tenant     | Decision | Cost avoided |
| ----- | ---------- | --------------- | ---------- | -------- | ------------ |
| 14:07 | sierra-ai  | dispatch.rma    | northwind  | BLOCKED  | $135.50      |
| 14:07 | sierra-ai  | rma.mail_in     | northwind  | ALLOWED  | —            |

**Marcus (VO, over the row):**
> "Sierra tried. Guard said no, and told it what to try instead. One row. One receipt."

---

## 2:15 — 2:45 · Dashboard KPI payoff

**Cut:** Sarah's screen. `/theguard/reports` — a single card: **Cost Avoided · Today**.

Card fills: **$135.50** → animates to **$1,417.00** → **$18,244.00** as the day rolls.

**Sarah (to camera):**
> "This is one ticket. This is one day. Multiply by four million tickets a year, and the AI tier is finally worth what we paid for it."

**Lower third:** `Meridian, this quarter: $2.1M avoided · 14,000 receipts · zero wrong dispatches.`

---

## 2:45 — 3:00 · Next-episode tease

**Cut:** Sarah's inbox. New email: `Northwind Outfitters — IT Compliance <compliance@northwind.com>`. Subject: **"Can we see the log?"**

**Sarah (raises eyebrow):**
> "…and now they want the audit trail."

**Card:** `Next: E2 — The Customer Asks for the Log.`

---

## Production notes

- **Screens:** Sierra console is a mock (Figma export). Guard `/theguard/activity` + `/theguard/reports` are real shipped UI.
- **Data:** pull from `meridian-dispatch.yaml` seed tenants (Northwind = depot, Contoso = onsite, Fabrikam = self-serve).
- **Voices:** Sarah warm/tired, Marcus dry/technical. No music under Sarah beats — silence sells it.
- **Cost card animation:** three-step count-up, ~1s each. Real numbers from receipts table, not mocked.
- **One thing to NOT show:** the policy YAML itself. Bible rule — visual is the receipt, not the config.
