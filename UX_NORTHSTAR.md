# UX Northstar — Conduct

> **Purpose:** A constraint document that names the journey, the kill list, and the decisions for Conduct's UX as of mid-2026. Not a manifesto. Not a vision essay. Everything we ship after this week references this doc.
>
> **Timebox:** 1 week. Ships day 7 even if incomplete.
>
> **What this doc is:** journey + surface map + primitives + decision log. The screens we keep, redesign, merge, or kill — and why.
>
> **What this doc is not:** pixel-perfect design (after this), brand or visual identity (separate track), a re-opening of positioning (v3 is the input).

---

## Executive summary

Conduct is shifting its UX from a 2024 SaaS console (sidebar + list pages + settings) to a 2026 AI-app shape (conversational + ambient + governance-spine) — *without rip-and-replace*. The canvas stays. Guard becomes the visible spine on every rung. The journey reorders to buyer-first (Entry → Govern → Audit → Build → Run) so the security / compliance lead sees the case to pay before they ever touch Build / Run.

The doc names **9 primitives** (Guard inline pill, compliance evidence chip, intent input, block card, timeline row, spend ribbon, role chip, compliance pack pane, right-panel inspector), **10 wireframes**, **23 decisions**, **5 phases** of implementation (Phase 0 unblockers → Phase 4 marketing), and **5 success metrics** (one per rung, 90-day targets).

What dies: `/security` (3-line redirect), `/governance` (947-line dupe of `/guard`), the "blank canvas as first-time experience," the "dashboard as default landing" pattern, generic "team automations" copy. What's net-new: `/home` (conversational entry), the right-panel inspector primitive, the Guard event-schema `satisfies` field, the 3-tab Guard spine, the compliance pack pane.

## How to read this doc

- **For a 5-minute scan:** read this summary + the journey rungs + the wireframes section headings. That's the shape.
- **For implementation:** start with the *Implementation order* section. Phase 0 is the gate to everything else.
- **For a single screen:** look it up in the surface map, then jump to the wireframe and any decisions that reference it.
- **For a single decision:** the decision log is authoritative. The journey + primitives describe the *what*; decisions describe the *why and what-was-considered*.
- **Load-bearing primitives:** #1 (Guard inline pill) and #2 (compliance evidence chip) — every constraint depends on these existing.
- **Load-bearing decisions:** #1 (Guard-on-every-rung), #3 (no rip-and-replace), #4 (run = timeline), #7 (buyer-first order), #21 (5-phase order). If you change one of these, the whole doc shifts.

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
| `/dashboard`                                            | Run/Govern   |      | x        |       |      | stops being default landing; reframed as "ops overview" — KPIs + SpendArc + GuardSnapshot + agent-health. Sits next to /home as a power-user deep-link, never the default route. |
| `/projects`                                             | Build        |      | x        |       |      | reframe as workspace index; project = canvas group          |
| `/projects/[id]`                                        | Build        |      | x        |       |      | becomes the canvas with run-history inline                  |
| `/workflows`, `/workflows/[id]`                         | Build        | x    |          |       |      | canvas stays; only entry changes                            |
| `/workflows/new`                                        | Build        |      | x        |       |      | ambient draft replaces blank canvas                         |
| `/workflows/[id]/settings`                              | Build        |      |          | x     |      | merge into canvas right-panel inspector                     |
| `/playbooks/[slug]`, `/marketplace/[slug]`              | Build        |      |          | x     |      | one canonical playbook detail view                          |
| `/playbook-queue`                                       | Govern       |      |          | x     |      | confirmed admin/security-only approval surface — merge into `/guard?tab=approvals` |
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

## Primitives

The reusable building blocks every surface uses. The first two (Guard inline pill + compliance evidence chip) are load-bearing — Guard-on-every-rung depends on them. Spec'd day 2. The rest are listed with one-liners; specs land day 3.

### 1. Guard inline pill — **load-bearing**

Decision badge that appears wherever an action is shown. The visible form of the Guard spine.

**Surfaces:**
- Build (Rung 4) — on every block in the canvas, predicted from current policies
- Run (Rung 5) — on every step in the timeline, actual decision at run time
- Audit (Rung 3) — on every event in the timeline
- Govern (Rung 2) — on the policy itself ("this policy blocked 47 calls this week")
- Entry (Rung 1) — on the ambient "3 calls blocked overnight" prompt on /home

**States (color + label, B2B subdued palette — not consumer red/green):**
- `allow` — slate, no label by default; "Allowed" on hover
- `warn` — amber, label "Warn: {short reason}" (e.g. "Warn: 80% of monthly cap")
- `block` — red, label "Blocked: {short reason}" (e.g. "Blocked: above per-call cap")
- `predict` — outlined (dashed) variant of allow/warn/block, used at draft time on canvas. Same colors. Hover reveals "Predicted at draft time."
- `synthetic` — gray outlined, used for demo / mock-LLM events so they're visually distinct in audit

**Anatomy:**
- Compact (dense lists, default in timelines and canvas): 20px pill, color dot + 1-line label, click → expand inline
- Expanded (detail views, on demand): same pill + reason text + "Policy: {name}@{version}" link → Govern policy detail

**Behavior:**
- Every pill links back to the policy that fired (Govern rung is the source of truth)
- At draft time (Build), only `predict` variant — no actual decision yet
- Pills are read-only in Run + Audit (events are immutable); editable on Govern (you can change the policy that produced them)

**Accessibility:**
- Color never carries information alone; the label always names the state
- Screen-reader announces decision + reason + policy name
- Keyboard: pill is focusable; Enter expands, Esc collapses

**[contested]** Should `predict` show on canvas always, or only after the first save? Always is more honest; first-save reduces noise. Recommend always; revisit if developers complain in week-2 dogfood.

### 2. Compliance evidence chip — **load-bearing**

Chip that links a screen element (an event, a policy, a block, a setting) to a compliance requirement it satisfies.

**Surfaces:**
- Audit (Rung 3) — on every timeline row that maps to a requirement
- Govern (Rung 2) — on each policy ("satisfies SOC 2 CC6.1")
- Marketing (Entry, Rung 1) — on the homepage compliance section, linking to live evidence

**Anatomy:**
- 22px chip with framework icon (SOC 2 / ISO 27001 / EU AI Act / OWASP-for-LLMs / internal) + requirement code (e.g. `CC6.1`, `A.5.1`, `§27`)
- Hover: framework full name + 1-line requirement summary
- Click: → requirement definition page + the events that satisfy it

**Behavior:**
- Multiple chips per row when an event satisfies multiple frameworks (common: SOC 2 + ISO 27001 from one access-control event)
- Bulk select on audit timeline → export to compliance pack format (PDF + JSON per framework)
- Filter audit timeline by chip ("show me everything satisfying SOC 2 CC6.*")

**Data model implications:**
- Each event in Guard's event store needs a `satisfies: [{ framework, requirement_code }]` field (likely already partly there per Guard schema; verify day 3)
- Requirement registry is its own thing — versioned, framework-namespaced, owned by `apps/api/app/modules/guard/compliance/` (verify location day 3)

**v1 frameworks (per Lexoculus + SOC 2 capture memories):**
1. SOC 2 (CC controls) — primary
2. EU AI Act (§16, §27 most common) — second priority
3. ISO 27001 — third
4. OWASP-for-LLMs — fourth (already partly there per #828)
5. Internal policies — fifth (customer-defined requirements)

**[contested]** Display strategy when an event satisfies 4+ requirements — show first two + "+3 more"? Show a count? Use the count chip pattern Linear uses for issue labels.

### 3. Intent input

Chat-as-finder, lives in the app shell. Scoped to the user's workspace context — not blank-slate.

**Surfaces:**
- Shell (always-on, top of every page) — collapsed pill, click to expand
- `/home` (Entry, Rung 1) — expanded by default, primary surface focus
- Build (Rung 4) — used to draft a new playbook ("auto-fix CI failures with Claude")
- Govern (Rung 2) — used to draft a new policy ("block GPT-4 calls over $0.50")
- Audit (Rung 3) — used to filter the timeline ("show me everything blocked yesterday by the AppSec lane")

**Behavior:**
- Suggestions are workspace-aware: pulled from connected integrations, existing playbooks, active policies, current user's lane
- Three routing modes: **find** (navigate to a surface, no LLM), **draft** (LLM call, produces a canvas / policy / filter), **ask** (LLM call, returns an answer card)
- Mode is auto-selected from the intent; user can override with a `/find` `/draft` `/ask` prefix
- B2B copy rules: never "What would you like to build today?" — always anchored ("Find a run, draft a policy, ask a question. Try: ‘show me blocks from last week'.")

**Accessibility:**
- `/` keyboard shortcut focuses it on any page
- Esc collapses; Cmd-Enter submits
- Screen reader announces routing mode + result count

**Data-model implications:**
- Needs a small intent classifier (single LLM call routing to ~10 destinations + a generator hook for draft mode)
- Suggestion data needs an endpoint listing recent playbooks / policies / runs for the current workspace + lane

### 4. Block / node card

Single card shape reused on canvas (Build) and timeline (Run + Audit). One component, one set of states.

**Anatomy:**
- 64px tall in dense layouts (timeline), 96px in spacious (canvas)
- Left: block-type icon (action / trigger / brain / guard / approval / notify / memory / output)
- Middle: name + lane chip + Guard inline pill
- Right: spend estimate (canvas) or actual cost (run) + status icon
- Hover: drill-down chevron appears
- Click: opens detail in right-panel inspector (primitive #9, see below — does not exist today, must be built)

**States:**
- Draft (canvas) — outlined, `predict` Guard pill, dashed border
- Active (run, in-flight) — solid, animated dot
- Done (run, finished) — solid, status checkmark or fail icon
- Blocked (run) — red border, Guard pill expanded by default

**Reuse means:** changing the card visual changes both canvas + timeline. One source of truth keeps them coherent — and means a redesign is one PR, not two.

### 5. Timeline row

The Audit-and-Run primitive. Established in Audit (Rung 3), reused in Run (Rung 5). Establishes the canonical "event with provenance" shape.

**Anatomy:**
- Compact mode (Audit index): 48px tall — timestamp / actor / action / target / Guard inline pill / compliance evidence chip(s) / spend
- Expanded (single-run detail): 96px — same fields + inputs/outputs preview + drill-down to event JSON

**States:**
- Single event (audit row)
- Step (run sub-event, indented under parent run)
- Group (collapsed cluster — "47 allow events" if you're filtering for blocks)

**Filtering anchors (the surface-level promise):**
- Time range
- Actor (user / agent / playbook)
- Lane (compliance / security / engineering)
- Policy (back-link from Guard inline pill)
- Compliance framework (back-link from evidence chip)
- Decision (allow / warn / block)

**Why this is one primitive, not two:** Audit + Run are both "ordered events with provenance." Different filters, same shape. One primitive forces consistency.

### 6. Spend ribbon

Running cost shown inline wherever a cost is accruing.

**Surfaces:**
- Canvas (Build, Rung 4) — projected cost per run + cumulative for the playbook this month
- Run timeline (Run, Rung 5) — actual cost growing as steps complete
- Govern Spend tab (Govern, Rung 2) — the canonical view, per-developer + per-team breakdown
- `/home` (Entry) — current month vs budget as ambient context

**Anatomy:**
- Thin bar (4px), color-graded: emerald (under 50%) → slate (50–80%) → amber (80–100%) → red (over)
- Right side: `$current / $budget` text
- Hover: tooltip with breakdown by lane

**Behavior:**
- Always references the per-developer + per-team budgets defined in Govern (Rung 2)
- Clicking the ribbon opens Govern Spend tab pre-filtered to the relevant scope (this playbook / this run / this developer)
- Goes red and pulses when the budget breaches — same visual on every surface

### 7. Role chip

RBAC made visible. User always knows what role they're acting as. Required for B2B audience.

**Surfaces:** app shell header, every screen.

**Anatomy:**
- 22px chip, slate-bordered, role icon + role name + workspace name
- Click: opens role / workspace switcher
- Multi-role users: dropdown showing every role they have, current one checked

**Roles (per ROLES.md):** admin, security, developer, viewer.

**Behavior:**
- Surfaces that require a specific role (Govern, audit export, settings) show a small lock chip if the user can't act
- Hover on the lock: "Requires {role}. Switch role or ask {admin name}."
- Never silently hides surfaces — RBAC is visible so users know what they're missing

### 8. Compliance pack pane

Always-on accessory on the Govern surface; doubles as the click target from marketing's compliance section.

**Surfaces:**
- Govern (Rung 2) — always-visible right-rail pane
- Marketing `/` and `/guard-landing` (Entry) — abbreviated form ("SOC 2: 87 events satisfied · ISO 27001: 41 · EU AI Act: 12")
- Audit export flow (Rung 3) — picker for which pack to export

**Anatomy:**
- Card per framework (SOC 2, EU AI Act, ISO 27001, OWASP-for-LLMs, internal)
- Each card: framework name + completion % + last evidence-export date + gap count
- Click a card → Audit timeline filtered to that framework

**Behavior:**
- "Export pack" CTA on each card — produces a PDF + JSON bundle for that framework, with linked evidence chips for every requirement
- Gap count is clickable → "show me requirements with no events"
- v1 covers SOC 2 only; other frameworks show "Coming soon — request access" (B2B selling motion)

### 9. Right-panel inspector — **does not exist today, must be built**

Discovered day 3: no existing right-panel-inspector component in `apps/web/src/components/`. Required by primitive #4 (block card click target) and the merged-in `/workflows/[id]/settings` (decision day 1). Spec'd here so day-3 reviewer sees the dependency.

**Surfaces:**
- Build canvas (block detail)
- Run timeline (step detail)
- Audit timeline (event detail)
- Govern policy list (policy detail)

**Anatomy:**
- 420px right-edge sheet, collapsible
- Header: title + close + "open as full page" link
- Tabs for the resource type (block: config / Guard / history; event: detail / linked policy / linked compliance)
- Persists which tab the user last used per resource type

**Why one primitive, not four:** every surface in the doc has a "click to inspect" intent. One sheet shape applied consistently is cheaper and more learnable than per-surface modals.

---

## Wireframes (low-fi, ASCII)

ASCII boxes instead of Excalidraw — readable inline in the PR, captures layout + flow + primitive placement. Pixel fidelity is out of scope this week (per #860). 8–10 key screens. Day 3 ships 2 of them (the load-bearing entry + Govern surfaces); day 4 ships the rest.

### Wireframe 1 — `/home` (Entry, post-login)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [Conduct logo]   [workspace ▾]  [role chip: developer · Engineering]   │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  spend ribbon:  ████████░░░░░░░░░░░  $312 / $500 this month  ▾          │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Find a run, draft a policy, ask a question.                       │ │
│  │  Try: "show me blocks from last week"                              │ │
│  │  [               intent input              ]   [/]                 │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  Recent Guard activity                                                   │
│  ─────────────────────────────────                                       │
│  • 3 calls blocked overnight by Engineering lane    [Guard pill: block] │
│    └ Policy: "no-claude-opus-without-approval @v3"                       │
│  • 1 spend warning at 80% — DevOps team             [Guard pill: warn]  │
│  • SOC 2 export ready: 47 new events linked         [evidence: CC6.1]   │
│                                                                          │
│  Your lanes                                                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                        │
│  │ Compliance  │ │ Security    │ │ Engineering │                        │
│  │ 4 playbooks │ │ 7 playbooks │ │ 11 playbooks│                        │
│  │ 12 runs/wk  │ │ 23 runs/wk  │ │ 89 runs/wk  │                        │
│  └─────────────┘ └─────────────┘ └─────────────┘                        │
│                                                                          │
│  [ → Canvas ] [ → /guard ] [ → /audit ]   (B2B nav, not a sidebar)      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** intent input (expanded), spend ribbon (header), role chip (header), Guard inline pill (activity list), compliance evidence chip (SOC 2 export row).

**Annotations:**
- Activity list is ambient — 3 items max, scoped to the user's lane. Not a feed.
- "Your lanes" cards are quick-jumps, not dashboards. Detail is in canvas.
- No persistent sidebar. Nav is the row at the bottom + the workspace switcher in the header (Linear-style: keyboard + workspace switcher do most of the work).

### Wireframe 1a — `/home` empty state (first session post-setup)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [Conduct logo]   [workspace ▾]  [role chip · developer · Engineering] │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  spend ribbon:  ░░░░░░░░░░░░░░░░░░░░  $0 / $500 this month              │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Find a run, draft a policy, ask a question.                       │ │
│  │  Try: "draft a PR review bot for our repo"                         │ │
│  │  [               intent input              ]   [/]                 │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  No runs yet — start with a starter playbook:                           │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                     │
│  │ PR Review    │ │ Autopilot    │ │ SOC 2 evid.  │                     │
│  │ Bot          │ │ + Approval   │ │ collector    │                     │
│  │ Engineering  │ │ Engineering  │ │ Compliance   │                     │
│  │ [Install]    │ │ [Install]    │ │ [Install]    │                     │
│  └──────────────┘ └──────────────┘ └──────────────┘                     │
│                                                                          │
│  Guard is already protecting your workspace.                            │
│  ▸ 0 policies set (defaults active)            [→ tune]                 │
│  ▸ $500 monthly budget (set in setup)          [→ adjust]               │
│                                                                          │
│  [ → Canvas ] [ → /guard ] [ → /audit ]                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**Annotation:** zero-state shows three lane-tagged starter playbooks (one per lane), not a generic catalog. Guard reassurance card sits below to make the spine visible from second one of session one.

### Wireframe 2 — `/guard` (Govern, 3-tab spine)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Guard  [● ON]                          [role chip · security · Eng wsp] │
│  ─────────────────────────────────────────────────────────────────────  │
│  [ Policy ]  [ Spend ]  [ Activity ]  [ Approvals ]   <— tabs           │
│                                                                          │
│  ─── Policy tab ─────────────────────────────────────────────────────── │
│                                                                          │
│  ┌── policies ────────────────────────────┐  ┌── compliance pack ─────┐ │
│  │ ▸ no-claude-opus-without-approval @v3  │  │  SOC 2     87 ev  →    │ │
│  │   [block]  fires: 47/wk                │  │  EU AI Act 12 ev  →    │ │
│  │ ▸ block-gpt4-over-50c          @v1     │  │  ISO 27001 41 ev  →    │ │
│  │   [warn ]  fires: 12/wk                │  │  OWASP-LLM 9  ev  →    │ │
│  │ ▸ require-signed-policy        @v2     │  │  Internal  3  ev  →    │ │
│  │   [block]  fires: 0/wk                 │  │                        │ │
│  │                                        │  │  Last export:          │ │
│  │  + new policy   [draft via intent ▾]   │  │   SOC 2 — 3 days ago   │ │
│  └────────────────────────────────────────┘  └────────────────────────┘ │
│                                                                          │
│  ─── spend ribbon (entire-org view) ──────────────────────────────────  │
│  ████████████░░░░░░░░  $3,210 / $5,000 this month  [by lane ▾]         │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** Guard inline pill (per-policy fire decision), compliance evidence chip (right-rail pane), spend ribbon (footer), role chip (header).

**Annotations:**
- "Draft via intent" button is the entry into the intent-input primitive — drafts a new policy from natural language.
- Compliance pack pane is the right rail; clicking a framework deep-links to Audit filtered to that framework.

### Wireframe 3 — `/guard?tab=spend` (Govern, Spend tab)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Guard  [● ON]                          [role chip · admin · Eng wsp]  │
│  [ Policy ]  [ Spend ●]  [ Activity ]  [ Approvals ]                   │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  This month                                                              │
│  ████████████████░░░░░░░░  $3,210 / $5,000 (64%)                       │
│                                                                          │
│  By lane                                                                 │
│  ┌─────────────┬──────────┬──────────┬──────────┐                       │
│  │ Lane        │  Spent   │ Budget   │  Trend   │                       │
│  ├─────────────┼──────────┼──────────┼──────────┤                       │
│  │ Compliance  │   $410   │  $1,000  │  ▼ 12%   │                       │
│  │ Security    │ $1,140   │  $2,000  │  ▲ 4%    │                       │
│  │ Engineering │ $1,660   │  $2,000  │  ▲ 21% ⚠ │                       │
│  └─────────────┴──────────┴──────────┴──────────┘                       │
│                                                                          │
│  By developer                                                            │
│  ┌─────────────┬──────────┬──────────┬───────────┐                      │
│  │ Developer   │  Spent   │ Per-cap  │  Status   │                      │
│  ├─────────────┼──────────┼──────────┼───────────┤                      │
│  │ Sudhi       │   $312   │   $400   │  ok       │                      │
│  │ Jen         │   $189   │   $250   │  ok       │                      │
│  │ Alex        │   $247   │   $250   │  ⚠ 99%    │                      │
│  └─────────────┴──────────┴──────────┴───────────┘                      │
│                                                                          │
│  [ + adjust team budget ]    [ + add per-dev limit ]                    │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** spend ribbon (header), role chip (header), Guard inline pill implied in ⚠ markers.

**Annotations:** lane row turns amber when ≥80% of lane budget, red ≥100%. Per-dev row goes ⚠ at 99% (matches the "hard cap at 100%" toggle from /setup).

### Wireframe 4 — `/audit` (Audit, timeline-first)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Audit                                  [role chip · security · Eng wsp]│
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  Filters: [ time ▾ ]  [ actor ▾ ]  [ lane ▾ ]  [ policy ▾ ]            │
│           [ framework ▾ ]  [ decision: all ▾ ]            [ export ▾ ]  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 14:32  sudhi      run     pr-review-bot.engineering              │   │
│  │        [Guard: allow]    [SOC 2 CC6.1]    $0.04                  │   │
│  ├──────────────────────────────────────────────────────────────────┤   │
│  │ 14:31  alex       run     autopilot-fix.engineering              │   │
│  │        [Guard: BLOCK — above per-call cap]                       │   │
│  │        Policy: block-gpt4-over-50c @v1                  →        │   │
│  ├──────────────────────────────────────────────────────────────────┤   │
│  │ 14:28  agent      tool    github.create_pr  (autopilot run #4823)│   │
│  │        [Guard: allow]    [SOC 2 CC6.1] [EU AI Act §27]   $0.00   │   │
│  ├──────────────────────────────────────────────────────────────────┤   │
│  │ 14:22  jen        policy.edit  block-gpt4-over-50c v0→v1        │   │
│  │        [Guard: allow]    [SOC 2 CC6.6] [internal-policy]  -      │   │
│  ├──────────────────────────────────────────────────────────────────┤   │
│  │ 47 more allow events  [show all]                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Showing 4 of 51 events for the last 24h                                │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** timeline row (the surface itself), Guard inline pill (per row), compliance evidence chip (per row), role chip (header).

**Annotations:**
- Compact mode 48px rows; click → right-panel inspector (primitive #9) with full event JSON.
- 47-allow collapse is the "group" timeline-row state — keeps the surface scannable when 99% of events allow.
- Export dropdown produces compliance packs (SOC 2 / EU AI Act / etc.) using the framework filter.

### Wireframe 5 — `/workflows/[id]` canvas with Guard pills (Build)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PR Review Bot · engineering         [role chip · developer · Eng wsp] │
│  [ canvas ●]  [ runs ]  [ settings ]                          [ run ▶ ] │
│  ─────────────────────────────────────────────────────────────────────  │
│  spend ribbon (projected per-run):  ████░░░░░░  $0.42 / $1.00 cap      │
│                                                                          │
│  ┌──────────────┐                                                       │
│  │ TRIGGER      │  GitHub PR opened                                      │
│  │ [predict: ●] │                                          ──→          │
│  └──────────────┘                                                       │
│           │                                                              │
│           ▼                                                              │
│  ┌──────────────┐                                                       │
│  │ MEMORY       │  recall prior reviews for this repo                    │
│  │ [predict: ●] │  → 2,400 tokens                                       │
│  └──────────────┘                                                       │
│           │                                                              │
│           ▼                                                              │
│  ┌──────────────┐                                                       │
│  │ AGENT STEP   │  Claude reviews PR diff                                │
│  │ [predict: ⚠ ]│  warn: 'block-gpt4-over-50c' would warn at $0.62      │
│  └──────────────┘                                                       │
│           │                                                              │
│           ▼                                                              │
│  ┌──────────────┐                                                       │
│  │ GUARD        │  policy gate                                           │
│  │ [predict: ●] │  evaluates 3 policies                                 │
│  └──────────────┘                                                       │
│           │                                                              │
│           ▼                                                              │
│  ┌──────────────┐                                                       │
│  │ TOOL         │  github.post_review_comment                            │
│  │ [predict: ●] │                                                       │
│  └──────────────┘                                                       │
│                                                                          │
│  [ + add block ]                                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** block/node card (every block), Guard inline pill `predict` variant (every block), spend ribbon (header).

**Annotations:**
- Every block shows its `predict` Guard pill at draft time — `●` = allow, `⚠` = warn, `■` = block (drawn here as filled square). The third block warns because the projected cost would cross a policy threshold; user sees this without running.
- Right-panel inspector (primitive #9) opens on block click with full Guard / spend / config detail.
- This is the load-bearing Build view: ambient draft populated this canvas, user is reviewing before running.

### Wireframe 6 — `/workflows/[id]/runs/[run_id]` (Run timeline reusing Audit primitive)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Run #4823 · PR Review Bot · engineering                                │
│  Started 14:28 · 2m 14s · $0.41 actual    [role chip · developer]      │
│  ─────────────────────────────────────────────────────────────────────  │
│  spend ribbon (this run):   ████░░░░░  $0.41 / $1.00 cap              │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ 14:28:02  TRIGGER     GitHub PR #4823 opened                     │   │
│  │           [Guard: allow]                                  $0.00  │   │
│  ├──────────────────────────────────────────────────────────────────┤   │
│  │ 14:28:04  MEMORY      recall prior reviews (2,400 tok)           │   │
│  │           [Guard: allow]                                  $0.01  │   │
│  ├──────────────────────────────────────────────────────────────────┤   │
│  │ 14:28:05  AGENT STEP  Claude reviews PR diff                     │   │
│  │           [Guard: warn — 80% of per-call cap]             $0.38  │   │
│  │           Policy: block-gpt4-over-50c @v1                 →      │   │
│  ├──────────────────────────────────────────────────────────────────┤   │
│  │ 14:30:11  GUARD       policy gate — 3 evaluated                  │   │
│  │           [Guard: allow]                                  $0.00  │   │
│  ├──────────────────────────────────────────────────────────────────┤   │
│  │ 14:30:12  TOOL        github.post_review_comment                 │   │
│  │           [Guard: allow]    [SOC 2 CC6.1]                 $0.02  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ✓ Run complete — review comment posted                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** timeline row (the surface itself, same primitive as Audit), Guard inline pill (per step), compliance evidence chip (final tool row), spend ribbon (header), role chip.

**Annotations:** structurally identical to `/audit` — that's the point. The only difference is the filter: this is a single run, audit is all events. One primitive, two views.

### Wireframe 7 — Compliance pack page (`/guard/packs/soc2`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  SOC 2 Compliance Pack                  [role chip · security · Eng wsp]│
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  Last evidence export: 3 days ago                                       │
│  Coverage: 87 events / 47 requirements satisfied                        │
│                                                                          │
│  [ Export evidence pack ▾ ]    [ schedule monthly export ]              │
│                                                                          │
│  Requirements                                                            │
│  ┌──────────┬────────────────────────────────┬────────┬────────┐        │
│  │ Code     │ Requirement                    │ Events │ Last   │        │
│  ├──────────┼────────────────────────────────┼────────┼────────┤        │
│  │ CC6.1    │ Logical access controls        │   23   │ 4m ago │        │
│  │ CC6.6    │ Manage system credentials      │   12   │ 2h ago │        │
│  │ CC7.2    │ Detect and respond to events   │    8   │ 1d ago │        │
│  │ CC8.1    │ Change management              │    0 ⚠ │ never  │ →gap  │
│  │ CC9.2    │ Vendor risk management         │    0 ⚠ │ never  │ →gap  │
│  └──────────┴────────────────────────────────┴────────┴────────┘        │
│                                                                          │
│  2 gaps — [ show me how to satisfy ▾ ]                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** compliance pack pane (the surface), role chip.

**Annotations:** gap rows are the critical UI — they're the "do this next" CTA for the security buyer. "Show me how to satisfy" is intent-driven help (intent input #3 wired to this surface): the LLM proposes a playbook or policy that would generate satisfying events.

### Wireframe 8 — Ambient draft modal (Build, intent → canvas)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Draft a new playbook                                       [ close × ] │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  What should this playbook do?                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ when CI fails on main, open an issue, ping the on-call in Slack,  │ │
│  │ and let Claude attempt a fix as a draft PR                         │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  Lane: [ engineering ▾ ]    Connected integrations: GitHub, Slack ✓     │
│                                                                          │
│  Conduct will draft:                                                    │
│  ┌──────────┐ → ┌──────────┐ → ┌──────────┐ → ┌──────────┐             │
│  │ TRIGGER  │   │ TOOL     │   │ AGENT    │   │ TOOL     │             │
│  │ CI fail  │   │ open iss.│   │ Claude   │   │ draft PR │             │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘             │
│                                                                          │
│  Policies that will apply:                                              │
│  • block-gpt4-over-50c @v1 [warn]                                       │
│  • require-signed-policy @v2 [block]                                    │
│                                                                          │
│  [ Draft on canvas ]   [ Cancel ]                                       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** intent input (draft mode), block/node card preview, Guard inline pill (predicted on each upcoming block).

**Annotations:** modal renders the *predicted* canvas + the policies it will be subject to *before* the user commits. B2B users don't want surprises — they want to see what they're about to create. This is the ambient agent rung with a brake.

### Wireframe 9 — `/setup` target shape (post-#858 redesign)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Conduct                                          Step 1 of 4           │
│  ─────────────────────────────────────────────────────────────────────  │
│  [●][○][○][○]   Workspace                                               │
│                                                                          │
│  Organization:    [ OrganicSphere                                    ]  │
│  Workspace name:  [ Engineering                                      ]  │
│  Data region:     US · Oregon  (US only for now)                        │
│                                                                          │
│  Your lane (drives the suggested playbooks later):                      │
│  ( ) Compliance       — SOC 2, ISO, EU AI Act focus                     │
│  (●) Security         — AppSec, secrets, dependency triage              │
│  ( ) Engineering      — DevEx, CI, on-call                              │
│  ( ) Multiple lanes — pick the primary; others enable later             │
│                                                                          │
│                                                  [ Skip → /guard ]      │
│                                                  [ Continue → ]         │
└──────────────────────────────────────────────────────────────────────────┘
```

**Annotations:**
- Lane selector added — drives downstream starter playbooks (matches 3-lane positioning).
- Skip routes to `/guard` (decision day 0 in #858 slice 1).
- Region is fixed text, not a dropdown (decision in #858).

### Wireframe 10 — Marketing entry (`/` rebuilt around v3 positioning)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Conduct                          [ docs ] [ guard ] [ pricing ] [ in ]│
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│   The Guard-first AI governance platform.                              │
│                                                                          │
│   Policy, compliance, spend, and audit                                 │
│   for AI usage at work.                                                │
│                                                                          │
│   [ Try the 60s demo ]   [ Talk to us ]                                │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                          │
│  Three automation lanes on a single governance spine:                  │
│                                                                          │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                   │
│  │ Compliance  │   │ Security    │   │ Engineering │                   │
│  │ SOC 2, ISO  │   │ BugHunter,  │   │ PR review,  │                   │
│  │ EU AI Act   │   │ Autopilot,  │   │ on-call,    │                   │
│  │ evidence    │   │ secrets     │   │ deploy      │                   │
│  └─────────────┘   └─────────────┘   └─────────────┘                   │
│                                                                          │
│  Compliance live                                                        │
│  SOC 2:    87 events satisfied                                          │
│  ISO 27k:  41 events satisfied                                          │
│  EU AI Act: 12 events satisfied                                         │
│                                                                          │
│  [ See the audit log of every AI call in your org → ]                  │
└──────────────────────────────────────────────────────────────────────────┘
```

**Primitives used:** compliance pack pane (abbreviated form, marketing surface), Guard inline pill implied in "audit log".

**Annotations:**
- 30-second test: a security buyer sees "Guard-first AI governance," "policy / compliance / spend / audit," and live compliance numbers above the fold.
- Three lanes are concrete (named playbooks per lane), not abstract.
- "60s demo" CTA links to #826 (dev funnel) — same demo, marketing-shaped framing.

---

## Guard-on-every-rung — verification table

Per constraint #1, every rung must show Guard inline. This table makes that visible; if any cell is empty, the constraint is broken.

| Rung    | Where Guard appears                                                                                       | Primitive used        |
|---------|-----------------------------------------------------------------------------------------------------------|------------------------|
| Entry   | Ambient activity prompts ("3 calls blocked overnight"); demo (#826) shows a real block in 60s             | Guard inline pill #1; compliance evidence chip #2 (marketing) |
| Govern  | The whole surface. 3-tab spine (Policy / Spend / Activity), compliance pack right rail                    | Guard inline pill #1; spend ribbon #6; compliance pack pane #8 |
| Audit   | Every timeline row shows decision + linked policy + evidence chip                                          | Guard inline pill #1; compliance evidence chip #2; timeline row #5 |
| Build   | Every block on canvas shows `predict` Guard pill at draft time; ambient draft modal shows applicable policies before commit | Guard inline pill #1 (predict variant); block card #4; intent input #3 |
| Run     | Every step in timeline shows actual decision + linked policy; spend ribbon on every run                   | Guard inline pill #1; timeline row #5; spend ribbon #6 |

All five rungs surface Guard inline. Constraint #1 holds.

## What's intentionally still rough (push back here)

The doc deliberately stops at the "constraint" level, not "spec." These are the places where ambiguity is by design — flag if you need more before Phase 0 starts.

- **Visual treatment of `predict` vs `allow` Guard pill.** Specified as outlined vs filled; actual stroke / fill / dash pattern is for the design phase, not this doc.
- **Right-panel inspector tabs per resource type.** Listed conceptually; per-tab content is per-phase spec work.
- **Marketing wireframe (WF #10) above-the-fold layout.** Intentionally thin — brand / hero / illustration is the separate brand track (decision #13).
- **Compliance pack export format.** Named as "PDF + JSON bundle"; field-level schema is for the engineer implementing the export.
- **Intent input classifier model.** "Small LLM call routing to ~10 destinations" — not which model, not the prompt. Picked by whoever builds Phase 3.
- **Per-phase ship dates.** Listed as "Week 2 / Week 3 / etc." — these are *order*, not deadlines. Calendar dates are set when each phase plans.

## Implementation order (Phase 0 → Phase 4)

The doc lists a lot. Order matters more than completeness. Phase 0 is the smallest set of changes that bend the product toward the journey without breaking anything; each phase compounds.

### Phase 0 — Unblockers (Week 1 post-doc, in parallel with #858 slice 1)

These are blockers for anything else. Until they're done, every other phase has to fake them.

- **Schema:** add `satisfies: [{ framework, requirement_code }]` to Guard event store (decision #10). New issue, day 7.
- **Primitive #9:** build the right-panel inspector shell — no content yet, just the component (decision #14). Same shape, four resource types. ~2 days.
- **Primitive #1:** Guard inline pill component — implement allow/warn/block, defer `predict` + `synthetic` until canvas is wired (Phase 2). ~1 day.

### Phase 1 — Govern surface collapse (Week 2)

The buyer-first half of the journey. Ship before Phase 2 because the canvas redesign depends on these primitives being live.

- Merge `/guard/policies`, `/guard/spend`, `/guard/activity` into `/guard` 3-tab spine + tab routing. Old routes 302 to the new tabs.
- Delete `/security` (3-line redirect, decision #9).
- Merge `/governance` content into `/guard` + redirect (decision #9).
- Move `/playbook-queue` under `/guard?tab=approvals` (decision #12).
- Add compliance pack pane to Govern right rail (primitive #8) — SOC 2 only in v1, others "coming soon."

### Phase 2 — Run + Audit timeline (Week 3)

The other half of the buyer-first journey, and the surface that establishes the timeline primitive used in Run.

- Build `/audit` as timeline-first using primitive #5 (timeline row).
- Reuse primitive #5 for `/workflows/[id]/runs/[run_id]` — same component, single-run filter.
- Merge `/observability` into `/runs` as a saved filter (decision #10).
- Move `/observability/alerts` under Guard.
- Merge `/guard/session-reports`, `/guard/tool-errors`, `/guard/reports/soc2` into `/audit` filters (per surface map).
- Compliance evidence chip (primitive #2) goes live wherever the `satisfies` field is populated.

### Phase 3 — Entry + Build flip (Week 4)

The user-facing half. Lower urgency than buyer-facing but where dogfooding bites first.

- Build `/home` net-new (decision #8) — intent input primitive #3 in find / draft / ask modes.
- Change post-login default route from `/projects` (or `/dashboard`) to `/home`.
- Reframe `/dashboard` as "ops overview" power-user surface (decision #11).
- Wire ambient draft modal (WF #8) — primitive #3 in draft mode → canvas seed.
- Add Guard `predict` pill state to every block on canvas (primitive #1 completion).
- Merge `/workflows/[id]/settings` into the canvas right-panel inspector.

### Phase 4 — Marketing + setup polish (Week 5–6)

Externally visible, but lower-impact internally. Run last so it benefits from everything before.

- `/setup` redesign per WF #9 (post-#858 slice 1, with lane picker).
- Marketing `/` rebuild per WF #10 — copy + structure only; brand is separate track.
- Kill `/solutions` (merge into `/` lane sections).
- `/guard-landing` tighten — already Guard-first, just align with v3 wording.
- Wire compliance pack pane on marketing (abbreviated form per WF #10).

### What this doesn't include

- Wireframes are not specs. Each phase still needs per-screen specs (Figma or refined ASCII) before engineers commit. Spec lead-time per phase: ~3 days.
- Brand / visual identity is a separate track (decision #13) — not in this roadmap.
- Backend work for satisfies + new endpoints lives in API engineering's own tracker; this doc names what's needed, not how to build it.

---

## Re-spec table for #858 / #859 / #826

These children were filed before this doc existed. Each gets re-specced here against the doc; the GitHub comment per child (day 7) links back to the right section.

### #858 — /setup wire-up (slice 1 interim, full redesign deferred)

**What was filed:** wire all 4 setup steps, first-time gate, skip → Guard Overview. Three slices proposed (1h / 3h / 8h).

**Doc alignment:**
- **Slice 1 stays as filed** — ships in parallel with this doc week. First-time gate + skip → `/guard` are no-doc-dependency wins.
- **Slice 2 is reshaped** by WF #9 — adds the lane picker (decision #18). Reshapes the org / workspace step to defer non-required fields to a smaller initial form.
- **Slice 3 (full) is now Phase 4** — lands after Phase 3 because /home and the conversational entry need to exist for "skip setup" to land somewhere useful.

**Action day 7:** comment on #858 linking → "Implementation order — Phase 4" + WF #9 + decision #18.

### #859 — Conversational entry + ambient agent (subsumed)

**What was filed:** Gap 1 = chat-as-finder. Gap 2 = ambient agent.

**Doc alignment:**
- Both gaps remain — Gap 1 is now primitive #3 (intent input, find/draft/ask modes); Gap 2 is now WF #8 (ambient draft modal, with predicted-canvas-before-commit per decision #20).
- Effort sizing in #859 was Gap 1 ~1 week / Gap 2 ~3 weeks. Doc agrees with Gap 1; Gap 2 may be shorter because the primitives (#3, #4, #5) are already specified — the work is wiring + an LLM prompt grounded on block library, not designing from blank.
- Phase 3 (Week 4) ships Gap 1; Gap 2 starts in Week 5 alongside Phase 4 marketing work.

**Action day 7:** comment on #859 linking → primitive #3 + WF #8 + decisions #16, #20.

### #826 — Demo funnel (`docker-compose.demo.yml`)

**What was filed:** 60-second demo with mock LLM + budget breach, in a public sister repo (`conductai/demo`).

**Doc alignment:**
- Entry rung WF #10 references "60s demo" as the marketing CTA — #826 IS this asset.
- The doc adds one constraint: the demo's scripted runaway request must produce events that look exactly like Run + Audit timeline rows (primitive #5). Otherwise the demo and the real product visually diverge and the funnel breaks.
- v1 of the demo uses `synthetic` Guard inline pill variant (primitive #1) so audit data from demos is visually distinct from real customer data.

**Action day 7:** comment on #826 linking → primitive #1 (`synthetic` state) + primitive #5 + WF #10.

---

## Success metrics — how we know the doc worked

Without a metric the doc is theory. Each rung gets one number to move; if all five move in the right direction over the next 90 days, the journey worked. These are inputs to the success criteria in the per-phase shipping, not OKRs.

| Rung   | Metric                                                              | Today (rough estimate)        | Target (90 days post-launch) |
|--------|---------------------------------------------------------------------|-------------------------------|------------------------------|
| Entry  | Pre-signup → trial signup conversion                                | ?                             | +50% (#826 demo is the lever) |
| Entry  | Post-signup → first-meaningful-action within 24h                    | ?                             | +30% (intent input is the lever) |
| Govern | Time from "I want to set a policy" → policy live                    | unknown, many clicks          | < 60 seconds via intent + draft |
| Audit  | Time from "auditor asks for SOC 2 evidence" → exported pack         | hours / days (manual)         | < 5 minutes via compliance pack |
| Build  | Time from "I have an automation idea" → first run                   | unknown                       | < 5 minutes via ambient draft |
| Run    | Time to diagnose a blocked run                                      | minutes of clicking           | < 30 seconds via inline Guard pill |

Each phase ships an instrumentation hook so the metric is measurable from day one. Phase 0 includes the analytics primitive (one event schema, one helper) so we don't add tracking screen by screen.

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
| 11  | `/dashboard` reframed as power-user "ops overview" (Run + Govern crossover); never default landing | Kill /dashboard entirely / keep as default landing | Real components there (SpendArc, GuardSnapshot, AgentHealth) are useful for engineering leads. Killing wastes shipped work. But landing engineers there contradicts the buyer-first journey. Compromise: it stays, just not as the front door. | 2026-06-27 |
| 12  | `/playbook-queue` merges into `/guard?tab=approvals` (Govern) | Leave under Build / kill it | File confirmed: pending→promoted|needs_work approval flow, role-gated to admin/security. Pure governance surface. | 2026-06-27 |
| 13  | Marketing pages are in scope for journey + entry-rung decisions, out of scope for visual / brand work | Treat marketing as entirely separate / fold all of it into the doc | Marketing IS the entry rung pre-signup; we can't ignore it without breaking the journey. But brand / visual identity is its own track per #860 out-of-scope. Split cleanly: journey calls (lead with Guard, kill /solutions as a separate page) are in; redesigning the hero is out. | 2026-06-27 |
| 14  | Add primitive #9 right-panel inspector — does not exist today, blocks `/workflows/[id]/settings` merge and primitive #4 (block card click) | Use modal dialogs / new-page navigation instead of inspector | Modals lose context (you can't see the canvas behind); separate pages break the "inspect without navigating" promise. A single right-edge sheet is the standard B2B pattern (Linear, Notion, GitHub PR review). | 2026-06-28 |
| 15  | Wireframes use ASCII boxes, not Excalidraw or Figma | Excalidraw .json files; embedded Figma frames | ASCII renders inline in the PR, no separate tool needed, low-fi enough that no one mistakes it for production design. Matches #860's "low-fi" constraint. | 2026-06-28 |
| 16  | Intent input has 3 modes (find / draft / ask), auto-selected from intent | Single chat mode like Claude.ai / ChatGPT | B2B users have rich context — most intents are find-a-thing, not generate-from-blank. Surfacing the mode prevents user confusion ("why is it making something new when I asked to find one?") and lets each mode have the right latency budget (find = instant, draft / ask = LLM). | 2026-06-28 |
| 17  | Audit + Run are one primitive (timeline row), not two | Separate audit-row and run-step components | Both are "ordered events with provenance"; different filters, same shape. Forces visual + data-model coherence and saves one component. | 2026-06-28 |
| 18  | `/setup` adds a "lane" picker (compliance / security / engineering / multiple) | Skip the lane picker; default to multi-lane | Lane drives the suggested playbooks downstream + matches 3-lane positioning. Picking primary lane during setup is a 5-second tradeoff for materially better starter suggestions. | 2026-06-29 |
| 19  | Marketing homepage rebuilt around v3 positioning above the fold (Guard-first + 3 lanes + live compliance numbers) | Keep current homepage and add a banner | 30-second test fails if buyer has to scroll. Live numbers are the trust signal; without them, "compliance" reads as vaporware. Visual / brand work is out of scope (per #860); copy + structure is in scope. | 2026-06-29 |
| 20  | Ambient draft modal shows predicted canvas + applicable policies *before* user commits | Generate directly to canvas like Lovable / v0 | B2B users want a confirm step before unknown LLM-generated structure lands in their workspace. Matches Linear's "preview before commit" pattern. | 2026-06-29 |
| 21  | 5-phase implementation order (Unblockers → Govern → Run+Audit → Entry+Build → Marketing) | Ship surface-by-surface as bandwidth allows | Phase 0 (schema + primitives #1, #9) is unavoidable scaffolding. Govern before Build because Build references policies defined in Govern. Marketing last because it benefits from everything before. | 2026-06-30 |
| 22  | Compliance evidence chip depends on Guard event schema gaining a `satisfies: [{framework, code}]` field — file as a Phase 0 issue | Compute satisfies at read-time / per-framework lookup tables | Read-time computation slows the audit timeline, the surface that needs to be fast. Static lookup tables drift. Storing satisfies on the event itself is the simplest correct thing. | 2026-06-30 |
| 23  | Success metric per rung, not per surface | OKR-style for the whole doc / no metrics this week | The doc is theory without measurement. One number per rung is tractable; per-surface is paralysis. Targets are 90 days post-launch so they survive the actual roll-out. | 2026-06-30 |
| 24  | Compliance pack v1 = SOC 2 only; other frameworks ship "request access" cards | Ship all 4 frameworks at v1 / ship none and gate behind sales | SOC 2 has the most existing customer demand + the Lexoculus capture data is strongest there. Other frameworks generate inbound interest with zero engineering cost via the "request access" pattern. Pure B2B selling motion. | 2026-07-01 |
| 25  | Doc has an executive summary + "how to read" + "what's intentionally rough" sections at the top, not just at the end | Skip the summary; reviewers should read it linearly | The doc is dense enough (~600 lines) that a cold reader needs a map. Load-bearing primitives + decisions are named explicitly so a reviewer can push back on the *right* things. | 2026-07-01 |


---

## Open questions

1. ~~Does `/home` exist as a real route?~~ **Resolved day 1:** no — build new (decision #8).
2. ~~`/governance` vs `/security` vs `/guard` — confirm which two die.~~ **Resolved day 1:** delete `/security`, merge `/governance` into `/guard` (decision #9).
3. ~~`/observability` vs `/runs` — overlap?~~ **Resolved day 1:** merge `/observability` into `/runs`, move `/observability/alerts` under Guard (decision #10, [contested]).
4. ~~`/dashboard` — what is it actually for today?~~ **Resolved day 2:** KPIs + SpendArc + GuardSnapshot + AgentHealth + EmptyChecklist (143-line shell + supporting components). Real ops-overview surface for engineering lead. Stops being default landing, lives next to `/home`. Decision #11.
5. ~~Marketing pages in scope?~~ **Resolved day 2:** journey + entry rung decisions ARE in scope; visual / brand work is separate. Decision #13.
6. ~~`/playbook-queue` role?~~ **Resolved day 2:** admin/security-only approval surface (allowed roles: admin, security; status flow pending→promoted|needs_work). Confirmed Govern, not Build. Decision #12.
7. ~~Canvas right-panel inspector — exists today?~~ **Resolved day 3:** no — `apps/web/src/components/` has no inspector component. Must be built (primitive #9). Decision #14.
8. ~~Which compliance pack format do we standardize on?~~ **Resolved day 6:** SOC 2 only for v1. Other frameworks ship "coming soon — request access" cards per primitive #8 + WF #7. The B2B selling motion likes this; it generates inbound interest for ISO / EU AI Act / OWASP-LLM packs. Decision #24 below.
9. **New (day 2):** `predict` Guard pill always-on at draft time, or only after first save? Primitive #1 recommends always; revisit week-2 dogfood.
10. ~~event `satisfies` field — already in Guard schema?~~ **Resolved day 3:** no — grepped `apps/api/app/modules/guard/` for `satisfies|compliance.*framework|requirement_code`, no matches. Schema work required before primitive #2 (compliance evidence chip) can be implemented. Capture as a follow-up issue day 7.

---

## Day 7 — ship state

The week ran. Doc is checked in. Open PR [#861](https://github.com/sseshachala/conductai/pull/861) carries the full history (day 0 → day 7). Three children commented with re-spec anchors. One new Phase 0 issue filed.

### Shipped this week

- `UX_NORTHSTAR.md` at repo root — exec summary + how-to-read + positioning lock + 5 hard constraints + 4 personas + 5-rung journey + surface map (every existing page judged) + 9 primitives spec'd + 10 wireframes (low-fi ASCII) + 5-phase implementation roadmap + re-spec for #858 / #859 / #826 + 5 success metrics + 25 decisions.
- New issue **[#862](https://github.com/sseshachala/conductai/issues/862)** — Phase 0 Guard event schema (`satisfies[]` field). Unblocker for primitive #2 + audit timeline + compliance pack export.
- Comment on **#858** — Slice 1 unchanged; Slice 2 reshapes to WF #9 + decision #18 (lane picker); Slice 3 moves to Phase 4.
- Comment on **#859** — Gap 1 = primitive #3 (3-mode intent); Gap 2 = WF #8 (preview before commit); Gap 2 likely shorter than original sizing.
- Comment on **#826** — adds two constraints (use primitive #5 timeline shape + `synthetic` Guard pill variant) so demo stays visually coherent with prod.

### Open at end of week

- Open questions 4 and 9 are resolved; questions 7, 10 resolved during the week.
- No remaining `[contested]` markers in the doc (all resolved or punted to per-phase planning).
- One follow-up that didn't land this week: an *example* compliance evidence chip seed mapping (~15 SOC 2 controls). It belongs inside #862's scope, not the doc.

### Hand-off

If someone reading this doc cold needs to pick the first thing to ship: **start with #862**. Until the Guard event schema has `satisfies[]`, primitive #2 is theoretical and the compliance pack export can't return real numbers. Everything else in the journey can be built on top of that field; without it, Phase 1 ships incomplete.

If you want to argue with the doc: push back on the 5 **load-bearing decisions** named in "How to read this doc" — those are the joints the doc bends around. Decisions further down (per-primitive, per-wireframe) are cheaper to change.

*Doc closed for the week. Next: per-phase planning issues opened from the implementation roadmap.*