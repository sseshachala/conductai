# E1 — The $140 Ticket

**Runtime:** 3:00 · **Series:** Conduct Demo Series · **Bible:** `00-series-bible.md`

**Frame:** PH's AI stack (Sierra + ChatGPT) can already fix the ticket. The ceiling isn't capability — it's authority. E1 shows Guard turn a $140 onsite dispatch into a 15-cent auto-remediation with a human 1-click, on one ticket, with a receipt.

---

## 0:00 — 0:20 · Cold open

**Visual:** Slow zoom on a PH support console. A ticket sits open: `#48213 · Northwind Outfitters · Store 7, Boulder, CO · POS laptop won't boot after Windows update`.

**Sarah (VO):**
> "This ticket is going to cost me a hundred and forty dollars. I have four million like it a year. And the AI already knows the fix — it just isn't allowed to run it."

**Cut to:** Sarah at her desk, mid-forties, tired. Sierra AI panel open on her second monitor.

---

## 0:20 — 0:50 · The pain in their words

**Sarah (to camera):**
> "We bought Sierra last year. ChatGPT the year before. Both work. Sierra reads the boot log, spots the corrupt BCD entry from last night's patch, and knows the fix — one script, thirty seconds, done.
>
> Onsite tech to Store 7 is a hundred and forty bucks. A remote screenshare with a human is thirty-five. AI running the script itself is cents.
>
> But I can't let Sierra just… write to Northwind's POS terminal. If it bricks the register at 6am on Black Friday, I'm on a call with their CIO. So every fix routes through a human, and the AI tier is worth nothing."

**Lower third:** `$140 · $35 · ¢¢ — PH's three tiers, one gate.`

---

## 0:50 — 1:20 · Guard capability

**Cut:** Marcus at a whiteboard. Two boxes: `Sierra AI` and `remediation.ph.support`. Between them, a diamond labeled **Guard**.

**Marcus:**
> "Sierra doesn't need to be smarter. It needs a place to ask 'am I allowed to run this action, on this device, for this customer, right now.'
>
> Guard is that place. Two ways in: Sierra calls `guard_check` before it fires — cooperative. Or if it doesn't, the remediation API sits behind our proxy — same rule, hard boundary. Either way, the answer is the same, and the receipt is the same."

**Lower third:** `Capability ≠ Authority. Guard is where authority lives.`

---

## 1:20 — 2:15 · Live UI walkthrough

**Screen:** Sierra AI console. Ticket #48213 loaded. Sierra's diagnosis panel:

```
Diagnosis: BCD boot entry corrupted (KB5041580 rollback conflict)
Proposed fix: run remediation.script("bcd_repair") on store7-pos-04
Confidence: 0.94
```

Sierra proposes: `remediation.run(script="bcd_repair", target="store7-pos-04", tenant="northwind")`.

**Beat 1 (1:20-1:35):** `guard_check` fires. Response panel drops in:

```
BLOCKED · ph.remediation.pos_write_requires_approval
Northwind entitlement: retail-hardened — no unattended writes on POS-class devices.
Suggest: remediation.propose_for_review (queues for 1-click human approval)
Receipt: cost_avoided_usd = 139.85 (vs onsite dispatch)
```

**Beat 2 (1:35-1:55):** Sierra re-plans. New action: `remediation.propose_for_review` — script + diagnosis packaged, queued to on-call tech. Second `guard_check` — `ALLOWED`. Tech's phone buzzes: **"Approve BCD repair on store7-pos-04?"** → tap **Approve**. Script runs. Register boots. Ticket closes. Total spend: $0.15 compute + 30 seconds of a human.

**Beat 3 (1:55-2:15):** Cut to Guard's `/theguard/activity` feed. Two rows appear:

| Time  | Actor      | Intent                        | Tenant     | Decision | Cost avoided |
| ----- | ---------- | ----------------------------- | ---------- | -------- | ------------ |
| 14:07 | sierra-ai  | remediation.run               | northwind  | BLOCKED  | $139.85      |
| 14:07 | sierra-ai  | remediation.propose_for_review | northwind  | ALLOWED  | —            |

**Marcus (VO, over the row):**
> "Sierra tried. Guard said no, and told it what to try instead. One row. One receipt."

---

## 2:15 — 2:45 · Dashboard KPI payoff

**Cut:** Sarah's screen. `/theguard/spend` — a single card at the top: **Cost Avoided · Today**.

Card fills: **$139.85** → animates to **$1,458.00** → **$18,791.00** as the day rolls.

**Sarah (to camera):**
> "This is one ticket. This is one day. Multiply by four million tickets a year, and the AI tier is finally worth what we paid for it — because it's finally allowed to work."

**Lower third:** `PH, this quarter: $2.1M avoided · 14,000 receipts · zero bricked registers.`

---

## 2:45 — 3:00 · Next-episode tease

**Cut:** Sarah's inbox. New email: `Northwind Outfitters — IT Compliance <compliance@northwind.com>`. Subject: **"Can we see the log?"**

**Sarah (raises eyebrow):**
> "…and now they want the audit trail."

**Card:** `Next: E2 — The Customer Asks for the Log.`

---

## Production notes

- **Screens:** Sierra console is a mock (Figma export). Guard `/theguard/activity` is real shipped UI. The **Cost Avoided · Today** card on `/theguard/spend` is NOT built yet — either add it before shoot or mock it as an overlay for E1.
- **Data:** three tenants in `meridian-dispatch.yaml` seed — Northwind (retail-hardened, human approval on POS writes), Contoso (office fleet, auto-remediation allowed for boot/driver class), Fabrikam (dev laptops, full self-serve).
- **Voices:** Sarah warm/tired, Marcus dry/technical. No music under Sarah beats — silence sells it.
- **Cost card animation:** three-step count-up, ~1s each. Real numbers from receipts table, not mocked.
- **One thing to NOT show:** the policy YAML itself. Bible rule — visual is the receipt, not the config.

## Economics reference (for lower-third accuracy)

| Tier                          | Per-ticket cost | Who does the work                          |
| ----------------------------- | --------------- | ------------------------------------------ |
| Onsite dispatch               | ~$140           | Tech drives to store, 1-2 hr window        |
| Remote screenshare (human)    | ~$35            | Agent on chat/screenshare, 15-20 min       |
| AI auto-remediation           | ~$0.15          | Script runs unattended, seconds            |
| AI + 1-click human approval   | ~$0.50          | Script queued, human taps approve, seconds |

Guard's job: route each ticket to the *cheapest* tier the customer's contract actually allows.
