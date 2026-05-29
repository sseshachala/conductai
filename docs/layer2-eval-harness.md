# Layer 2 — Eval Harness & Public Benchmark

## What was built

### Fixture files (`apps/api/eval/fixtures/`)

One YAML file per playbook. Each has 20+ scenarios including 5+ negative cases.

| File | Scenarios | Positive | Negative |
|---|---|---|---|
| ai_ready.yaml | 21 | 15 | 6 |
| autopilot.yaml | 22 | 15 | 7 |
| autopilot_approved.yaml | 22 | 15 | 7 |
| autopilot_full.yaml | 22 | 15 | 7 |
| autopilot_quick.yaml | 21 | 15 | 6 |
| ci_notify.yaml | 20+ | 15 | 5+ |
| dependency_updater.yaml | 20+ | 15 | 5+ |
| docs_drift_detector.yaml | 21 | 15 | 6 |
| flaky_test_detective.yaml | 21 | 15 | 6 |
| incident_responder.yaml | 21 | 15 | 6 |
| issue_triage.yaml | 22 | 17 | 5 |
| postmortem_drafter.yaml | 21 | 15 | 6 |
| pr_reviewer.yaml | 21 | 17 | 4 |
| release_notes.yaml | 20+ | 15 | 5+ |
| release_readiness.yaml | 21 | 15 | 6 |
| security_patch_updater.yaml | 22 | 15 | 7 |
| security_scanner.yaml | 21 | 15 | 6 |
| terraform_reviewer.yaml | 20+ | 15 | 5+ |

### Scoring system

**Structural scoring** (offline, ~10ms, `eval/scorer.py`):
- 13 criteria, 100 pts max
- DSL validation, trigger wiring, block reachability, brain descriptions, JSON output contracts, logic branches, test fixtures, outcome map entry, model input, block labels, memory writes, dead-end blocks
- Per-playbook bonus checks (e.g. pr_reviewer must output `critical` key)

**Quality scoring** (live, `eval/scorer.py`):
- Mechanical: run_succeeded (15), outcome_detected (10), artifact_produced (10), token_budget (5) = 40 pts
- LLM-as-judge (optional `--judge` flag): correctness (10), completeness (10), actionability (10) = 30 pts
- Total quality max: 70 pts with judge, 40 without

### LLM-as-judge (`eval/judge.py`)

- Calls Claude Haiku by default (~$0.002–0.005 per judgment)
- Per-playbook rubric overrides for all 18 slugs in `_RUBRIC_OVERRIDES`
- Returns `JudgeResult` with per-dimension scores and reasons
- `extract_brain_output()` pulls brain text from final run state

### Prompt adapters (`eval/prompt_adapters.py`)

- `detect_family(model)` → `"anthropic"` | `"openai"` | `"google"`
- `adapt_for_model(description, model)` → `AdaptedPrompt(system, user)`
- Anthropic: XML tags, explicit JSON contract block
- OpenAI: markdown headers, code-fenced JSON schema
- Google: plain natural language, collapsed system+user
- `all_eval_models()` → `["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"]`

### Runner CLI (`eval/runner.py`)

```bash
# Structural only (fast, no API key needed)
python -m eval.runner
python -m eval.runner --playbook pr_reviewer

# Live execution (real LLM, mocked GitHub/Slack)
python -m eval.runner --live --playbook pr_reviewer

# Multi-scenario
python -m eval.runner --playbook pr_reviewer --scenarios

# With LLM judge (adds 30 pts quality score)
python -m eval.runner --live --judge --playbook pr_reviewer

# All 3 models + publish baselines
python -m eval.runner --live --judge --all-models --publish

# Generate a full edition manifest
python -m eval.runner --live --judge --all-models --publish --edition 002
```

### Edition generation script (`scripts/gen_edition.sh`)

```bash
# Auto-slug from today's date
./scripts/gen_edition.sh

# Explicit slug → reports/baselines/edition-002.json
./scripts/gen_edition.sh 002

# Single playbook only
./scripts/gen_edition.sh 002 pr_reviewer
```

Requires `ANTHROPIC_API_KEY` in environment. Key is in root `.env`.

### Benchmark manager (`eval/benchmark.py`)

- `list_editions()` — all `edition-*.json` files, newest first
- `get_edition(slug)` — full edition manifest
- `publish_edition(report_dict, edition_slug, model)` — single-model edition
- `build_edition_manifest(edition, reports, playbook_filter)` — multi-model edition with `models[]` array

---

## Edition 001 results

Published: 2026-05-29

| Model | Avg | A | B |
|---|---|---|---|
| claude-haiku-4-5-20251001 | 92.9% | 10 | 9 |
| claude-sonnet-4-6 | 92.9% | 10 | 9 |
| claude-opus-4-7 | 92.9% | 10 | 9 |

**Grade A playbooks** (all three models): copilot_reviewer, incident_responder, issue_triage, pr_reviewer, release_notes, security_scanner, ci_notify, release_readiness, smoke_test, terraform_reviewer

**Grade B playbooks** (infrastructure-dependent): ai_ready (needs DigitalOcean droplet), autopilot, autopilot_approved, autopilot_full, autopilot_quick, postmortem_drafter (has human_review block), dependency_updater, security_patch_updater, docs_drift_detector

The Bs are not model quality issues — they're playbooks with live infrastructure dependencies (DigitalOcean, human approval gates) that can't be fully exercised in mocked eval mode.

---

## Baseline files

```
apps/api/reports/baselines/
  edition-001.json                      — multi-model edition manifest
  all_claude_haiku_4_5_20251001.json    — haiku per-playbook baselines
  all_claude_sonnet_4_6.json            — sonnet per-playbook baselines
  all_claude_opus_4_7.json              — opus per-playbook baselines
```

---

## Known gaps (not yet built)

- **`ai_ready` live eval**: always fails because the agentic `implement` block requires a real DigitalOcean droplet. Should be excluded from `--live` runs or the fixture should skip that block.
- **GPT-5 / OpenAI model**: prompt adapter exists (`openai` family), but no OpenAI API key configured and no `OPENAI_API_KEY` in `.env`.
- **Public benchmark UI**: pages exist at `/benchmark`, `/benchmark/[edition]`, `/benchmark/[edition]/[slug]` but not verified against the new multi-model edition format.
- **`conduct eval` CLI**: Northstar spec calls for `conduct eval <playbook>` shorthand; currently `python -m eval.runner`.
- **Deterministic precision/recall scoring**: Northstar mentions must-flag/must-not-flag grading; not implemented.
- **Editorial findings section**: per-edition 3–5 notable changes; not implemented.

---

## How to run the next edition

```bash
cd apps/api
ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' ../../.env | cut -d= -f2-) \
  ./../../scripts/gen_edition.sh 002
```

Then commit `reports/baselines/edition-002.json` and the per-model JSONs.
