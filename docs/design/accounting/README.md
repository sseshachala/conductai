# Unified Accounting — Design Document

Tracking issue: [#2209](https://github.com/sseshachala/conductai/issues/2209)
Branch: `feat/accounting-foundation-2209`
Status: Session 4 shipped (per-attempt persistence + shadow writer, OFF by default)

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

## Session plan (7 sessions, one branch, one draft PR)

| Session | Deliverable | Status |
|---------|-------------|--------|
| 1 | Inventory confirmation + typed contracts, no behavior change | shipped |
| 2 | Shared pricing service + unified reservation estimator behind compat wrappers | shipped |
| 3 | Anthropic + OpenAI Chat/Responses + LiteLLM normalizers with fixtures | shipped |
| 4 | Gateway per-attempt persistence + shadow calculation | **shipped** |
| 5 | Workflow/runtime + Lens integration via receipt references | pending |
| 6 | Controlled activation + concurrent/failure/reconciliation tests + canary | pending |
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
