# Conduct AI — Moat-Building Spec
**v0.1 · May 24, 2026 · Houston**

---

## TL;DR

In 2026, a Claude-generated SaaS can clone any single feature in a weekend. Moats are no longer features — they're **compounding positions** built from things that individually look weak but stack into something hard to replicate over 12–24 months. For Conduct, that stack is six layers: run-data flywheel, eval harness + public benchmark, community marketplace, integration depth, distribution footprint, and trust/compliance. This spec lays out what to build in each, in what order, with real budget, real timelines, and the anti-patterns to avoid.

The thesis in one line: **stop building features, start building accumulators.**

---

## 1. Where We Are (May 2026)

**What exists today:**
- 11 pre-built playbooks shipped, MIT-licensed, config-as-code
- GitHub, Slack, PagerDuty, OpsGenie integrations
- Slack approval gates as first-class blocks
- Ephemeral Modal sandboxes per run
- AES-256-GCM credential vault
- Event-sourced audit trail per run
- CLI for terminal/CI triggering
- Auth via Google, GitHub, Microsoft
- Marketing site at conductai.ai, blog hosted under narratr.ai
- Early-access status (no paid tier surfaced yet)

**What's missing from the moat stack:**
- No eval harness, no public benchmark, no per-playbook quality scores
- No online run scoring or fixture-promotion loop
- Marketplace exists as a catalog, not as a publishing surface for community
- No cross-tenant analytics layer (per-tenant audit trail only)
- No GitHub Marketplace / Slack App Directory listings
- No compliance certification path published (SOC 2, etc.)
- No quarterly content cadence — blog is sporadic

**Read of the position:** the product foundation is solid; the **accumulation infrastructure** is not yet built. The next 12 months are about pivoting build cycles from feature additions to accumulator construction.

---

## 2. Strategic Frame

### Why features aren't moats anymore

A feature is replicable in a weekend by anyone with Claude Code and an API key. RBAC, multi-tenant, templates, observability dashboards — all table stakes, none defensible. The naive response is to keep building more features. The strategic response is to **change what you're optimizing for**.

### What compounds

| Doesn't compound | Compounds |
|---|---|
| A feature shipped | A fixture added to the eval suite |
| A landing page | A blog post that ranks for an evergreen query |
| A pricing tier | A SOC 2 audit completed |
| A new integration | A community-contributed playbook |
| A dashboard | A customer that's been on for 18 months |

The right test for any roadmap item: *"Does this asset get more valuable next quarter just by existing, or does it depreciate the moment a competitor copies it?"*

### The accumulation thesis

Build six layers in parallel, all of them accumulating. None is a moat alone. Stacked, they make the 18-month-from-now version of Conduct uncloneable even if a competitor's v1 looks identical to today's Conduct.

---

## 3. The Six Compounding Layers

### Layer 1 — Run Data Flywheel

**What:** Every agent execution (offline eval + online production) produces structured outcome data: prompt, model, tool calls, output, human verdict (approved/rejected in Slack), downstream signal (PR merged, alert resolved, issue triaged correctly). This data is the raw material for every other moat.

**Why it compounds:** A clone has zero on day one. After 12 months you have hundreds of thousands of labeled outcomes. After 24 months, you have something that funds model-routing decisions, quality benchmarks, and an analytics product nobody else can build.

**What to build:**
- `run.completed` event emitted from every agent run with full trace
- Online eval worker that scores each run (sampling: 100% deterministic checks, 20% LLM-as-judge, 100% when humans approve/reject)
- Anonymization pipeline (strip PII, regenerate identifiers, reduce to minimal repro)
- Fixture-promotion queue: low-scoring runs and human-disagreement runs surfaced for review and addition to the offline eval suite

**Success metric:** Cumulative scored runs in the data store. Target: 100K by Q1 2027, 500K by Q4 2027.

---

### Layer 2 — Eval Harness + Public Benchmark

**What:** Two systems, intentionally separate:
1. **Offline (fixture-based)** — synthetic test cases committed to git, run on cron/CI/model release. Catches regressions before they reach users.
2. **Online (production)** — triggered by `run.completed`, scores real runs in the wild. Feeds Layer 1.

Both share an LLM-as-judge runtime, scoring conventions, and a common results schema. The offline suite is the visible artifact; the online system is the data engine.

**Why it compounds:** The eval framework itself is replicable (OpenAI Evals, Promptfoo, Inspect, Braintrust exist). What's not replicable is the **fixture pool** that grows from real production cases over time, and the **public benchmark** that becomes the citable artifact for "Claude vs GPT-5 for AI code review."

**What to build:**

*Eval harness:*
- `playbooks/<name>/evals/` directory structure: `fixtures/`, `graders/`, `baselines/`, `config.yaml`
- 4-model coverage: Haiku 4.5, Sonnet 4.6, Opus 4.7, GPT-5 (rationale: cheap/mid/premium/non-Anthropic)
- Per-model prompt adapters in `prompts/`: canonical + anthropic + openai + google variants
- Three-tier scoring: deterministic (precision/recall against must-flag/must-not-flag) + LLM-judge (rubric) + budget (cost/run, p95 latency)
- Baselines committed to git as JSON — score changes become reviewable PR diffs
- CLI: `conduct eval <playbook> [--model X] [--compare] [--publish]`
- Minimum bar to publish a playbook: 20 fixtures including 5+ negative cases, baselines for 2+ models, defined budget

*Public benchmark:*
- Quarterly editions at `/benchmark/2026-q2/`, etc.
- Leaderboard: 11 playbooks × 4 models, with recommended-model highlighted per row
- Editorial findings section: 3–5 notable changes per edition
- Deep-dive per playbook (start with Security Scanner)
- Methodology section linking to the open-source eval repo
- Per-edition diff page on subsequent releases for SEO around new-model launches

**Success metric:** Public benchmark cited by 5+ external sources within 12 months of Edition 001. All 11 playbooks have evals with ≥20 fixtures each.

---

### Layer 3 — Community Marketplace

**What:** Open marketplace publishing so users can contribute playbooks (and fixtures), not just consume the 11 first-party ones. Quality gated by passing eval thresholds.

**Why it compounds:** Network effect. 11 first-party playbooks is a catalog. 200 community playbooks with ratings, install counts, and per-playbook quality scores is a platform. A clone starts at 0; contributors only come to the platform with traction.

**What to build:**
- Publishing flow: PR with `playbook.yaml` + required evals → CI runs the eval suite → if it clears threshold, listing goes live
- Marketplace listing page per playbook with: install count, quality score (current benchmark), reviews, version history
- Fork/derive flow for community to customize
- Contributor credits in each benchmark edition
- "Submit a fixture" flow: separate from publishing, lower-effort, lets users add edge cases against existing playbooks

**Success metric:** 50+ community-contributed playbooks live by end of 2027. 1,000+ community-contributed fixtures.

---

### Layer 4 — Integration Surface Depth

**What:** Not new integrations — *deeper* coverage of existing ones. The long tail of GitHub/Slack/PagerDuty edge cases that take years to discover and weeks each to fix.

**Why it compounds:** The happy path is a weekend's work; the edge cases are years. Every customer that hits a weird GitHub state and gets a fix is a permanent quality lead.

**Categories:**
- GitHub: App vs OAuth flows, fine-grained PAT permissions, mono-repo vs poly-repo, required-status-check interactions, branch protection edge cases, rate-limit backoff at scale, webhook replay/dedup, GHE compatibility, fork PR handling
- Slack: threading vs DMs for approvals, multi-workspace orgs, OAuth scope changes, Block Kit limits, ephemeral message handling
- PagerDuty/OpsGenie: schedule weirdness, escalation policy interactions, custom incident fields, API v2/v3 differences
- CI providers: GitHub Actions, CircleCI, custom self-hosted runners

**Process:** Every customer-reported edge case → tracked → fixed → fixture added → regression-tested forever.

**Success metric:** Tracked count of "integration edge cases handled." Should grow 5–10/month with active customers.

---

### Layer 5 — Distribution Footprint

**What:** Where Conduct is *discoverable*, not just findable.

| Channel | Target | Effort |
|---|---|---|
| GitHub Marketplace listing | Top-5 for "AI code review" / "AI workflows" | 2–4 weeks |
| Slack App Directory | Featured in DevOps category | 4–6 weeks (review process) |
| Linear integration directory | Listed for issue-triage use case | 1–2 weeks |
| AWS Marketplace | Enterprise procurement channel | 2–3 months |
| SEO content | Rank for "AI PR reviewer benchmark," "Claude vs GPT code review" | 6–12 months |
| HN front page | 1–2 launches/quarter tied to benchmark editions | Ongoing |

**Content cadence:**
- Quarterly benchmark edition
- 2 blog posts/month tied to benchmark findings or integration deep-dives
- 1 "State of AI Engineering" annual report (Q1 2027 first)

**Success metric:** Organic monthly visitors 10× over year following Edition 001. GitHub Marketplace install count tracked.

---

### Layer 6 — Trust & Compliance

| Asset | When | Cost estimate |
|---|---|---|
| Public security page + trust portal | Q3 2026 | Internal |
| SOC 2 Type I readiness gap analysis | Q3 2026 | $5–10K |
| SOC 2 Type I audit | Q4 2026 | $15–25K |
| SOC 2 Type II observation period | Q1–Q3 2027 | Ongoing |
| SOC 2 Type II report | Q4 2027 | $20–30K |
| VPC-deploy / self-hosted option | Q1 2027 (gated on demand) | 4–8 weeks eng |
| DPA template, MSA template | Q3 2026 | Legal ~$5K |

**Success metric:** SOC 2 Type II by end of 2027. ≥10 enterprise customers on procurement allowlist.

---

## 4. Phased Rollout

### Phase 1 — Foundation (May → August 2026, ~90 days)

| Deliverable | Layer | Effort |
|---|---|---|
| Eval harness v1 (offline only), 20 fixtures per playbook minimum | 2 | 4–6 weeks |
| `run.completed` event + telemetry schema | 1 | 2 weeks |
| Public benchmark page — Edition 001 published | 2, 5 | 2 weeks (after evals exist) |
| GitHub Marketplace listing live | 5 | 2 weeks |
| Slack App Directory submission in flight | 5 | 4 weeks (review process) |
| Public security page + trust portal | 6 | 2 weeks |
| SOC 2 readiness gap analysis kicked off | 6 | External |
| Content cadence started: 2 posts/month | 5 | Ongoing |

**Exit criteria:** Edition 001 published with all 11 playbooks scored across ≥3 models. GitHub Marketplace listing live.

### Phase 2 — Loop Closure (September → November 2026, ~90 days)

| Deliverable | Layer | Effort |
|---|---|---|
| Online eval scoring on `run.completed` (sampled) | 1, 2 | 3 weeks |
| Fixture promotion queue + review UI | 1, 2 | 2 weeks |
| Per-model prompt adapters for OpenAI, Google | 2 | 3 weeks |
| Marketplace publishing flow (private beta with 5 design partners) | 3 | 4 weeks |
| Benchmark Edition 002 published | 2, 5 | 2 weeks |
| SOC 2 Type I audit in progress | 6 | External |

**Exit criteria:** A real production run gets scored, promoted to a fixture, and catches a regression in the next eval run.

### Phase 3 — Network Effects (December 2026 → May 2027, ~180 days)

| Deliverable | Layer | Effort |
|---|---|---|
| Marketplace publishing open to community | 3 | Ongoing |
| Cross-tenant analytics layer | 1 | 6–8 weeks |
| Fixture contribution flow open to community | 3 | 2 weeks |
| Benchmark editions 003, 004 published | 2, 5 | Recurring |
| "State of AI Engineering 2027" annual report | 5 | 4 weeks |
| SOC 2 Type I report published | 6 | External |
| SOC 2 Type II observation underway | 6 | Continuous |

**Exit criteria:** 25+ community playbooks live. 100+ community fixtures. Cross-tenant insights powering ≥2 published posts.

### Phase 4 — Compounding (June 2027+)

Recurring rhythm:
- Quarterly benchmark editions
- 2+ blog posts/month
- Continuous integration edge-case work
- Continuous fixture promotion from production
- Annual "State of" report

---

## 5. Budget

**Eval program (annual):** ~$6,000/year
- Quarterly full suite runs: 4 × $530 ≈ $2,100
- Ad-hoc re-runs on new model releases (~6/year): ~$3,000
- CI runs on prompt changes: ~$1,000

**Compliance (one-time + recurring):**
- SOC 2 Type I (year 1): ~$25,000
- SOC 2 Type II (year 2): ~$30,000
- Legal templates, DPA, MSA: ~$5,000
- Trust portal tooling (Vanta/Drata): ~$10,000/year

**Content & distribution (annual):**
- Freelance writer/editor: ~$24,000/year
- SEO tooling: ~$3,000/year
- Design contract for benchmark editions: ~$10,000/year

**Total year-1 incremental (beyond engineering headcount): ~$80–100K**

Frame as **marketing and credibility spend**, not engineering cost.

---

## 6. Anti-Patterns (What Not to Build)

- **Generic agent observability.** Differentiate on agent-specific signals (token cost per outcome, hallucination flags, approval friction), not generic traces.
- **Heavy RBAC for tiny teams.** Don't build SAML/SCIM until enterprise asks.
- **Treating the eval harness as the moat.** The harness is replicable. The fixture pool + run data is the moat.
- **Hiding model-specific prompt variants.** Credibility lives in disclosure.
- **Auto-upgrading customer models without testing.** Every version bump should trigger the eval suite first.
- **Per-tenant analytics dashboards instead of cross-tenant aggregates.** Per-tenant is commodity. Aggregate is moat.
- **Launching the marketplace with no quality bar.** Eval-gated publishing is non-negotiable from day one.
- **Competing on features with vibe-coded clones.** Optimize for accumulation, not feature parity.
- **Acquiring customers without instrumenting them.** Every signed customer should be a data source.

---

## 7. 18-Month Success Criteria

By **November 2027**, the moat exists if:

| Metric | Target |
|---|---|
| Cumulative scored agent runs | ≥250,000 |
| Fixtures in offline eval suite | ≥600 (≥50/playbook avg) |
| Community-contributed playbooks live | ≥50 |
| Community-contributed fixtures | ≥500 |
| Benchmark editions published | 6 (Editions 001–006) |
| External citations of the benchmark | ≥20 |
| GitHub Marketplace install count | ≥2,500 |
| Slack App Directory: featured in category | Yes |
| SOC 2 Type II report | Published |
| Paying customers | ≥150 |
| Net Revenue Retention | ≥120% |
| Organic monthly visitors to conductai.ai | ≥50K |

Hitting 8+ = moat is real. Fewer than 5 = still building features, not accumulators.

---

## 8. Decisions Blocking Forward Motion

1. **Eval framework:** Build on Inspect or Promptfoo (recommended: Promptfoo — YAML-native, maps naturally to playbook format), or roll our own runner.

2. **Marketplace publishing surface:** GitHub PRs into a dedicated `conductai/playbooks` repo (recommended — lowest friction, native review tooling, public visibility).

3. **Benchmark domain:** `benchmark.conductai.ai` subdomain (recommended — linkable as its own artifact, separable later).

---

## Closing Note

A vibe-coded SaaS can clone Conduct's v1 in a weekend. It cannot clone:
- 18 months of accumulated production run data
- 600 regression fixtures sourced from real customer cases
- 50 community-contributed playbooks with install counts and ratings
- The published benchmark cited 20 times
- A SOC 2 Type II report
- 50 GitHub integration edge cases handled
- 150 customers on procurement allowlists

That's the moat. None of it ships in a sprint. All of it ships if the next 18 months are spent building accumulators instead of features.

— v0.1 · May 24, 2026 · Houston
