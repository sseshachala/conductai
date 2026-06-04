# Phase 2 Playbook: Cost Predictability and Rate Freshness

Status: Proposed
Owner: Engineering + QA
Last updated: 2026-06-04

## Why this exists

Phase 2 issue #6 is cost unpredictability. We need two properties at the same time:

1. Rates stay current as providers change pricing.
2. In-flight runs remain deterministic and auditable.

The operating rule is: dynamic rates for future runs, frozen rates per active run.

## Current code map (today)

1. Runtime LLM call cost calculation is in [apps/api/app/runtime/llm_client.py](apps/api/app/runtime/llm_client.py).
2. Brain run aggregates token/cost usage and emits provider/model fields in [apps/api/app/runtime/executor.py](apps/api/app/runtime/executor.py).
3. Workflow estimate endpoint currently uses static Sonnet pricing constants in [apps/api/app/routers/workflows.py](apps/api/app/routers/workflows.py).

Implication: runtime cost and pre-run estimate can drift unless both read the same rate source.

## Target model (Phase 2)

1. Introduce a pricing registry (single source of truth).
2. Sync rates on schedule (for example daily), with safe fallback.
3. Freeze a `rate_version` snapshot at run start.
4. Use frozen rates for all cost math until run completion.

## Test matrix

### A) Rate lookup and math

1. Lookup returns correct rate for provider/model/version.
2. Unknown model uses explicit fallback policy (and logs warning event).
3. Cost formula is correct for input and output tokens.
4. Rounding is consistent (6 dp internal, 4 dp presentation).

Expected: deterministic values for the same inputs.

### B) Freshness and sync safety

1. Sync job imports valid provider feed and creates new version.
2. Invalid provider payload does not overwrite active rates.
3. Partial sync failure keeps previous version active.
4. Approval gate required before activating new version (if configured).

Expected: no accidental rate corruption.

### C) Freeze-per-run behavior

1. Run starts with `rate_version=A`.
2. Global active rates change to `B` mid-run.
3. In-flight run remains on `A`; next run uses `B`.

Expected: no mid-run repricing.

### D) Budget guardrails

1. Warning emitted when spend crosses 70% soft threshold.
2. Warning emitted when spend crosses 90% threshold.
3. Hard cap crossing stops run with `budget_exhausted` reason.
4. Retry step checks affordability before next turn.

Expected: zero hard-cap overruns.

### E) Estimate vs actual drift

1. Pre-run estimate computed from same rate source/version as runtime.
2. Post-run drift metric is recorded: `(actual - estimate_expected) / estimate_expected`.
3. Drift alerts trigger when threshold is exceeded (for example >15%).

Expected: median drift stays within agreed target.

## CI test suite plan

Use these test groups in CI (names illustrative):

1. `tests/test_pricing_registry.py`
2. `tests/test_pricing_sync_job.py`
3. `tests/test_executor_cost_freeze.py`
4. `tests/test_budget_enforcement.py`
5. `tests/test_estimate_actual_drift.py`

Suggested command:

```bash
cd apps/api
.venv/bin/pytest \
  tests/test_pricing_registry.py \
  tests/test_pricing_sync_job.py \
  tests/test_executor_cost_freeze.py \
  tests/test_budget_enforcement.py \
  tests/test_estimate_actual_drift.py -q
```

## Ops runbook: keeping rates latest

1. Scheduler runs pricing sync job daily.
2. Job writes a new candidate `rate_version` with source timestamp.
3. Validation checks pass (schema, monotonicity, non-negative values).
4. Candidate is approved (manual or policy-driven) and activated.
5. Reconciliation compares recent run costs to invoice exports.
6. Alert if drift crosses threshold; do not auto-edit active rates on drift alert.

## Observability requirements

For each run, store:

1. `rate_version`
2. `provider`
3. `model`
4. `input_tokens`, `output_tokens`
5. `cost_usd`
6. `budget_soft_usd`, `budget_hard_usd`
7. `budget_stop_reason` (if stopped)

For each sync job, store:

1. source fetched time
2. candidate version id
3. activation status
4. validation failures

## Phase 2 acceptance gates for issue #6

1. No run exceeds hard budget in staging soak tests.
2. Every run has provider/model/rate_version attached.
3. Estimate and runtime use the same versioned rates.
4. Sync failure leaves active rates intact.
5. Drift dashboard and alerting are live.

## Rollout order

1. Build registry + versioning.
2. Switch runtime cost reads to registry.
3. Switch pre-run estimator to registry.
4. Enforce budget gates.
5. Enable sync automation and drift alerts.
