# Conduct AI — Products

## The two-layer model

Most teams jump straight to AI coding tools and wonder why quality regresses. The answer is always the same: the agent doesn't know your standards, and nothing enforces them when it gets them wrong.

Conduct solves this in two layers.

---

## Layer 0 — Team OS

**Free. Open source. Works with any AI coding tool.**

Three files that give every agent on your team the same context a senior engineer carries in their head.

| File | What it does |
|---|---|
| `CLAUDE.md` | Project memory — architecture, patterns, what to never do |
| `REVIEW.md` | The quality gate — what "done" means on your team |
| `standards/` | The playbook — auth, security, migrations, naming |

Commit these to your repo. Tell your agents to read them before starting any task. That's Layer 0.

**What it solves:** Agents finishing work to their standard, not yours. Non-engineers shipping code that looks right but breaks quietly. Review comments repeating the same things every PR.

**What it doesn't solve:** Agents that ignore the files (it works on the honour system). Standards drift across a team. Real-time enforcement before code is written.

→ **[Get the templates](https://conductai.ai/team-os)** — Free for individuals · commercial license for companies

---

## Layer 2 — Conduct AI

**Enforcement, audit, and governance at scale.**

Layer 0 tells agents what to do. Layer 2 makes sure they do it — and gives you the log that proves it.

### Guard — real-time enforcement

Guard sits in front of every AI tool call on your team. Before any agent reads a file, writes code, or calls an API, Guard checks the action against your policies.

- Blocks disallowed actions before they happen — not after review
- Applies your standards in real-time, not at PR merge
- Works across Claude Code, Cursor, Copilot, any tool that uses an LLM
- Timestamped audit log of every decision: allowed, blocked, or warned

Your REVIEW.md says "never concatenate user input into SQL." Guard enforces it on the spot.

### Security Loop — automated vulnerability scanning

Every PR gets scanned against OWASP Top 10, secret detection, and your custom rules. Critical findings don't just get reported — they trigger Autopilot to fix them.

- Scans changed lines only — no noise from unchanged code
- Posts findings as a structured PR review comment with severity, file/line, and suggested fix
- Critical findings automatically create a fix issue labeled for Autopilot
- Findings feed into `/secure/activity` — one place to see all vulnerabilities across all repos

Your REVIEW.md says "check for SQL injection." Security Loop checks it on every PR, automatically.

### Audit trail — what every agent did

A tamper-evident log of every AI action across your workspace: what was attempted, what was allowed, what was blocked, what ran and for how long.

- Know exactly what changed and what tried to change but couldn't
- Attribution: which agent, which user, which workflow
- Exportable for compliance reviews and security audits

### Multi-workspace governance

Apply your Layer 0 standards across teams, not just repos. Set policies once, enforce them everywhere.

---

## The path

```
Week 1   Copy Team OS → agents have context and a quality bar
Week 2   Add first CI gate → structure enforced automatically
Month 1  Add Conduct Guard → enforcement moves from PR to real-time
Month 2  Enable Security Loop → every PR scanned, critical findings auto-fixed
Month 3  Full audit trail → you can prove what every agent did
```

You don't need Layer 2 on day one. Start with Layer 0. When the markdown files aren't enough — when you're managing a team, not a repo, and you need enforcement not reminders — Layer 2 is ready.

---

## Pricing

**Layer 0 — Team OS:** Free for individuals and small teams (< 10 people). Commercial license required for larger organisations.

**Layer 2 — Conduct AI:** [conductai.ai/pricing](https://conductai.ai/pricing)

---

## Built on our own standards

Every change to Conduct AI goes through the same REVIEW.md we publish here. The auth coverage check that gates our CI, the security scanner that reviews our own PRs, the audit trail that logs our own agent runs — we ship under the standards we publish.

That's not a marketing line. It's the only honest way to sell a quality gate.
