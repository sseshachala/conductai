# Unified Accounting — Design Document

Tracking issue: [#2209](https://github.com/sseshachala/conductai/issues/2209)
Branch: `feat/accounting-foundation-2209`
Status: Session 6 shipped (per-workspace canary + delta metrics + failure tests)

## Goal

Replace fragmented token and cost calculations across Gateway, workflow runtime,
Lens, and any other LLM caller with **one accounting engine** shared by all.
Every upstream inference attempt has one usage record and one cost calculation.
Flight Recorder, spend reporting, and budget settlement consume the same result.

Preserve existing workspace + per-developer budgets. No team-budget expansion.
No changes to configured limits.

## Non-negotiable invariants

Copied from #2209 for the branch record:

1. One authoritative receipt per **actual upstream attempt**. Request/run totals
   aggregate attempts without double counting.
2. Workspace + developer attribution comes from trusted authentication/execution
   context, not arbitrary client-supplied labels.
3. Estimated input, reserved money, provider-reported consumption, and
   calculated provider cost are **distinct concepts** and must remain
   distinguishable in storage, APIs, and UI.
4. Known zero is not missing usage. Partial / unavailable / pending / complete
   remain distinguishable.
5. Reasoning tokens already included in output totals are a **breakdown**, not
   an additional charge. `output_tokens = 100, reasoning_output_tokens = 30`
   means 100 total, not 130. **No additive reasoning rate by default.**
6. A pre-provider block has zero upstream inference consumption. Post-provider
   block retains incurred usage and cost.
7. Failed / disconnected requests can still incur provider charges. Do not
   automatically release all reserved spend merely because the client saw an
   error.
8. Duplicate callbacks, retries, reconciliation, and worker restarts must not
   double-settle or double-count.
9. Unknown model pricing is **explicit** (`unpriced`), never silently priced as
   another model or as free.
10. Accounting changes must not weaken policy checks, durable-accept-before-
    dispatch, workspace isolation, or existing budget enforcement.

## Session 1 findings — inventory confirmation

### 1. `GuardAuditEvent` is one-row-per-request, NOT per-attempt

Evidence:

- `apps/api/app/modules/guard/models.py:256–261` — partial unique index
  `ux_guard_audit_events_request_id` on `request_id WHERE request_id IS NOT NULL`.
- `apps/api/alembic/versions/0132_*.py` (migration comment): "one row per
  request_id only."
- `apps/api/app/modules/guard/gateway_handler.py:706–723` — `open_durable_row()`
  called **once** per HTTP request at entry.
- `apps/api/app/modules/guard/gateway_handler.py:831, 1196, 1300` — durable row
  **finalized** once at end, after all attempts. `provider` and `model` columns
  updated to reflect whichever attempt succeeded/last-failed.
- No `attempt_id`, `attempt_ordinal`, or `attempts` JSON column exists today.

**Implication.** When Anthropic 429s and we fall back to OpenAI, that's
currently 1 audit row with the last provider recorded. Fallback attempts
against the first provider (which may have incurred provider charges) are not
persisted per-attempt.

**Decision required in Session 4:** introduce a new `llm_attempt_receipt`
table (or side table) with FK to `GuardAuditEvent.request_id`. Contract in
Session 1 is storage-agnostic; persistence design lands in Session 4.

### 2. Lens has its own LLM call paths — NOT reader-only

Evidence:

- `apps/api/app/modules/glens/routers/chat.py:609–612` — Phase 1 tool
  resolution via `_guarded_openai_completion()` → `guarded_client_call()`.
  Non-streaming completion with tool-use, up to 5 turns, max 512 tokens.
- `apps/api/app/modules/glens/routers/chat.py:654–665` — Phase 2 synthesis
  streaming via `_stream_synthesis()` → `guarded_client_stream()`. Max 1024
  tokens.
- Both call paths currently record to `GuardAuditEvent` with `ai_tool="lens"`
  via `_record_audit()` in `runtime/gateway.py:486, 554`.

**Implication.** Lens receipts already flow through the Guard audit path (good
— attribution + workspace scope already wired). But they inherit the same
one-row-per-request limit, and streaming output tokens are recorded as `0`
today (line 524 TODO). Session 3 normalizer + Session 4 per-attempt persistence
resolve this uniformly for all callers.

### 3. Confirmed fragmented callers

From the Session 0 audit (see comment thread on #2209):

- **Gateway** — `runtime/adapters/{anthropic,openai,perplexity,together,gateway_profile}.py`
  each compute cost via `_xxx_cost()` local functions. All read pricing from
  `runtime/pricing.py` but do their own arithmetic.
- **Workflow runtime** — `runtime/blocks/brain_block.py:715–877` accumulates
  cache tokens per turn; writes `input_tokens`, `output_tokens`, `cost_usd` to
  `RunAnalyticsEvent` and per-turn to `RunTrace`.
- **Lens** — records via `GuardAuditEvent` (Guard audit path), see above.
- **Reservation estimators** — duplicated between `audit._estimate_input_tokens`
  and `gateway_lifecycle` estimators. Epic #2209 flags this explicitly.
- **Budget checks** — `budget_ledger.py` + `gateway_lifecycle.reserve_budgets_for_request()`
  read `GuardSpendBudget` and reserve against Redis-backed atomic counters.

### 4. Pricing coverage gaps confirmed

- **No reasoning token rate slot.** `runtime/pricing.py:15–86` `_DEFAULT_PRICING`
  has `input`, `output`, `cache_read`, `cache_write`, `request_fee_usd`. Missing
  `reasoning_output` — but per invariant #5, this is deliberately a **breakdown
  of output**, not a separately-priced dimension. Contract exposes the field;
  pricing service does not multiply it independently.
- **No modality units.** Audio/image/video unit rates absent. Session 3
  normalizers expose the fields; Session 2 pricing service leaves them nullable.
- **Cache tiers.** Anthropic 5m and 1h ephemeral rates need explicit slots.
  Session 2 pricing schema addition.

## Contract shapes (Session 1 deliverable)

Typed dataclasses in `apps/api/app/runtime/accounting/contracts.py`. Storage-
agnostic. No behavior change. Filled by future sessions.

- **`UsageRecord`** — one paid upstream attempt = one record.
- **`AttemptIdentity`** — `receipt_id`, `request_id`, `attempt_ordinal` (0-indexed),
  `parent_receipt_id` (for fallback chains), optional workflow/run/step links.
- **`Attribution`** — workspace, developer, agent identity, source, client tool,
  transport. From trusted auth context only.
- **`TokenBreakdown`** — nullable-by-design. Distinguishes known-zero from
  missing / pending / partial. `total_output_tokens` includes
  `reasoning_output_tokens` as a subset (invariant #5).
- **`ExecutionOutcome`**, **`UsageOrigin`**, **`UsageCompleteness`**,
  **`PricingCompleteness`** — enums. Preserve provenance for reconciliation.
- **Monetary** — integer microdollars for storage. `1 USD = 1_000_000 μUSD`.
  Rounding decisions live at ledger boundaries (Session 5).

`CONTRACT_VERSION = 1`. Bumps require a documented migration.

## Session 2 findings — silent under-reservation bug

The two legacy estimators (`guard.audit._estimate_input_tokens` and
`guard.gateway_lifecycle.estimate_budget_micros`) diverged on **coverage**:

| Input shape | audit.py | gateway_lifecycle.py |
|-------------|:--------:|:--------------------:|
| messages | ✓ | ✓ |
| system | ✓ | ✗ |
| instructions | ✓ | ✗ |
| response_input (Responses API) | ✓ | ✗ |
| tool schemas | ✓ | ✗ |
| vision content | ✓ | ✗ |

The `gateway_lifecycle` path is what actually **reserves budget** pre-flight.
It systematically under-reserves for requests that use anything beyond a
`messages` array. `system` + `instructions` + tool schemas can easily add
hundreds of tokens per request that the ledger did not reserve — meaning
budgets can technically be exceeded on inbound requests.

**Session 2 does NOT fix this.** Sudhi's correction #5 is explicit: shadow
must exist before new calculations affect settlement. So the compat wrappers
preserve legacy under-coverage byte-identically. The new
`estimate_tokens(body, include=ALL_SHAPES)` API can be called for full
coverage; Session 4 wires the shadow path that logs the delta, Session 6
activates full coverage after canary verification.

Filed observation, not a hot-fix: reservation short-fall is bounded by tool
schema + system prompt sizes, and settlement (which uses the provider's
real usage report) is authoritative. The ledger under-reserves during the
request window but reconciles at commit.

## Session 4 — per-attempt persistence + shadow calculation

New table `llm_attempt_receipts` supports the N-receipts-per-request semantic
that `guard_audit_events` cannot (Session 1 finding). Unique key on
`(request_id, attempt_ordinal)`; migration `0148_llm_attempt_receipts.py`.

The shadow writer (`app/runtime/accounting/shadow_writer.py`) runs
alongside the legacy settlement path. Every settled Gateway request also
persists a normalized receipt with:

- Full `TokenBreakdown` from the Session-3 normalizers (cache tiers,
  reasoning subset, uncached input)
- Priced via `PricingService` (Session 2, non-strict — preserves silent
  fallback for parity with legacy audit rows)
- **Legacy comparison columns** — `legacy_input_tokens`,
  `legacy_output_tokens`, `legacy_cost_microdollars` — populated with what
  the pre-Session-2 extraction produced for the same request. Session 6
  metrics query the delta.

Invariants preserved:

1. **Never fails the request.** `shadow_write()` catches every exception
   internally + a belt-and-suspenders outer try in `gateway_handler`.
2. **Additive only.** No mutation of `guard_audit_events`; no change to
   `settle_reservations` behavior.
3. **Kill-switch.** `settings.guard_accounting_shadow_enabled` defaults
   `False` — no traffic touches the new path until ops enables it.
4. **Contract-versioned.** Each row records `contract_version`,
   `pricing_version`, `normalizer_version` so future readers dispatch
   on version.

Session 4 writes ONE row per request (matching current GuardAuditEvent
granularity). Session 5 or 6 expands to true per-attempt writes once
`attempt_coordinator.py` captures per-attempt response bytes (currently
each attempt's usage bytes are only available for the FINAL winning
attempt — failed attempts before it record only the error class).

**Streaming path**: Session 4 hook is on the non-streaming settlement path
only. Streaming settlement runs inside `_wrap_v2_stream_finalize`; Session 5
adds the hook there.

## Session 5 — Lens integration + read API contract

### Separation of concerns (per Sudhi, 2026-09-23)

Three epics, three responsibilities:

| Epic | Responsibility |
|------|----------------|
| **Accounting** (#2209, this branch) | Produce trustworthy usage / cost / attribution + queryable aggregates. Distinguish reported vs estimated vs incomplete data. |
| **Lens** (separate epic) | Conversational surface that turns evidence into answers ("who drove yesterday's spend?", "how much did caching save?", "why was this budget-blocked?"). Consumes the accounting API for every number. |
| **Flight Recorder** ([#2069](https://github.com/sseshachala/conductai/issues/2069)) | Evidence links: requests, attempts, policy decisions. Lens hyperlinks to Flight Recorder entries when a user drills into a specific answer. |

**Non-negotiable**: Lens's LLM never invents math. Every number Lens
surfaces to a user comes from `AccountingReader`; the LLM's role is to
route the question, phrase the answer, and cite the source — not to compute.

### Accounting → Lens API contract (v1)

Location: `apps/api/app/runtime/accounting/reader.py`.

**Types:**

- `SpendAggregate` (frozen dataclass) — one slice of aggregated evidence.
  Every field is a fact derived from `llm_attempt_receipts` rows. Fields:
  - `receipt_count`, `request_count` (distinct request_ids)
  - `total_cost_microdollars`, `total_reserved_microdollars`,
    `legacy_cost_microdollars` (for Session 6 shadow deltas)
  - `total_input_tokens`, `total_output_tokens`,
    `total_uncached_input_tokens`, `total_cache_read_tokens`,
    `total_reasoning_output_tokens`
  - `completeness_breakdown: dict[UsageCompleteness → count]`
  - `pricing_completeness_breakdown: dict[PricingCompleteness → count]`
  - `execution_outcome_breakdown: dict[ExecutionOutcome → count]`
  - Derived properties: `total_cost_usd`, `has_partial_or_missing`,
    `has_unpriced_attempts`

- `AggregateScope` enum: `WORKSPACE`, `DEVELOPER`, `AGENT_IDENTITY`,
  `MODEL`, `PROVIDER`, `CLIENT_TOOL`, `WORKFLOW_RUN`, `HOOK_SESSION`.

**Methods:**

- `AccountingReader.summarize_by_scope(workspace_id, period_start, period_end, scope)`
  returns `list[SpendAggregate]` — one per distinct scope value.

Session 5 ships the shape + this one method. Additional query shapes
(per-attempt drilldown, cache-savings computation, budget-block correlation)
plug in as the Lens epic identifies conversational needs.

### Invariants the reader surfaces to Lens

1. **Known-zero ≠ missing ≠ pending ≠ partial** (invariant #4). Lens must
   caveat any figure derived from an aggregate where
   `has_partial_or_missing` is true.
2. **Unpriced attempts are visible** (invariant #9). Lens must NOT report
   `total_cost_microdollars` as the exact spend when `has_unpriced_attempts`
   is true; the true cost is at least the reported figure.
3. **Reasoning tokens are a subset** (invariant #5). Available for display
   ("this run used 30k reasoning tokens") but never contribute to cost.
4. **Cache savings are queryable, not invented**. Lens can compute
   "caching saved $X" as `(uncached_rate - cache_read_rate) * cache_read_tokens`
   from the aggregate + the pricing snapshot version recorded on each
   receipt. Lens does not run its own aggregation.

### Session 5 wiring summary

| Path | File | What fires |
|------|------|------------|
| Gateway non-streaming | `gateway_handler.py:1449+` (Session 4) | one shadow row per request at settlement |
| Gateway streaming | `gateway_handler.py::_wrap_v2_stream_finalize` (Session 5) | one shadow row per stream at finalize |
| Lens tool resolution | `guard/gateway.py::guarded_client_call` (Session 5) | one shadow row per Lens LLM call, `source="lens"` |
| Lens streaming synthesis | `guard/gateway.py::guarded_client_stream` (Session 5) | one shadow row per streamed synthesis, usage=UNAVAILABLE (Lens streams do not opt into include_usage yet) |

New scope columns on `llm_attempt_receipts` (migration `0149`):
`workflow_run_id`, `workflow_step_id`, `hook_session_id` — nullable, indexed
partial. Lets aggregations answer "cost per workflow run" and "cost per
Lens session" from a single JOIN-free scan.

### Session 5 workflow hook — resolved in Session 6b

The workflow direct-adapter hook (brain_block) was deferred in Session 5
because brain_block routes through both `gateway_profile` (HTTP → Gateway
→ Session 4 hook fires) and direct-provider adapters (no Gateway hop).
Naive hook = double-count for Gateway-routed workflow calls.

**Resolved by an adapter-marker pattern:**

- `GatewayProfileClient.routes_through_gateway = True` class attribute.
- Direct-provider adapters (Anthropic, OpenAI, Perplexity, Together)
  leave it unset — `getattr(llm, "routes_through_gateway", False)`
  returns False.
- `brain_block` reads the marker at the LLM call site: if True, skip its
  own `shadow_write` (Gateway already wrote the receipt); if False, fire.
- Direct-adapter receipts carry `source="workflow_runtime"` +
  `workflow_run_id` (parsed as UUID if possible) + `client_tool=block_id`.
  Provider-aware synthetic usage blob (Anthropic vs OpenAI shape) so the
  normalizer picks up cache tokens correctly.

No new schema (uses the Session 5 `workflow_run_id` column). Adapter
marker is a class attribute, so a future adapter that routes through
Gateway just adds `routes_through_gateway = True` — one-line opt-in.

## Session 6 — canary rollout + delta metrics + Session 7 gate criteria

### Per-workspace canary

Old: `settings.guard_accounting_shadow_enabled` was a global on/off. Ops
had to enable it everywhere or nowhere.

New: `settings.accounting_shadow_enabled_for(workspace_id: str) -> bool`
layers two settings:

- `guard_accounting_shadow_enabled` (bool, default `False`) — global
  kill-switch. When `False`, shadow writer is off for every workspace.
- `guard_accounting_shadow_workspace_allowlist` (str, default `""`) —
  comma-separated workspace IDs. Empty or `"*"` means "all workspaces".

Precedence: global kill-switch > allowlist. Ops enables the global flag
plus a small allowlist, expands the list, then removes the allowlist
(sets `"*"`) to reach global-on.

No percentage rollout: shadow rows are cheap and idempotent (unique on
`(request_id, attempt_ordinal)`) so ops can flip workspaces on and off
freely without partial-canary aliasing.

### Delta metrics (`runtime/accounting/metrics.py`)

`ShadowDeltaReport` — one report per (workspace, period). Session 7 gate
review pulls this per canary workspace before deleting legacy paths.

Report exposes:

- **Cost deltas** — `new_cost_microdollars`, `legacy_cost_microdollars`,
  `sum_abs_delta_microdollars` (Σ |new − legacy| per row),
  `max_abs_delta_microdollars` (worst single row), `relative_delta_pct`
  (|Σ delta| / legacy).
- **Provenance counts** — `missing_usage_count`, `partial_usage_count`,
  `pending_usage_count`, `unpriced_count`, `incomplete_pricing_count`.
- **Reconciliation** — `settled_requests_missing_shadow_count` (LEFT JOIN
  `guard_audit_events` against `llm_attempt_receipts` on `request_id`).
- **Per-provider/model buckets** — `list[DeltaBucket]` for drilldown.

Derived properties: `missing_usage_rate`, `unpriced_rate`,
`relative_delta_pct`.

### Session 7 gate criteria (documented; enforced by ops review)

**Do not proceed to Session 7 removal until all of the following hold on
at least one canary workspace for a documented observation window:**

1. **Cost delta small and explained.** `relative_delta_pct` within a
   documented tolerance (suggested: <2%), OR every non-trivial delta
   explained by a known correctness fix (cache-tier pricing coverage,
   reasoning-subset semantics, etc.).
2. **No unpriced surprises.** `unpriced_count == 0` OR unpriced models
   are on an approved list (workspace-specific overrides).
3. **Missing-usage bounded.** `missing_usage_rate < 1%` of dispatched
   attempts, and trending down as ops adds `stream_options.include_usage`
   to callers.
4. **No duplicate settlements.** DB unique constraint on `(request_id,
   attempt_ordinal)` guarantees this — verify IntegrityError telemetry
   rate is zero over the observation window.
5. **Reconciliation clean.** `settled_requests_missing_shadow_count` is
   below a documented rate (suggested: <0.1% of settled requests) AND
   trending down.

If any of these fails, **Session 7 does not proceed on schedule**. Old
settlement stays authoritative until the specific delta is explained or
the specific rate falls under the threshold.

### Concurrent / failure hardening

Session 6 self-checks prove the shadow writer:

- Survives 50 concurrent invocations across 10 threads — no shared
  mutable state, each call owns its DB session.
- Never lets a settlement path fail: `IntegrityError` (duplicate key),
  `db.close()` failures, normalizer exceptions, and pricing-service
  exceptions all swallowed.
- Is idempotent: same `(request_id, attempt_ordinal)` write twice → first
  succeeds, second returns None (unique constraint), no receipt is lost
  or duplicated.
- Honors the per-workspace canary decision even when the decision
  function itself raises.

Postgres-backed integration tests (real duplicate-key races, transaction
rollback isolation) will run in CI once the migration is upstream — the
in-process tests here cover the writer's public contract.

## Session 6c — reviewer response (PR #2221)

Sudhi's review at commit `b08e31b3` surfaced 9 findings (7 P1 + 2 P2).
Session 6c addresses all of them. Real Postgres/Redis concurrency
validation, actual per-attempt usage capture in the coordinator, and
Gateway↔workflow receipt linkage are scoped to Session 6D (gate-blocking).
Lens consumer wiring + Flight Recorder integration are scoped to 6E
(product-value, not gate-blocking).

Findings + fixes:

| # | Finding | Fix |
|---|---------|-----|
| P1 · 1 | Clerk IDs / emails / `"system:lens"` passed into UUID column silently dropped receipts | New `developer_external_id: Text` column (migration `0150`). Writer routes non-UUID identifiers there; real UUIDs still land in `developer_user_id` |
| P1 · 2 | Gateway shadow hooks nested in `if _reservations:` — unreserved traffic invisible | Hooks moved OUT of the reservation gate. Fire for all settled requests |
| P1 · 3 | Only one receipt per request; failed attempts unaccounted | `write_receipts_for_attempts` helper — one row per `attempts_meta` entry, chained via `parent_receipt_id`. Winner carries real usage; failed attempts recorded as `execution_outcome=FAILED` with `usage_completeness=UNAVAILABLE`. Full per-attempt usage capture at each dispatch boundary lands in 6D (coordinator extension) |
| P1 · 4 | `PricingService.price_tokens(input_tokens=...)` subtracted `cache_read_tokens` again → 3,270 μUSD instead of 3,570 for reviewer's fixture | API param renamed to `uncached_input_tokens`. No subtraction inside pricing. Each token bucket priced at its own rate |
| P1 · 5 | Sync DB commit on the async event loop | Gateway hooks wrap `write_receipts_for_attempts` in `run_in_threadpool` |
| P1 · 6 | brain_block hook fired on both cache-hit and actual-call branches — replay manufactured a fake receipt | `_did_actual_llm_call` flag gates the hook to the else branch |
| P1 · 7 | Shadow writer used `strict=False` → silent fallback contaminated the shadow-vs-legacy comparison | Writer uses `strict=True`. Unknown models surface as `PricingCompleteness.UNPRICED` with no `calculated_cost_microdollars`. Legacy path keeps `strict=False` (unchanged) |
| P2 · 8 | Anthropic normalizer marked `{"usage": {}}` COMPLETE with zero input; writer inferred outcome from usage completeness | Normalizer distinguishes empty dict / all-None fields from reported zero → returns UNAVAILABLE. `shadow_write` accepts explicit `execution_outcome` and `succeeded` from callers |
| P2 · 9 | `reserved_microdollars` populated with actual cost, not the ledger reservation. Estimator missed tool-call args, tool_use.input, tool_result content, and `max_output_tokens` | Hooks pass `reserved_microdollars = sum(estimated_micros for r in _reservations)`. Estimator walks `tool_calls[].function.arguments` (OpenAI Chat), `tool_use.input` and `tool_result.content` (Anthropic), and honors `max_tokens` / `max_output_tokens` / `max_completion_tokens` |

Session 6c self-checks pin each fix (12 new tests in
`test_reviewer_response.py`). Full suite: 2354 passing (up from 2341).

## Session 6D — shipped

All gate-blocking items delivered:

1. **Per-attempt usage capture (partial).** `AttemptRecord` now carries
   `response_bytes_b64` for failed attempts. Coordinator's except-block
   duck-types `exc.response.content` (httpx.HTTPStatusError pattern),
   captures up to 64 KiB, base64-encodes so it survives the JSONB
   `routing_meta` trip. `write_receipts_for_attempts` decodes and feeds
   the failed-attempt bytes to the normalizer + pricing service.
   Successful attempts still use the handler-owned upstream body
   snapshot. Success attempts' per-attempt normalized usage is a
   Session 7 nice-to-have.
2. **Accounting-version pin.** Handler snapshots
   `settings.accounting_shadow_enabled_for(workspace_id)` +
   `CONTRACT_VERSION` at request entry. Both flow through every
   `shadow_write` call for the request as `pinned_shadow_enabled` and
   `pinned_contract_version` kwargs. A mid-flight flag flip during
   rollout cannot re-attribute an in-flight attempt to the new engine.
3. **Reconciliation writer.** `runtime/accounting/reconciler.py` scans
   `guard_audit_events` for a workspace/period, LEFT JOINs against
   `llm_attempt_receipts`, and writes placeholder receipts for the
   unmatched rows. Placeholders carry `source="reconciler"`,
   `usage_origin=RECONCILED`, `execution_outcome=RECONCILED_LATE`,
   `usage_completeness=PENDING`. Idempotent: second pass over the same
   period is a no-op courtesy of the unique constraint.
4. **Gateway↔workflow receipt linkage.** Handler reads
   `x-conductai-run-id` header (`_run_id`), parses as UUID, and passes
   it as `workflow_run_id` to `write_receipts_for_attempts`. Streaming
   path threads `conductai_run_id` through `_wrap_v2_stream_finalize`.
   Per-run cost aggregations JOIN cleanly on the new column.
5. **Real Postgres tests.** `tests/integration/test_shadow_receipts_realdb.py`
   locks the DB contract: model + migrations apply cleanly; unique
   constraint fires on duplicate `(request_id, attempt_ordinal)`;
   concurrent inserts from two threads produce exactly one row;
   reconciler backfill + idempotency; workspace CASCADE deletes
   receipts. Opt-in via `RUN_ACCOUNTING_REALDB=1` (nightly-only, same
   pattern as `test_durable_audit_lifecycle_realdb.py`).

Session 6D test count: 13 new self-checks in `test_session_6d.py`
covering the coordinator capture helper, the version pin, workflow
linkage, and reconciler error paths. Full guard+runtime suite: 2367
passing.

## Session 6E — Lens consumer + Flight Recorder

Not gate-blocking. Unlocks product value.

1. **Lens consumer wiring** — Lens conversational surface calls
   `AccountingReader.summarize_by_scope(...)` for every number it
   displays. Lens's LLM never invents math (per Sudhi's split of the
   accounting vs Lens epics).
2. **Lens streaming usage** — turn on `stream_options.include_usage`
   in `guarded_client_stream` so Lens receipts stop being
   `UNAVAILABLE`.
3. **Flight Recorder (#2069) integration** — Lens hyperlinks answers
   to Flight Recorder evidence entries.

## Session plan (7 sessions, one branch, one draft PR)

| Session | Deliverable | Status |
|---------|-------------|--------|
| 1 | Inventory confirmation + typed contracts, no behavior change | shipped |
| 2 | Shared pricing service + unified reservation estimator behind compat wrappers | shipped |
| 3 | Anthropic + OpenAI Chat/Responses + LiteLLM normalizers with fixtures | shipped |
| 4 | Gateway per-attempt persistence + shadow calculation | shipped |
| 5 | Workflow/runtime + Lens integration via receipt references + read API | shipped |
| 6 | Controlled activation + concurrent/failure/reconciliation tests + canary | **shipped** |
| 7 | Removal — completion gate, not calendar | pending |

Session 7 does **not** proceed on schedule. It proceeds only when shadow deltas
are within tolerance and reconciliation is clean. If unexplained deltas remain,
old settlement stays authoritative.

## Related

- [#2069](https://github.com/sseshachala/conductai/issues/2069) — Flight Recorder
  input/output usage + provenance (coordinate visibility scope, don't duplicate).
- [#2057](https://github.com/sseshachala/conductai/issues/2057) —
  Governance-under-load contract (5 invariants preserved).
- [#1959](https://github.com/sseshachala/conductai/issues/1959) — Durable audit
  lifecycle.
