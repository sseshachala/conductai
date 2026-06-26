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
- The other Govern tabs (Spend, Activity, Approvals) follow the same shell; specs come in day-4 wireframes.

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


---

## Open questions

1. ~~Does `/home` exist as a real route?~~ **Resolved day 1:** no — build new (decision #8).
2. ~~`/governance` vs `/security` vs `/guard` — confirm which two die.~~ **Resolved day 1:** delete `/security`, merge `/governance` into `/guard` (decision #9).
3. ~~`/observability` vs `/runs` — overlap?~~ **Resolved day 1:** merge `/observability` into `/runs`, move `/observability/alerts` under Guard (decision #10, [contested]).
4. ~~`/dashboard` — what is it actually for today?~~ **Resolved day 2:** KPIs + SpendArc + GuardSnapshot + AgentHealth + EmptyChecklist (143-line shell + supporting components). Real ops-overview surface for engineering lead. Stops being default landing, lives next to `/home`. Decision #11.
5. ~~Marketing pages in scope?~~ **Resolved day 2:** journey + entry rung decisions ARE in scope; visual / brand work is separate. Decision #13.
6. ~~`/playbook-queue` role?~~ **Resolved day 2:** admin/security-only approval surface (allowed roles: admin, security; status flow pending→promoted|needs_work). Confirmed Govern, not Build. Decision #12.
7. ~~Canvas right-panel inspector — exists today?~~ **Resolved day 3:** no — `apps/web/src/components/` has no inspector component. Must be built (primitive #9). Decision #14.
8. Which compliance pack format do we standardize on for `/audit?pack=*` export? SOC 2 is row one; EU AI Act + ISO 27001 next (per Lexoculus capture). Spec'd in primitive #2 above (v1 priority list). **Confirm day 5** when re-spec'ing #858/#859/#826.
9. **New (day 2):** `predict` Guard pill always-on at draft time, or only after first save? Primitive #1 recommends always; revisit week-2 dogfood.
10. ~~event `satisfies` field — already in Guard schema?~~ **Resolved day 3:** no — grepped `apps/api/app/modules/guard/` for `satisfies|compliance.*framework|requirement_code`, no matches. Schema work required before primitive #2 (compliance evidence chip) can be implemented. Capture as a follow-up issue day 7.

---

*End of day 3. Next: day 4 — wireframes 3–10 (Build canvas, Run timeline, Audit timeline, compliance pack page, ambient draft modal, /setup target, marketing entry).*