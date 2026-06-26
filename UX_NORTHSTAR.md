# UX Northstar — Conduct

> **Purpose:** A constraint document that names the journey, the kill list, and the decisions for Conduct's UX as of mid-2026. Not a manifesto. Not a vision essay. Everything we ship after this week references this doc.
>
> **Timebox:** 1 week. Ships day 7 even if incomplete.
>
> **What this doc is:** journey + surface map + primitives + decision log. The screens we keep, redesign, merge, or kill — and why.
>
> **What this doc is not:** pixel-perfect design (after this), brand or visual identity (separate track), a re-opening of positioning (v3 is the input).

---

## Positioning (input, not a question)

> **Conduct is a Guard-first AI governance platform** — policy, compliance, spend, and audit for AI usage at work — **with team automation playbooks layered on top, scoped to compliance, security, and engineering workflows.**

Guard is the spine — not a module, not a tab. Every playbook, every run, every developer's Claude Code / Cursor / Copilot / agent / MCP call passes through Guard.

**Buyer order:** security / compliance lead first, engineering lead second, individual developer third.

**Audience reality:** B2B users inside companies. SSO, RBAC, procurement, audit obligations, shared workspaces. We borrow patterns from Linear, Vercel, Datadog, GitHub — never from Lovable, v0, ChatGPT, Claude.ai.

---

## Hard constraints (do not relax mid-week)

1. **Guard-on-every-rung.** Guard appears inline on entry, build, run, govern, and audit. Not a sidebar item.
2. **Three automation lanes only:** compliance, security, engineering. No generic "team automations" copy.
3. **No rip-and-replace.** Surface map columns are keep / redesign / merge / kill — kill is the exception. Redesigns ship as a new route or behind a flag alongside the old one until parity. No forced cutover.
4. **B2B not consumer.** No "Let's get started!" voice. No blank-slate chat prompts. Intent-driven *within the user's company context.* Copy assumes auditors will read it.
5. **Constraint doc, not aspiration doc.** Kill list + decisions + journey.

---

## Personas (buyer-weighted)

### 1. Security / compliance lead — **primary buyer**

**Titles:** CISO, AppSec lead, GRC manager, Director of Security.
**Job to be done:** prove AI usage inside the company is governed — to the board, to auditors, to enterprise customers asking for evidence.
**Day-to-day:** reviews policies, signs off on tool rollouts, owns SOC 2 / ISO evidence, fields questions about Copilot / Cursor / Claude Code usage from Legal and Risk.
**Frustration today:** Copilot and Cursor are already in the building; there's no enforcement layer; audit log is the developer's terminal history.
**What they need from Conduct in 30 seconds:** *"Here's every AI call in your org. Here's what was blocked. Here's the evidence."*
**Trust signals they look for:** policy versioning, audit trail with immutable timestamps, SSO, role separation, compliance pack downloads.

### 2. Engineering lead — **secondary buyer, drives expansion**

**Titles:** VP Engineering, Director of Platform, Staff Eng running developer productivity.
**Job to be done:** ship more without losing oversight; turn one engineer's working playbook into the team's automation; control spend on agentic runs.
**Day-to-day:** approves tool budgets, owns CI/CD reliability, runs the AI-adoption committee, sees Claude Code bills climbing.
**Frustration today:** every team is automating differently; no shared playbook library; spend is opaque; agents fail silently.
**What they need from Conduct:** the playbook canvas, the run timeline, spend visibility per team and per repo.

### 3. Individual developer — **adoption channel, not the buyer**

**Titles:** Senior Eng, SRE, AppSec engineer, ML engineer.
**Job to be done:** use Claude Code / Cursor / agents to do real work, without surprises from Guard.
**Day-to-day:** lives in their editor and terminal. Touches the Conduct web UI maybe weekly — to inspect a run, install a playbook, or check why Guard blocked something.
**Frustration today:** new tools that add friction without value. Will reject anything that feels like Big Brother without explanation.
**What they need from Conduct:** clear block explanations, fast skip / appeal paths, CLI parity with the web UI.

### 4. First-time visitor — **pre-signup, pre-trust**

**Context:** lands from HN, a Loopers comparison, a SOC 2 search, a peer recommendation. No account, no context.
**Job to be done:** decide in ≤2 minutes whether Conduct is worth a trial.
**What they need:** a concrete demo of Guard blocking something (#826), a one-screen description of the three automation lanes, proof other companies use it.
**What kills them:** signup walls, "schedule a demo" as the only CTA, marketing copy that doesn't name the buyer.

---

## Journey — 5 rungs (buyer-first ordering)

For each rung: who, what they're trying to do, what they see today, what they should see, what dies, where Guard shows up inline.

**Why this order:** Entry → Govern → Audit → Build → Run is buyer-first, not user-first. The security/compliance lead evaluates Govern + Audit before they ever care about Build or Run. The 30-second test (#860 constraint #1) hits in Entry; the case to pay hits in Govern + Audit; Build and Run come after the buyer has decided to use the product. See decision log #7.

### Rung 1 — Entry

**Who:** first-time visitor + returning user landing post-login.
**JTBD:** decide if this is worth using (pre-signup) / get to the thing they need to do (post-signup).
**Today:** marketing pages on `/`, `/guard-landing`, `/solutions`; post-login lands on `/projects` or `/dashboard` (sidebar-shaped, list-of-things).
**Target:** pre-signup — a hosted demo running #826's mock LLM, showing a real block in 60s (also passes the 30-second test: a security buyer sees Guard work before signing up). Post-signup — `/home` as the conversational entry, intent input scoped to the user's workspace context (their playbooks, their policies, their lane). Default post-login route changes from `/projects` to `/home`.
**Dies:** the "/dashboard as default landing" pattern. The blank sidebar greeting.
**Guard inline:** the demo's headline block event is the hero (pre-signup). The conversational entry surfaces recent Guard activity ("3 calls blocked overnight — review?") and the live spend ribbon as ambient prompts (post-signup).
**Resolved:** `/home` does not exist in the codebase (no file under `apps/web/src/app/`). The memory was stale. We build `/home` net-new per #859, not "wire up an existing draft." See decision log #8.



### Rung 2 — Govern (Guard policy, spend, compliance)

**Who:** security / compliance lead.
**JTBD:** set policy, review spend, prove compliance.
**Today:** `/guard`, `/guard/policies`, `/guard/spend`, `/guard/activity`, `/guard/reports/soc2`, `/governance`, `/security` — at least seven surfaces, overlapping responsibility.
**Target:** Guard becomes one canonical surface with three tabs (Policy, Spend, Activity) and one always-on compliance pack pane. The other six get redesigned or merged in. `/security` is already a 3-line redirect (effective kill, just delete the file). `/governance` is a 900+ line dupe of `/guard` — proper **merge** target.
**Dies:** `/security` redirect file. The duplication between `/guard` and `/governance`. The split between `/guard/policies` and policy enforcement views.
**Guard inline:** Guard *is* the rung. **Govern is the source of truth** — every policy, every spend cap, every compliance attestation defined here is referenced inline on Audit (rung 3), Build (rung 4), and Run (rung 5) as a Guard inline pill linking back to its definition here. This referential model is why Govern must come before Build/Run in the journey.

### Rung 3 — Audit

**Who:** security / compliance lead, auditor (read-only persona later).
**JTBD:** produce evidence on demand — for SOC 2, for enterprise sales, for board reviews.
**Today:** `/audit`, `/guard/session-reports`, `/guard/reports/soc2`. Timeline-of-events shape is partly there but split across pages.
**Target:** one audit timeline, filterable by user / tool / policy / lane. Every event links to the **compliance evidence chip** (primitive) that explains *what compliance requirement it satisfies* — not just the raw event. Export to compliance pack format. **This rung establishes the timeline primitive** that Run (rung 5) then reuses for execution traces.
**Dies:** report pages as separate destinations. Auditors should filter the timeline, not browse a report library.
**Guard inline:** Guard is the source of every audit event. The audit rung is a read view over Guard's event store, scoped by the auditor's question. Every row shows the policy version that fired (linking back to Govern, rung 2).



### Rung 4 — Build

**Who:** engineering lead, individual developer.
**JTBD:** turn an intent ("auto-fix CI failures with Claude") into a working playbook within one of the three lanes.
**Today:** canvas at `/workflows/[id]` or `/projects/[id]` — blank canvas, drag blocks, alien to first-time. Playbook marketplace at `/marketplace` is browse-then-install.
**Target:** ambient draft — user types intent or picks a starter; agent drafts canvas grounded on (a) connected integrations, (b) the three-lane block library, and (c) the policies already defined in Govern (rung 2). User edits the draft. The canvas itself stays — only the entry into it changes.
**Dies:** the blank canvas as a first-time experience. The "pick a playbook then configure 12 things" flow.
**Guard inline:** every block on the canvas shows its **Guard inline pill** (policy check, spend estimate, audit hook) without opening a sub-panel. Blocks that would violate an existing Govern policy show a red pill *at draft time*, not at run time. This is the Guard moat made visible in the editor.

### Rung 5 — Run

**Who:** engineering lead (monitoring), individual developer (debugging).
**JTBD:** see what the playbook actually did, why a step failed, what was blocked.
**Today:** `/runs` table, `/workflows/[id]/runs/[run_id]` detail with panels.
**Target:** run-as-first-class — a timeline view that **reuses the Audit timeline primitive** (rung 3), filtered to a single run. Every step shows its inputs, outputs, the Guard decision inline, and the cost. The timeline is the primary surface; tables become filterable indexes into timelines.
**Dies:** the panel-tabbed run detail. The disconnect between "what was the policy check" (Guard module) and "what was the step output" (run detail). The separate observability surface if it overlaps too much (see open question 3).
**Guard inline:** Guard decisions show as inline pills on the relevant step — color, reason, link to the policy that fired (back to Govern). Not a separate Guard column. Spend ribbon runs along the top.

---

## Surface map (day 1 — initial call per row; revisit any [contested] day 3)

| Page                                                    | Rung         | Keep | Redesign | Merge | Kill | Notes                                                       |
| ------------------------------------------------------- | ------------ | ---- | -------- | ----- | ---- | ----------------------------------------------------------- |
| `/` (marketing home)                                    | Entry        |      | x        |       |      | lead with Guard story, 3 lanes; current copy is dev-funnel  |
| `/guard-landing`                                        | Entry        | x    |          |       |      | already Guard-first; tighten only                           |
| `/solutions`                                            | Entry        |      |          | x     |      | merge into 3-lane sections under `/` or `/guard-landing`    |
| `/setup`                                                | Entry        |      | x        |       |      | slice 1 of #858 in parallel; full redesign post-doc         |
| `/sign-in`, `/sign-up`, `/accept-invite`                | Entry        | x    |          |       |      | Clerk-shaped, leave alone                                   |
| `/home` *(new)*                                         | Entry        |      |          |       |      | **build new** — conversational entry per #859               |
| `/dashboard`                                            | Entry/Build  |      | x        |       |      | stops being default landing; becomes a per-lane summary     |
| `/projects`                                             | Build        |      | x        |       |      | reframe as workspace index; project = canvas group          |
| `/projects/[id]`                                        | Build        |      | x        |       |      | becomes the canvas with run-history inline                  |
| `/workflows`, `/workflows/[id]`                         | Build        | x    |          |       |      | canvas stays; only entry changes                            |
| `/workflows/new`                                        | Build        |      | x        |       |      | ambient draft replaces blank canvas                         |
| `/workflows/[id]/settings`                              | Build        |      |          | x     |      | merge into canvas right-panel inspector                     |
| `/playbooks/[slug]`, `/marketplace/[slug]`              | Build        |      |          | x     |      | one canonical playbook detail view                          |
| `/playbook-queue`                                       | Build        |      | x        |       |      | becomes a Govern surface (admin approvals) [contested]      |
| `/playbooks/submit`                                     | Build        | x    |          |       |      | low-traffic, leave alone                                    |
| `/runs`, `/workflows/[id]/runs`                         | Run          |      | x        |       |      | timeline-first index                                        |
| `/workflows/[id]/runs/[run_id]`                         | Run          |      | x        |       |      | timeline view reusing Audit primitive                       |
| `/observability`                                        | Run          |      |          | x     |      | merge into `/runs` as a saved filter view                   |
| `/observability/alerts`                                 | Govern       |      | x        |       |      | move under Guard as "Alert rules" (policy adjacent)         |
| `/guard`                                                | Govern       |      | x        |       |      | redesigned as 3-tab spine (Policy / Spend / Activity)       |
| `/guard/policies`, `/guard/policies/new`                | Govern       |      |          | x     |      | merge into `/guard?tab=policy` inline editor                |
| `/guard/spend`                                          | Govern       |      |          | x     |      | merge into `/guard?tab=spend`                               |
| `/guard/activity`                                       | Govern       |      |          | x     |      | merge into `/guard?tab=activity`                            |
| `/guard/session-reports`, `/guard/session-reports/[id]` | Audit        |      |          | x     |      | merge into `/audit` timeline as a saved view                |
| `/guard/tool-errors`                                    | Govern       |      |          | x     |      | merge into activity tab w/ error filter                     |
| `/guard/team-memory`                                    | Govern       | x    |          |       |      | leave alone for now; unrelated to journey [contested]       |
| `/guard/settings`                                       | Govern       | x    |          |       |      | route may move under `/settings/guard` later                |
| `/guard/reports/soc2`                                   | Audit        |      |          | x     |      | first compliance pack — merge into `/audit?pack=soc2`       |
| `/governance`                                           | Govern       |      |          | x     |      | true dupe of `/guard` (947 lines) — merge content + redirect |
| `/security`                                             | —            |      |          |       | x    | 3-line redirect file; delete it                             |
| `/audit`                                                | Audit        |      | x        |       |      | timeline-first canonical surface                            |
| `/settings`, `/settings/modules`                        | Settings     | x    |          |       |      | tabbed surface stays                                        |
| `/integrations`                                         | Settings     | x    |          |       |      | tools moved here from /setup                                |


---

## Primitives (skeleton — content day 3)

- **Intent input** — chat-as-finder, lives in shell. Scoped to workspace context. Not blank-slate.
- **Block / node card** — same card on canvas (build rung) and timeline (run rung).
- **Guard inline pill** — decision (allow / block / warn) shown wherever an action is shown. The spine made visible.
- **Compliance evidence chip** — links a screen element to a SOC 2 / OWASP / internal requirement. Renders in audit timeline + on compliance pack pages.
- **Result card** — router output, search result, run summary all the same shape.
- **Spend ribbon** — running cost displayed inline on canvas + run timeline + governance.
- **Role chip** — RBAC made visible. User always knows what role they're acting as.

---

## Decision log (fill as decisions land)


| #   | Decision                                                                         | Alternative considered                             | Why we picked it                                                                             | Date       |
| --- | -------------------------------------------------------------------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------- |
| 1   | Guard-on-every-rung (inline pill on all surfaces)                                | Guard as a single module                           | Security buyer's 30-second test fails if Guard is only one tab                               | 2026-06-26 |
| 2   | B2B-not-consumer pattern sourcing (Linear / Vercel / Datadog / GitHub)           | Borrow from Lovable / v0 for ambient draft         | Consumer patterns assume zero context; B2B users have rich workspace context to drive intent | 2026-06-26 |
| 3   | No rip-and-replace; redesigns ship behind flags                                  | Big-bang relaunch                                  | Risk to existing users + canvas already differentiates; no upside to forced cutover          | 2026-06-26 |
| 4   | Run view becomes timeline-first                                                  | Keep panel-tabbed run detail                       | Audit + run are the same shape (event sequence); merging the model saves a surface           | 2026-06-26 |
| 5   | Govern collapses to one Guard surface with three tabs                            | Keep `/governance`, `/security`, `/guard` separate | Duplication confuses buyers; one canonical "Guard" is what the positioning sells             | 2026-06-26 |
| 6   | Three automation lanes (compliance / security / engineering) enforced in catalog | Generic "team automations" framing                 | v3 positioning lock; matches buyer language                                                  | 2026-06-26 |
| 7   | Journey order is Entry → Govern → Audit → Build → Run (buyer-first, not user-first) | Entry → Build → Run → Govern → Audit (action-first) | Security buyer evaluates Govern + Audit before they care about Build/Run; the case to pay lands in rungs 2–3; rungs 4–5 are post-purchase. Also makes Govern the canonical source of policies that Audit/Build/Run reference inline. | 2026-06-26 |
| 8   | Build `/home` net-new as the conversational entry; do not "wire up an existing draft" | Reuse a drafted home page from prior session | Confirmed via filesystem search — no `/home` file exists. Memory was stale, now corrected. Spec from #859 is the source. | 2026-06-26 |
| 9   | Delete `/security` (3-line redirect file) and merge `/governance` (947 lines) into `/guard` with a redirect | Keep both as distinct surfaces | `/security` already does nothing; `/governance` is a content dupe. v3 positioning says one canonical Guard surface. | 2026-06-26 |
| 10  | Merge `/observability` into `/runs` as a saved filter view; keep `/observability/alerts` and move it under Guard | Keep `/observability` as a parallel surface to `/runs` | Both are timeline-of-events at heart. Alerts are policy-adjacent, so they belong on the Guard side. [contested — confirm with whoever owns observability today] | 2026-06-26 |


---

## Open questions (resolve by day 4)

1. ~~Does `/home` exist as a real route?~~ **Resolved day 1:** no — build new (decision #8).
2. ~~`/governance` vs `/security` vs `/guard` — confirm which two die.~~ **Resolved day 1:** delete `/security`, merge `/governance` into `/guard` (decision #9).
3. ~~`/observability` vs `/runs` — overlap?~~ **Resolved day 1:** merge `/observability` into `/runs`, move `/observability/alerts` under Guard (decision #10, [contested]).
4. `/dashboard` — what is it actually for today? Who lands there? **Day 2:** read the file, name what it does, decide the redesign target (per-lane summary feels right but unverified).
5. Marketing pages — in scope or separate track? **Day 2 decision needed.** Recommendation: in scope for the journey rung 1, but visual / brand work is the separate track.
6. **New (day 1):** `/playbook-queue` — is this an admin approval surface (Govern) or a developer queue (Build)? Function unclear from the route name. Read file day 2.
7. **New (day 1):** does the canvas right-panel inspector exist today, or do we need to build it before `/workflows/[id]/settings` can be merged?
8. **New (day 1):** which compliance pack format do we standardize on for the `/audit?pack=*` export? SOC 2 is row one; ISO 27001 + EU AI Act are likely next (per Lexoculus capture memory).

---

*End of day 1. Next: day 2 — read `/dashboard` + `/playbook-queue`, decide marketing-track scope, start primitive specs.*