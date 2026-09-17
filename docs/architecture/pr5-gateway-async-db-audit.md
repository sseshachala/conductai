# PR 5 — Gateway async DB migration audit

**Status**: design doc (no code yet).
**Owner**: gateway scaling track (parent epic #2057, child #2056).
**Prerequisite for**: any migration commit that adds `asyncpg` to the gateway hot path.

The reviewer flagged that async DB migration is not a two-day mechanical change. This doc is the audit before any migration code lands. It maps every sync DB touch on the gateway hot path to its async plan and calls out the non-obvious risks: RLS lifecycle, transaction scope, lazy loading, cancellation, and the dependency graph.

**Not shipped by this doc**: any code change. This is the design; the migration PR(s) come after review of this audit.

---

## 1. Scope

**In scope**: the request path from `handle_gateway_request` entry through response return, on the v2 (cond_*) profile execution flow. Specifically the DB helpers listed in §2.

**Out of scope**:
- MCP `/mcp` dispatch — currently wraps whole call in `run_in_threadpool`; async DB migration there is possible but lower value (see PR 5 discussion). Deferred.
- Workflow worker (`delegator-worker`) — sync DB inside a queue consumer is fine; not on the async web path.
- Lens `chat.py` router — separate audit (see #TBD Lens audit follow-up).
- Admin/dashboard routes — not hot-path traffic. Migrate only if a specific endpoint proves it needs it.

**Non-goal**: eliminate all sync DB from the codebase. This audit is targeted at the specific hot path where event-loop responsiveness matters.

---

## 2. Sync DB touches on the gateway hot path

After PR #2065 (`fix/gateway-eliminate-shared-db`), every DB touch is inside a `run_in_threadpool` wrapper with its own `SessionLocal()`. The `run_in_threadpool` bridge is what unblocks the event loop today. Async migration replaces the threadpool + sync-session pattern with native async sessions.

| # | Helper | Location | Reads / writes | Frequency |
|---|---|---|---|---|
| 1 | `_resolve_gateway_auth_inner` | `gateway_helpers.py` | 3–7 queries: `agent_run_tokens`, `agent_identities`, member-token resolution, RLS SET | Once / request |
| 2 | `_resolve_upstream_credentials` | `gateway_helpers.py` | 3 queries: integration + env_vars + trial fallback | Once / v1 request (v2 uses `_build_v2_plan_owned` instead) |
| 3 | `_lookup_user_email` | `gateway_helpers.py` | 1 read: `users.email by clerk_id` | Once / request |
| 4 | `_lookup_workspace_trial` | `gateway_helpers.py` | 1 read: `workspaces.plan, owner_id` | Once / request |
| 5 | `_build_v2_plan_owned` (wraps `_build_v2_plan`) | `gateway_handler.py` | Multiple: `guard_gateway_profiles`, `guard_gateway_targets`, credential_ref resolution | Once / v2 request |
| 6 | `_apply_tier_resolution_owned` | `gateway_helpers.py` → `app.runtime.model_router` | 1–2 reads: `workspace_llm_primitives`, tier map | Once / request when body carries a tier form |
| 7 | `_check_rate_limit` (owned) | `app.modules.guard.rate_limit` | Redis primary + DB fallback for rate config | Once / request |
| 8 | `_resolve_transport_owned` | `gateway_handler.py` inline | `TransportResolver().resolve` — profile runtime, provider transport class | Once / request when canonical_profile |
| 9 | `_resolve_trial_key_owned` | `gateway_handler.py` inline → `app.modules.guard.trial_upstream` | Trial key + daily counter reads / conditional inserts | Once / request when trial fallback fires |
| 10 | `_eval_prompt_policy_owned` | `gateway_handler.py` inline → `app.guard.policy.evaluate_composed` | Composed policy engine: reads from `RulePolicySource`, `SpendCapPolicySource`, etc. — potentially N queries | Once / request (most expensive read on the path) |
| 11 | `_check` in `_execute_v2` | `gateway_handler.py` | Same composed policy engine, targeted at post-tier-resolved model | Once / target / attempt (usually 1) |
| 12 | `_apply_response_gate` (in threadpool) | `gateway_helpers.py` → policy engine at `gate="response"` | Same composed engine | Once / request post-upstream, non-streaming path only |
| 13 | Streaming response gate | `_wrap_streaming_response` | Same, invoked once at end-of-stream in the iterator's `finally` — already off the request loop | Once / streaming request |
| 14 | `_record_audit` | `app.guard.audit.record` | 1 insert per request (durable-audit writer batches) | Once / request |
| 15 | `_finalize_durable_row` (v2 stream) | `app.modules.guard.gateway_lifecycle` | 1 update per stream close | Once / streaming request |
| 16 | Vault decrypt for BYO keys | `_vault_key` inside credential resolve | 1 select + 1 crypto op per candidate row | Piggybacks on #2 |

**Total**: ~10–16 DB queries per request across the full pipeline. Each currently runs synchronously via SQLAlchemy in a threadpool worker.

---

## 3. Driver — `asyncpg` alongside `psycopg2`

**Plan**: add `asyncpg` to `requirements.txt`. Create a second `create_async_engine` + `async_sessionmaker` alongside the existing sync one. Do NOT replace the sync engine — many non-gateway paths still use it and shouldn't be forced through async.

```python
# apps/api/app/core/database.py (proposed additions)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

async_engine = create_async_engine(
    settings.sqlalchemy_database_url.replace("postgresql://", "postgresql+asyncpg://", 1),
    pool_pre_ping=True,
    pool_size=_pool_int("SQLALCHEMY_ASYNC_POOL_SIZE", 5),
    max_overflow=_pool_int("SQLALCHEMY_ASYNC_MAX_OVERFLOW", 10),
)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_async_db():
    async with AsyncSessionLocal() as db:
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
```

**Pool budget concern**: sync + async engines each have their own pool. Total connections per instance = `(sync pool + async pool) × workers`. Adjust `SQLALCHEMY_POOL_SIZE` and `SQLALCHEMY_ASYNC_POOL_SIZE` so the sum × service count × worker count stays under Postgres `max_connections`.

**Driver compatibility risks**:
- `asyncpg` uses native Postgres binary protocol — most SQL works but a handful of features differ (JSON serialization defaults, prepared statement caching).
- Some SQLAlchemy compiled expressions render differently under the asyncpg dialect. Any raw `text()` string using psycopg2-specific bind styles needs review.
- `pgvector` extension: verify async driver supports the type adapters (should work — pgvector-python has async support).

**Verification**: run a spike PR that just adds the async engine + a single `await db.execute(select(User).limit(1))` query and confirms it works end-to-end.

---

## 4. RLS lifecycle — the hardest part

**Current behavior**: `set_workspace_rls(db, workspace_id)` runs `SET LOCAL app.workspace_id = ...` on the sync session. `SET LOCAL` is scoped to the current transaction. When the session commits/closes, RLS resets. Since each request opens its own session, RLS is per-request-scoped and safe.

**Under `asyncpg` pool**: connections are shared across requests. `SET LOCAL` still works but only inside a transaction (`async with session.begin():`). Outside a transaction, `SET LOCAL` is a no-op.

**Three options**:

### Option A: wrap every DB operation in an explicit transaction

Every `AsyncSession` usage becomes:
```python
async with AsyncSessionLocal() as db:
    async with db.begin():
        await db.execute(text("SET LOCAL app.workspace_id = :ws"), {"ws": workspace_id})
        # ... query work ...
```

Pros: RLS is bounded to the transaction — safe.
Cons: read-only operations now pay for a transaction; verbose.

### Option B: use `SET LOCAL` inside a transaction that spans the whole request DB work

Open a transaction at the start of the request, keep it open, run all DB reads inside it, commit at the end.

Pros: single RLS setup per request.
Cons: holds a connection for the full request duration — undoes the whole point of session-per-op. Bad for concurrency.

### Option C: application-level RLS

Add `workspace_id = :workspace_id` explicit filters to every ORM query. Remove reliance on `SET LOCAL`.

Pros: no RLS state per connection; connections truly stateless.
Cons: touches every query. Discipline required — one missed filter is a cross-tenant leak. Should be paired with a linter/audit that grep-checks every query filters by `workspace_id`.

### Recommended: Option A

Explicit transaction per operation. Matches the "session-per-op" pattern from PR #2065. Some read paths become transactions but that's an acceptable cost. Verbose, but explicit is safer than clever.

**Migration side effect**: helpers refactored to accept `workspace_id` explicitly (they already do — see #2065). RLS SET happens inside the helper's transaction wrapper.

---

## 5. Transaction boundaries

Under async SQLAlchemy, the pattern is:

```python
# read (no transaction needed if using autocommit mode + no RLS)
async with AsyncSessionLocal() as db:
    result = await db.execute(select(User).where(...))

# write, or read that needs RLS
async with AsyncSessionLocal() as db:
    async with db.begin():
        await db.execute(text("SET LOCAL app.workspace_id = :ws"), {"ws": ws})
        # ... read or write ...
    # commit happens at db.begin() exit
```

**Rule for the migration**:
- Every helper opens `AsyncSessionLocal()` as a context manager.
- Every helper that needs RLS wraps its work in `async with db.begin():`.
- No helper holds a session across an `await` that leaves the helper's scope. Session lifetime = helper lifetime.

**No shared session across helpers** — same invariant as PR #2065.

---

## 6. Lazy loading — every ORM attribute access is a query

**Current risk**: sync SQLAlchemy hides N+1 queries behind attribute access. Under async, that becomes worse — every lazy attribute access raises unless explicitly awaited via `awaitable_attrs`.

**Audit action**: for each helper in §2, list the ORM objects returned and every attribute accessed after the session closes. If any attribute is a relationship (`agent_identity.workspace`, `policy.rules`, `profile.targets`), the query must eagerly load it via `selectinload()`.

**Example** (illustrative, needs verification):
```python
# Current sync code (works because lazy load is implicit):
ai = db.query(AgentIdentity).filter(...).first()
tier = ai.risk_tier  # column, no lazy load — fine
workspace_name = ai.workspace.name  # RELATIONSHIP LAZY LOAD — must be eager under async

# Async migration:
result = await db.execute(
    select(AgentIdentity)
    .options(selectinload(AgentIdentity.workspace))
    .where(...)
)
ai = result.scalar_one_or_none()
```

**Concrete audit**: after picking the first migration target (probably `_lookup_user_email` — simplest, 1 query, 1 column), map every attribute access and add `selectinload` for any relationship.

**Tests to add**: for each migrated helper, a test that asserts the helper does exactly N queries under `sqlalchemy.event.listen("before_execute", ...)`. Regression guard against silent N+1.

---

## 7. Cancellation semantics

**Current sync path (via threadpool)**: FastAPI cancels the async task, but the thread runs to completion. Session close in the helper's `finally` releases the connection. Cancellation doesn't leak connections but wastes work.

**Under `asyncpg`**: `await session.execute(...)` on a cancelled task cancels the underlying query via asyncpg's cancel token. Then:
- If session was `async with`'d correctly, the connection returns to pool on session exit.
- If session was manually created without context manager, connection may leak.

**Migration rule**: always use `async with AsyncSessionLocal() as db:`. Never `db = AsyncSessionLocal(); ...; await db.close()` — that pattern doesn't release on cancellation.

**Test**: create 100 tasks that each call an async DB helper, cancel half after 10ms, verify pool count returns to baseline within 1s.

---

## 8. Dependency graph

Migrating `handle_gateway_request` isn't self-contained — its DB helpers call further modules that also use sync SQLAlchemy. Migration touches:

- `app.core.auth` — `resolve_agent_token`, `token_is_expired`, `_resolve_agent_token`, `resolve_agent_identity_row`. Each takes `db: Session` and queries.
- `app.guard.policy` — `evaluate_composed(ctx)` where `ctx.db: Session`. The policy engine internally reads from multiple `PolicySource` implementations, each of which uses `db`.
- `app.guard.audit` — `record(...)` writes audit rows. Called via background tasks in the current pattern.
- `app.modules.guard.rate_limit` — `check_rate_limit(db, ...)`. Redis-primary but has DB config lookup.
- `app.modules.guard.gateway_runtime.TransportResolver` — sync DB queries.
- `app.modules.guard.trial_upstream.resolve_trial_key` — sync DB.
- `app.runtime.model_router` — used by `_apply_tier_resolution`.
- `app.core.credentials.get_credential` — sync DB.

**Migration strategy for dependencies**: two options.

### A. Async duplicates alongside sync

Add `async def resolve_agent_token_async(...)` next to the sync one. Migration flag: gateway path uses async; everyone else uses sync. Delete the sync version once no callers remain.

Pros: incremental, callable via feature flag.
Cons: two copies of similar logic, drift risk.

### B. Full replacement — every caller migrated

Every caller of these helpers switches to async in the same PR.

Pros: one source of truth.
Cons: PR touches many files; hard to bisect if something regresses.

**Recommended**: A for hot-path helpers (`resolve_agent_token`, `evaluate_composed`, `check_rate_limit`); B for helpers with few callers (`resolve_trial_key`, `TransportResolver`).

---

## 9. Migration strategy — feature-flagged, hybrid

Rather than a big-bang migration, ship one helper at a time behind a feature flag:

```python
if settings.gateway_async_db_enabled:
    result = await _resolve_gateway_auth_async(request, ...)
else:
    result = await run_in_threadpool(_resolve_gateway_auth, request, ...)
```

`GATEWAY_ASYNC_DB_ENABLED=false` default. Deploy code, flip flag in staging, canary in prod on one workspace, ramp.

Order of migration (smallest → largest blast radius):
1. `_lookup_user_email` — simplest, 1 query.
2. `_lookup_workspace_trial` — 1 query.
3. `_resolve_upstream_credentials` — 3 queries in one helper.
4. `_apply_tier_resolution` — 1–2 queries.
5. `_check_rate_limit` — Redis + DB.
6. `_build_v2_plan` — complex, multiple queries, credential_ref indirection.
7. `_eval_prompt_policy` — big one, touches the whole policy engine.
8. `_check` in `_execute_v2` — per-target policy re-eval.
9. `_apply_response_gate` — response-side policy.
10. `_record_audit` — write path, needs care around durable-audit writer.

Each helper migration is its own PR. Approx 1 day per, plus 1 day of stress testing per.

**Total estimated timeline**: 2–3 weeks for the gateway hot path, given the dependency-graph work and per-helper testing.

---

## 10. Testing strategy

Per-helper:
- Unit test with real Postgres (test DB) — verify the async helper returns the same value as the sync one for the same input.
- Cancellation test — task cancel mid-query, verify pool count.
- Query-count test — assert the helper does exactly N queries (guard against N+1).
- Concurrency test — 100 parallel invocations, verify no session leaks, pool count returns to baseline.

Path-level:
- Full-path integration test: send a gateway request through the async path, verify same response as sync path.
- Stress test: replicate the concurrency-40 stress-gateway.py run — verify event-loop lag stays low, `/health` responsive throughout.

Rollout tests:
- Toggle `GATEWAY_ASYNC_DB_ENABLED` mid-stress-test — verify no regressions.
- Kill-switch: verify the flag actually falls back cleanly.

---

## 11. Rollout & rollback

**Phase 1**: merge async engine + first helper (`_lookup_user_email`) behind flag. Default OFF. Deploy.

**Phase 2**: enable flag in staging. Stress-test for 24h. Verify:
- No connection pool exhaustion.
- No new error class in audit logs.
- Query count per request unchanged (guarded by tests).

**Phase 3**: canary in prod on one non-critical workspace via header override (`X-Gateway-Async-Db: true`). Verify latency + error rate unchanged.

**Phase 4**: enable globally. Watch `admission.loop_lag_high` — should stay silent (async DB removes the last event-loop-blocking source).

**Rollback**: flip the env var. Zero code redeploy.

**Phase 5** (much later, once all 10 helpers are migrated): remove the sync-helpers-plus-threadpool bridge. Delete `run_in_threadpool` wrapping. Delete the flag.

---

## 12. Explicit non-goals for the first migration PR

- Do NOT migrate MCP dispatch to async. MCP's `run_in_threadpool` pattern works fine at MCP's concurrency level; migration would restructure the JSON-RPC dispatcher for less gain than gateway.
- Do NOT migrate workflow worker. Sync DB inside a queue consumer isn't a bottleneck.
- Do NOT delete the sync helpers or `run_in_threadpool` bridge in the first PR. Both paths coexist behind the flag until Phase 5.
- Do NOT eliminate durable acceptance in front of dispatch. Invariant #3 of the governance-under-load contract (#2057) stays intact.

---

## 13. Open questions

1. **pgvector compatibility** — do we use vector types on the gateway path? If yes, verify `pgvector-python`'s async support in the spike PR.
2. **Prepared statement cache** — asyncpg maintains a prepared statement cache per connection. Under high query variety this can bloat memory. Investigate cache eviction config.
3. **Transaction retry policy** — what happens on transient serialization errors under async? SQLAlchemy has retry decorators for sync; async equivalent?
4. **Migration file compatibility** — Alembic migrations use sync engine. No change needed but verify our migration runner (`alembic upgrade head`) still works after `asyncpg` is added.
5. **Audit writer async path** — the durable-audit writer (`app.guard.audit`) currently uses sync DB. Migrating it is coupled with the async migration but has its own subtlety (durable acceptance timing). Separate audit doc?
6. **RLS strategy final choice** — Option A (explicit transaction per op) is the recommendation, but confirm nothing on the gateway hot path *requires* Option C's application-level filtering.

---

## 14. Reviewer checklist (before any migration PR lands)

- [ ] Spike PR completes: async engine works end-to-end with one query.
- [ ] pgvector async compatibility verified (if applicable).
- [ ] Cancellation behavior tested against real Postgres (not mocks).
- [ ] Query-count regression test framework in place.
- [ ] Feature flag `GATEWAY_ASYNC_DB_ENABLED` wired everywhere with default OFF.
- [ ] Rollback path documented and rehearsed in staging.
- [ ] Pool sizing math updated in `render.yaml` to include async pool.
- [ ] Documentation updated: this doc marks Phase 1 complete when the flag is added.

---

## References

- Parent epic: #2057 (governance under load — 5 invariants + shared Flight Recorder schema)
- Child epic: #2056 (gateway hot-path scaling — this is Stage 3)
- Prior PRs: #2063 (MCP admission), #2064 (gateway admission + first DB offloads), #2065 (`_check` async + shared-session elimination), #2066 (concurrency proof + isolated gateway service)
- SQLAlchemy async docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- asyncpg driver: https://magicstack.github.io/asyncpg/
- Reviewer's guidance on this PR's scope and gotchas (session-per-thread, cancellation, RLS lifecycle).
