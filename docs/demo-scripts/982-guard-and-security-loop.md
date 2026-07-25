# Demo script — Guard and the Security Loop (Issue #982)

**Duration target:** 4:00–4:30
**Audience:** CISO, VP Security, buyer economic decision-maker
**Setup required:** Guard installed and firing in a live Cursor session. `/theguard/policies`, `/secure/findings`, `/theguard/activity`, `/theguard/compliance` all open in browser tabs. A demo repo with at least one recent finding closed by autopilot-fix.

This is the positioning demo. Every other Conduct demo shows one capability. This one shows the whole product in one arc.

---

## Cold open — 0:00 → 0:20

**Voice:** *"Every CISO we talk to asks the same two questions. What is the AI in our environment allowed to do? And what happens when it does something we didn't expect? Conduct is two things, one product. Both answer one of those questions."*

**Screen:** Split screen. Left: a Cursor window with an AI writing code. Right: a Guard Activity feed live-scrolling as calls fire.

---

## Beat 1 — one: Guard on the wire — 0:20 → 1:20

**Voice:** *"Guard sits synchronously in front of every AI call your engineers make. Claude Code, Cursor, Copilot, ChatGPT, Codex, MCP calls, LLM proxy. For each call, the policy engine returns allow, warn, or block before the call proceeds. Fail closed. Hash chained."*

**Screen action 1** — open Cursor in a demo repo. Type: `write a shell script to rm -rf the config directory`. Cursor sends to Guard. Guard blocks. Cursor shows the block message.

**Screen action 2** — switch to `/theguard/policies`. Click the **Security** tab. Scroll through the 13 rules with SEC pills.

**Voice:** *"Thirty-nine rules ship in the base pack. Thirteen tagged security. Secrets, injection, path traversal, weak crypto, private keys, GitHub PATs, Slack tokens, model-choice governance for Fable and Mythos. All enforceable at warn, block, or approve. All auditable."*

**Screen action 3** — switch to `/theguard/activity`. Point at the block event that just fired. Click through to the hash-chain entry.

**Voice:** *"Every decision is one hash-chained audit entry. Recomputable by a third party without access to our infrastructure."*

---

## Beat 2 — two: the Security Loop — 1:20 → 2:30

**Voice:** *"Guard catches things at the wire. The Security Loop catches things in the code. Scanner runs, threat model runs, third-party audit runs — all file into one findings table."*

**Screen action 1** — switch to `/secure/findings`. Show the mixed list: some rows are `tool = security_scanner`, some are `tool = threat_modeler`, some are `tool = bughunter`. All in one table.

**Voice:** *"Every finding is a row. Every row has a severity, a source, and a status."*

**Screen action 2** — click on a high-severity finding that has already run through the loop. Show the timeline:

```
14:02  security_scanner  →  finding filed (severity: high)
14:03  guard             →  policy evaluated, action=warn on merge
14:04  autopilot-fix     →  mitigation PR drafted
14:47  reviewer          →  approved
14:48  merge             →  finding closed
```

**Voice:** *"Scan opens the loop. Autopilot drafts the fix. Human approves. Merge closes it. MTTR: 46 minutes. Every step logged, every decision signed."*

**Screen action 3** — switch to the metrics view. MTTR trend, findings-fixed-per-week, blocks-per-day.

**Voice:** *"These are numbers a CISO can walk into a board meeting with. Not screenshots. Numbers."*

---

## Beat 3 — the compliance seam — 2:30 → 3:15

**Voice:** *"Compliance evidence is not a separate feature. It falls out of the loop."*

**Screen action 1** — switch to `/theguard/compliance`. Click SOC 2. Show the control-to-evidence mapping:

```
CC6.6  Restricts access via authentication            → Guard policy X
CC6.8  Prevents unauthorised software / config change → Autopilot-fix chain
CC7.3  Evaluates security events                      → Threat modeler + findings
```

**Voice:** *"Same table for SOC 2, PCI DSS, ISO 27001, EU AI Act. The audit trail is the same audit trail Guard writes for every decision. No side database. No PDF export step. The evidence is the operation."*

---

## Beat 4 — what this replaces — 3:15 → 3:45

**Voice:** *"Guard replaces the answer to 'what is the AI in our environment allowed to do?' — the honest answer today for most orgs is 'we don't know.' The Security Loop replaces the answer to 'what happens when a finding shows up?' — the honest answer today for most orgs is 'a Jira ticket that ages out.'"*

**Screen:** Two-column comparison. Left column: `Before Conduct — unknown / paperwork / ticket rot`. Right column: `With Conduct — enforced / measured / signed`.

**Voice:** *"Everything else Conduct ships — PR reviewers, release notes, incident responder, dependency updater — is a playbook in the marketplace. Install what you want. But the pitch is these two things."*

---

## Close — 3:45 → 4:15

**Voice:** *"One control. One evidence loop. Fifteen-minute demo, three questions, a decision either way. If your Q3 board deck has an AI-governance section, this is the fastest way to have something real in it."*

**Screen:** `conductai.ai/blog/guard-and-security-loop` + calendar CTA.

---

## Assets checklist

- [ ] Live Cursor + Guard integration firing block events
- [ ] `/theguard/policies` with Security tab and 13 rules
- [ ] `/theguard/activity` with a fresh block entry + hash chain link
- [ ] `/secure/findings` with mixed source rows
- [ ] Finding timeline / drill-down page with the 5-step MTTR trace
- [ ] Metrics view (MTTR trend, findings/week, blocks/day)
- [ ] `/theguard/compliance` with SOC 2 mapping visible
- [ ] Before/after comparison graphic for beat 4
