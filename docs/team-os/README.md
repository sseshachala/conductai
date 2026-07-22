# Team OS — The Foundation Layer for AI-Assisted Development

Three files. Any team. Any stack. No account required.

```
your-repo/
├── CLAUDE.md        ← What the agent knows about your project
├── REVIEW.md        ← What "done" means on your team
└── standards/       ← How your team does specific things
    ├── auth.md
    ├── security.md
    └── migrations.md
```

This is Layer 0. Copy it, commit it, customise it.

---

## Why three files?

Most teams that struggle with AI-assisted development have the same problem: the agent finishes the task to *its* standard, not yours. It doesn't know your auth pattern. It doesn't know your migration hygiene. It doesn't know what your senior engineer would push back on in review.

These three files fix that. They move the knowledge out of someone's head and into the repo, where agents can read it.

**CLAUDE.md** — project memory. The agent reads this first. It tells the agent what the codebase does, what patterns to follow, what to never do.

**REVIEW.md** — the quality gate. Before the agent declares work done, it checks every item here. This is your senior engineer's review checklist, written down.

**standards/** — the playbook. How your team handles specific situations: auth, security, database migrations, naming. Agents reference these when the work touches those areas.

---

## The two-layer model

```
Layer 0: Team OS          Layer 2: Conduct AI
─────────────────         ───────────────────
CLAUDE.md           →     Guard enforces it in real-time
REVIEW.md           →     Security Loop catches what slips through
standards/          →     Audit trail shows every decision
```

**Layer 0** is where you start. It's free, it's yours, and it works with any AI coding tool — Claude Code, Cursor, Copilot, anything that reads files.

**Layer 2** is where you go when markdown alone isn't enough. When you need to enforce standards across a team, not just remind one agent. When you need to know what every AI tool did, blocked, or allowed — with a log that holds up in a security review.

The path: write it down (Layer 0) → enforce it automatically (Layer 2).

---

## Get started in 10 minutes

**1. Copy the templates into your repo**

```bash
# From the Team OS repo
cp CLAUDE.md.template your-repo/CLAUDE.md
cp REVIEW.md your-repo/REVIEW.md
cp -r standards/ your-repo/standards/
```

**2. Fill in CLAUDE.md**
Open `CLAUDE.md` and replace every `{{ }}` with your project's specifics. Start with: what does this codebase do, what auth pattern do you use, what should the agent never touch.

**3. Customise REVIEW.md**
Cut any sections that don't apply to your stack. Add sections for your specific patterns. The right REVIEW.md is the one your team will actually run through every PR.

**4. Wire the first automated check**
Pick one item from your REVIEW.md and automate it in CI. Auth coverage is a good first choice — there's a reference implementation in `standards/auth.md`.

**5. Commit everything**
These files belong in git. They're reviewable, versioned, and discoverable — by humans and agents.

---

## Adopt the progression

| Week | Action | What changes |
|---|---|---|
| 1 | Commit CLAUDE.md + REVIEW.md | Agents have context and a quality bar |
| 2 | Add to CLAUDE.md: "Check REVIEW.md before declaring done" | Agents self-review before finishing |
| 3 | Automate one CI gate (auth, tests, lint) | Structure enforced without a reviewer's memory |
| 4 | Retro: which items caught real bugs? Cut noise, add misses | Checklist gets better every sprint |
| Ongoing | Every production bug → add the check that would have caught it | Gate compounds over time |

---

## Contribute

Found something missing? Disagree with an approach? Open a PR.

The goal is a foundation layer any team can adopt and improve — not a checklist that only works for one company's stack.

`conductai.ai/team-os` · Free for individuals · Commercial license required for companies — conductai.ai/team-os/license

---

## When Layer 0 isn't enough

Layer 0 works on the honour system. Agents read the files and try to follow them. Humans check the PR.

Layer 2 (Conduct AI) is enforcement:
- **Guard** intercepts every AI tool call and checks it against your standards before it runs
- **Security Loop** scans every PR and triggers automatic fixes for critical findings
- **Audit trail** gives you a log of every AI action, every policy decision, every block — timestamped and attributable
- **Multi-workspace governance** applies standards across teams, not just repos

`conductai.ai` · Start free

