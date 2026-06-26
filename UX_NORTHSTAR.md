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

## Journey — 5 rungs (first-pass, Sudhi to react)

For each rung: who, what they're trying to do, what they see today, what they should see, what dies, where Guard shows up inline.

### Rung 1 — Entry
**Who:** first-time visitor + returning user landing post-login.
**JTBD:** decide if this is worth using (pre-signup) / get to the thing they need to do (post-signup).
**Today:** marketing pages on `/`, `/guard-landing`, `/solutions`; post-login lands on `/projects` or `/dashboard` (sidebar-shaped, list-of-things).
**Target:** pre-signup — a hosted demo running #826's mock LLM, showing a real block in 60s. Post-signup — `/home` as the conversational entry, intent input scoped to the user's workspace context (their playbooks, their policies, their lane).
**Dies:** the "/dashboard as default landing" pattern. The blank sidebar greeting.
**Guard inline:** the demo's headline block event is the hero. The conversational entry surfaces recent Guard activity ("3 calls blocked overnight — review?") as ambient prompts.
**[contested]** `/home` route was drafted (per memory) but I can't find a file for it in `apps/web/src/app/(app)/`. Either it lives elsewhere or it was never landed. Confirm in decision log tomorrow.

### Rung 2 — Build
**Who:** engineering lead, individual developer.
**JTBD:** turn an intent ("auto-fix CI failures with Claude") into a working playbook.
**Today:** canvas at `/workflows/[id]` or `/projects/[id]` — blank canvas, drag blocks, alien to first-time. Playbook marketplace at `/marketplace` is browse-then-install.
**Target:** ambient draft — user types intent or picks a playbook; agent drafts canvas grounded on connected integrations and the three-lane block library; user edits the draft. The canvas itself stays — only the entry into it changes.
**Dies:** the blank canvas as a first-time experience.
**Guard inline:** every block on the canvas shows its Guard posture (policy check, spend estimate, audit hook) without opening a sub-panel.

### Rung 3 — Run
**Who:** engineering lead (monitoring), individual developer (debugging).
**JTBD:** see what the playbook actually did, why a step failed, what was blocked.
**Today:** `/runs` table, `/workflows/[id]/runs/[run_id]` detail with panels.
**Target:** run-as-first-class — a timeline view (not a table-with-panels). Every step shows its inputs, outputs, the Guard decision inline, and the cost. The timeline is the primary surface; tables become filterable indexes into timelines.
**Dies:** the panel-tabbed run detail. The disconnect between "what was the policy check" (Guard module) and "what was the step output" (run detail).
**Guard inline:** Guard decisions show as inline pills on the relevant step — color, reason, link to the policy that fired. Not a separate Guard column.

### Rung 4 — Govern (Guard policy, spend, compliance)
**Who:** security / compliance lead.
**JTBD:** set policy, review spend, prove compliance.
**Today:** `/guard`, `/guard/policies`, `/guard/spend`, `/guard/activity`, `/guard/reports/soc2`, `/governance`, `/security` — at least seven surfaces, overlapping responsibility.
**Target:** Guard becomes one canonical surface with three tabs (Policy, Spend, Activity) and one always-on compliance pack pane. The other six get redesigned or merged in. `/governance` and `/security` are probably dupes — likely **merge** candidates.
**Dies:** the duplication between `/guard`, `/governance`, `/security`. The split between `/guard/policies` and policy enforcement views.
**Guard inline:** Guard *is* the rung. The other rungs reference policy versions and spend lines defined here.

### Rung 5 — Audit
**Who:** security / compliance lead, auditor (read-only persona later).
**JTBD:** produce evidence on demand — for SOC 2, for enterprise sales, for board reviews.
**Today:** `/audit`, `/guard/session-reports`, `/guard/reports/soc2`. Timeline-of-events shape is partly there but split across pages.
**Target:** one audit timeline, filterable by user / tool / policy / lane. Every event links to the evidence chip that explains *what compliance requirement it satisfies* — not just the raw event. Export to compliance pack format.
**Dies:** report pages as separate destinations. Auditors should filter the timeline, not browse a report library.
**Guard inline:** Guard is the source of every audit event. The audit rung is a read view over Guard's event store, scoped by the auditor's question.

---

## Surface map (skeleton — fill day 2)

| Page | Rung | Keep | Redesign | Merge | Kill | Notes |
|---|---|---|---|---|---|---|
| `/` (marketing home) | Entry | | | | | |
| `/guard-landing` | Entry | | | | | |
| `/solutions` | Entry | | | | | |
| `/setup` | Entry | | x | | | Slice 1 of #858 in parallel |
| `/sign-in`, `/sign-up`, `/accept-invite` | Entry | x | | | | |
| `/home` | Entry | | | | | [contested] — does it exist? |
| `/dashboard` | Entry/Build | | x | | | "default landing" pattern dies |
| `/projects` | Build | | x | | | |
| `/projects/[id]` | Build | | | | | |
| `/workflows`, `/workflows/[id]` | Build | x | | | | canvas stays |
| `/workflows/new` | Build | | x | | | ambient draft replaces blank |
| `/workflows/[id]/settings` | Build | | | x | | merge into canvas right-panel? |
| `/playbooks/[slug]`, `/marketplace/[slug]` | Build | | | x | | likely merge |
| `/playbook-queue`, `/playbooks/submit` | Build | | | | | |
| `/runs`, `/workflows/[id]/runs` | Run | | x | | | timeline-first |
| `/workflows/[id]/runs/[run_id]` | Run | | x | | | timeline view |
| `/observability`, `/observability/alerts` | Run | | | | | overlap with `/runs`? |
| `/guard` | Govern | x | | | | spine surface |
| `/guard/policies`, `/guard/policies/new` | Govern | | x | | | inline policy editor |
| `/guard/spend` | Govern | | | x | | merge into `/guard` tab |
| `/guard/activity` | Govern | | | x | | merge into `/guard` tab |
| `/guard/session-reports`, `/guard/session-reports/[id]` | Govern/Audit | | x | | | timeline shape |
| `/guard/tool-errors` | Govern | | | x | | merge into activity |
| `/guard/team-memory` | Govern | | | | | role unclear |
| `/guard/settings` | Govern | x | | | | |
| `/guard/reports/soc2` | Audit | | | x | | merge into audit timeline |
| `/governance`, `/security` | Govern | | | x | | dupes of `/guard`? |
| `/audit` | Audit | | x | | | timeline-first |
| `/settings`, `/settings/modules` | Settings | x | | | | |
| `/integrations` | Settings | x | | | | tools moved here from /setup |

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

| # | Decision | Alternative considered | Why we picked it | Date |
|---|---|---|---|---|
| 1 | Guard-on-every-rung (inline pill on all surfaces) | Guard as a single module | Security buyer's 30-second test fails if Guard is only one tab | 2026-06-26 |
| 2 | B2B-not-consumer pattern sourcing (Linear / Vercel / Datadog / GitHub) | Borrow from Lovable / v0 for ambient draft | Consumer patterns assume zero context; B2B users have rich workspace context to drive intent | 2026-06-26 |
| 3 | No rip-and-replace; redesigns ship behind flags | Big-bang relaunch | Risk to existing users + canvas already differentiates; no upside to forced cutover | 2026-06-26 |
| 4 | Run view becomes timeline-first | Keep panel-tabbed run detail | Audit + run are the same shape (event sequence); merging the model saves a surface | 2026-06-26 |
| 5 | Govern collapses to one Guard surface with three tabs | Keep `/governance`, `/security`, `/guard` separate | Duplication confuses buyers; one canonical "Guard" is what the positioning sells | 2026-06-26 |
| 6 | Three automation lanes (compliance / security / engineering) enforced in catalog | Generic "team automations" framing | v3 positioning lock; matches buyer language | 2026-06-26 |

---

## Open questions (resolve by day 4)

1. Does `/home` exist as a real route? Memory says yes; filesystem says no. Confirm.
2. `/governance` vs `/security` vs `/guard` — confirm which two die.
3. `/observability` vs `/runs` — overlap? Same surface with different filters?
4. `/dashboard` — what is it actually for today? Who lands there?
5. Marketing pages — in scope or separate track?

---

*End of day 0 skeleton. Next: day 1 — refine journey + start surface map cells.*
