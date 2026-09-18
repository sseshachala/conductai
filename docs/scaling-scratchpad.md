# Gateway scaling — scratchpad

Living reference for the 6-series governance-under-load work (epic
[#2057](https://github.com/sseshachala/conductai/issues/2057)). Skim
top-to-bottom for context, jump to sections by role.

## TL;DR

Under a real 2026-09-17 incident, 40 concurrent gateway requests
caused Render instance restarts because sync SQLAlchemy work blocked
the event loop. The 6-series broke the cliff into six kill-switched
slices, added an isolated `delegator-gateway` Render service, and put
a shared invalidation bus + three cache primitives in front of the
hot paths.

Everything is off by default and enabled per-service via env vars.

## Architecture

Two web services running the **same Docker image**, split by hostname:

| Host | Service | Role | `ADMISSION_ENABLED` |
|---|---|---|---|
| `api.conductai.ai` | `delegator-api` | Dashboard, admin, workflows, OAuth | `false` |
| `gateway.conductai.ai` | `delegator-gateway` | LLM proxy + MCP (latency-sensitive) | `true` |

Both expose `/mcp` and `/gateway/*`. The client-facing recommendation is
`gateway.conductai.ai` for MCP + LLM traffic; `api.conductai.ai` stays as
the dashboard and legacy fallback.

Also running: `delegator-worker` (Redis queue consumer, background jobs),
`delegator-db` (Postgres 16, `basic_256mb`), `delegator-redis` (Valkey 8,
starter, `noeviction`).

Traffic move to gateway is tracked in
[#2067](https://github.com/sseshachala/conductai/issues/2067) — DNS/proxy
decision, not a code change.

## PRs shipped

| PR | What |
|---|---|
| [#2060](https://github.com/sseshachala/conductai/pull/2060) | Refactor: extract helpers from `routers/proxy.py` → `gateway_helpers.py` |
| [#2063](https://github.com/sseshachala/conductai/pull/2063) | PR 1 — MCP admission control (kill switch off) |
| [#2064](https://github.com/sseshachala/conductai/pull/2064) | PR 2 — Gateway admission + initial DB offload |
| [#2065](https://github.com/sseshachala/conductai/pull/2065) | PR 3 — Session-per-thread + async `_check` coordinator callback |
| [#2066](https://github.com/sseshachala/conductai/pull/2066) | PR 3a + PR 4 — `/health` responsiveness proof + `delegator-gateway` blueprint block |
| [#2068](https://github.com/sseshachala/conductai/pull/2068) | PR 5 — async DB migration audit doc |
| [#2070](https://github.com/sseshachala/conductai/pull/2070) | PR 6a — in-process revision-content cache |
| [#2071](https://github.com/sseshachala/conductai/pull/2071) | PR 6e — invalidation bus + `VersionedCache` primitive |
| [#2072](https://github.com/sseshachala/conductai/pull/2072) | PR 6b — auth cache (fingerprint-keyed, TTL-bounded) |
| [#2073](https://github.com/sseshachala/conductai/pull/2073) | PR 6b canary — publisher helpers + router wiring + E2E proofs |
| [#2074](https://github.com/sseshachala/conductai/pull/2074) | PR 6c — effective-policy cache (in-process, bus-invalidated) |
| [#2075](https://github.com/sseshachala/conductai/pull/2075) | Chore — migrate `auth_events._fire` to shared `bus_publish.fire` |
| [#2076](https://github.com/sseshachala/conductai/pull/2076) | PR 6d — atomic budget-reservation ledger primitive (**not yet wired**) |
| [#2077](https://github.com/sseshachala/conductai/pull/2077) | Chore — bump DB plan to `basic_256mb` in `render.yaml` (unblock blueprint sync) |
| [#2078](https://github.com/sseshachala/conductai/pull/2078) | Chore — declare inherited env vars on `delegator-api` |
| [#2079](https://github.com/sseshachala/conductai/pull/2079) | Chore — hardcode gateway feature-flag defaults (fix chicken-and-egg on `fromService`) |
| [#2080](https://github.com/sseshachala/conductai/pull/2080) | Fix — start invalidation bus subscriber on FastAPI startup |
| [#2081](https://github.com/sseshachala/conductai/pull/2081) | PR 6b go-live — wire auth cache into gateway request path |
| [#2082](https://github.com/sseshachala/conductai/pull/2082) | Feat — `/admin/cache-stats` endpoint |

## Kill switches

All default OFF unless noted. Same env var must be set on **both**
`delegator-api` and `delegator-gateway` (skip `delegator-worker`).

| Env var | Default | Effect when ON | Effect when OFF |
|---|---|---|---|
| `INVALIDATION_BUS_ENABLED` | `false` | Bus publishes + subscribes | Publishes are no-op, subscribers never fire |
| `AUTH_CACHE_ENABLED` | `false` | Auth cache serves hits, invalidations drop entries | Every auth call goes to DB via threadpool |
| `EFFECTIVE_POLICY_CACHE_ENABLED` | `false` | `compute_policy` returns cached rules on hit | Every call hits Postgres (3+ queries) |
| `BUDGET_LEDGER_ENABLED` | `false` | (wiring pending) | (wiring pending) |
| `ADMISSION_ENABLED` | `true` on gateway, `false` on api | Reject-first when in-flight > cap | Requests pile up until Postgres pool exhausts |
| `BUDGET_LEDGER_FAIL_CLOSED` | `false` | Refuse when Redis down | Fall through to legacy `budget_check` |
| `METRICS_TOKEN` | *(empty)* | Required in header `X-Metrics-Token` for `/metrics` + `/admin/cache-stats` in prod | Endpoints refuse all callers (fail-closed) |
| `ENVIRONMENT` | *(defaults to `local`)* | `production` triggers auth on `/metrics` + `/admin/cache-stats` | Endpoints open |

Recommended rollout order (already done in prod, doc'd for future
services):

1. `INVALIDATION_BUS_ENABLED=true` → verify `invalidation_bus.subscribed` in logs
2. `AUTH_CACHE_ENABLED=true` → verify `auth.*` handlers in the subscribe log
3. `EFFECTIVE_POLICY_CACHE_ENABLED=true` → verify `guard.policy.invalidated` handler
4. Leave `BUDGET_LEDGER_ENABLED=false` until the wiring PR ships

## Tuning knobs

Leave at defaults unless load says otherwise.

| Env var | Default | Purpose |
|---|---|---|
| `AUTH_CACHE_TTL_SECONDS` | `300` | Auth staleness ceiling |
| `AUTH_CACHE_MAX_ENTRIES` | `10000` | `0` = genuine bypass |
| `EFFECTIVE_POLICY_CACHE_TTL_SECONDS` | `30` | Policy freshness ceiling |
| `EFFECTIVE_POLICY_CACHE_MAX_ENTRIES` | `10000` | `0` = genuine bypass |
| `GATEWAY_ADMISSION_MAX_INFLIGHT` | `40` | Reject at this in-flight count |
| `GATEWAY_ADMISSION_WORKSPACE_MAX` | `10` | Reject per-workspace at this count |
| `MCP_ADMISSION_MAX_INFLIGHT` | `40` | MCP-specific admission cap |
| `MCP_ADMISSION_WORKSPACE_MAX` | `10` | MCP per-workspace cap |
| `SQLALCHEMY_POOL_SIZE` | `5` per service (gateway only) | Base pool per worker |
| `SQLALCHEMY_MAX_OVERFLOW` | `10` per service (gateway only) | Burst allowance; `0` = hard cap |

DB pool math (per `render.yaml`): 3 services × 2 workers × (5 + 10) = 90
connections against Postgres `max_connections ≈ 97`. Headroom = 7 for
migrations. Adjust when scaling plan changes.

## Endpoints

Everything below applies to both `api.conductai.ai` and `gateway.conductai.ai`.

| Endpoint | Auth | Returns |
|---|---|---|
| `GET /health` | none | 200 (liveness) |
| `GET /live` | none | 200 |
| `GET /ready` | none | 200 if DB+Redis reachable |
| `GET /metrics` | `X-Metrics-Token` in prod | Prometheus text |
| `GET /admin/cache-stats` | `X-Metrics-Token` in prod | JSON dump of all cache/bus/admission counters |
| `POST /mcp` | Bearer | MCP JSON-RPC |
| `POST /gateway/v1/chat/completions` | Bearer | LLM proxy |

## Common ops commands

```bash
# Watch all 5 counter surfaces in one shot
curl -s -H "X-Metrics-Token: $METRICS_TOKEN" \
  https://gateway.conductai.ai/admin/cache-stats | jq

# Just the bus (is subscriber live? are events flowing?)
curl -s -H "X-Metrics-Token: $METRICS_TOKEN" \
  https://gateway.conductai.ai/admin/cache-stats | jq .invalidation_bus

# Just admission (is admission actually gating?)
curl -s -H "X-Metrics-Token: $METRICS_TOKEN" \
  https://gateway.conductai.ai/admin/cache-stats | jq .admission

# Render CLI — list services, get IDs
render services list

# Live logs by keyword
render logs --resources srv-dam81drm8hqs73crp0mg \
  --confirm --text "invalidation_bus"

# Deploy status for a service
render deploys list <srv-id> --confirm -o json | jq '.[0].status'

# Validate render.yaml before pushing a blueprint change
render blueprints validate ./render.yaml
```

Render service IDs (Oregon workspace):

| Service | ID |
|---|---|
| `delegator-api` | `srv-d86g57d7vvec73a78r9g` |
| `delegator-gateway` | `srv-dam81drm8hqs73crp0mg` |
| `delegator-worker` | `srv-d86g57t7vvec73a78s3g` |
| `delegator-db` | `dpg-d86g4o57vvec73a78no0-a` (`basic_256mb`) |
| `delegator-redis` | `red-d86g4o57vvec73a78nng` (Valkey 8, `noeviction`) |

## Gotchas hit (and fixes)

**Blueprint sync rejected: "cannot downgrade database from Basic-256mb to Free"**
Live DB was on `basic_256mb`; `render.yaml` still said `plan: free`.
Fixed in [#2077](https://github.com/sseshachala/conductai/pull/2077).
Rule: never downgrade a database plan in the blueprint — bump `render.yaml`
to match live before syncing.

**Blueprint sync rejected: "environment variable used but not defined"**
`delegator-gateway` referenced `fromService: envVarKey: GUARD_USE_DURABLE_AUDIT`
on `delegator-api`, but the key was never declared in the blueprint (only set
via dashboard). Fixed in
[#2078](https://github.com/sseshachala/conductai/pull/2078). Rule: every
`fromService: envVarKey` ref must correspond to a key declared on the source
service in the same `render.yaml`.

**Chicken-and-egg: `fromService` on new service creation**
Even after declaring the keys on `delegator-api`, the "Create service" step
for `delegator-gateway` fired before the "Create env var on `delegator-api`"
actions completed — the ref failed. Fixed in
[#2079](https://github.com/sseshachala/conductai/pull/2079) by hardcoding
`value:` defaults on the gateway block instead of `fromService`. Rule: for
brand-new services in a blueprint, don't use `fromService` — inline the
value.

**Bus enabled but subscriber never fired**
`INVALIDATION_BUS_ENABLED=true` shipped without a call to `bus.start()` on
FastAPI startup. Publishers worked (fire-and-forget), subscribers never
did — caches only recovered on TTL. Fixed in
[#2080](https://github.com/sseshachala/conductai/pull/2080). Rule: async
startup handlers are required when the work spawns event-loop tasks.

**Cache flag flipped but cache never populated**
`AUTH_CACHE_ENABLED=true` had no effect because `init_auth_cache(fetch=...)`
was never called and `_resolve_gateway_auth` never invoked `resolve()`. Fixed
in [#2081](https://github.com/sseshachala/conductai/pull/2081). Rule: a
kill switch is a proof of intent, not implementation — always check
that a code path actually reads the flag.

**`importlib.reload(app.main)` in tests poisons downstream tests**
Reloading main leaves the imported `settings` object stuck at the last
test's values. Every subsequent test that spins up LocalSession refused
to boot. Fixed by patching `settings.environment` in place via
`monkeypatch.setattr`. Rule: never `importlib.reload` a top-level module
in a test. Same landmine class as the earlier `database.py` reload issue.

**DCO check fail on branch with a merge commit**
Merge commits need their own `Signed-off-by` trailer or DCO refuses the
whole branch. Fix: `git rebase --signoff origin/main` to linearize + sign,
or cherry-pick the meaningful commits onto a fresh branch and force-push.

**Gateway service open without auth on `/admin/cache-stats`**
`ENVIRONMENT` was unset on `delegator-gateway`, defaulting to `local` →
endpoint bypassed the token check. Add `ENVIRONMENT=production` to any
new prod service that hosts these endpoints.

## Follow-up work

- **Budget ledger wiring** — analogous to [#2081](https://github.com/sseshachala/conductai/pull/2081)
  for `SpendCapPolicySource`. `reserve()` on evaluate, `release()`/`commit()`
  at request end. Reservation IDs need to flow through `PolicyDecision`.
  Primitive already merged in [#2076](https://github.com/sseshachala/conductai/pull/2076).
- **Traffic move to `gateway.conductai.ai`** — issue [#2067](https://github.com/sseshachala/conductai/issues/2067).
  Currently the gateway service is provisioned + healthy but customer traffic
  still lands on `api.conductai.ai`. Migration is a client-side config change
  (CLI gateway profiles, MCP setup docs, `cond-*` URL bases).
- **Prometheus wiring** — `/admin/cache-stats` is JSON. If we want dashboards
  + alerts, wire each `stats()` counter into a `prometheus_client.Counter`
  and let `/metrics` scrape them.
- **auth_events → bus_publish** — [#2075](https://github.com/sseshachala/conductai/pull/2075)
  did the migration; a follow-up could delete the alias if it stops being
  useful.
- **Delete-identity + membership/permission publishers** — the auth cache
  canary ([#2073](https://github.com/sseshachala/conductai/pull/2073)) wired
  identity-disable and risk-tier-change. Deleting an identity or changing a
  workspace membership currently doesn't publish; those events would need
  new writer-side calls.
- **MCP integration** — `POST /mcp` doesn't hit the auth cache today (only
  the gateway path does). Adding it would be a small change in the MCP
  transport handler.

## When ops asks "what changed in prod?"

- Every kill switch flip is visible in Render dashboard → service → Environment.
- The redeploy triggered by each flip shows in `render deploys list <id>`
  with `trigger=manual` and a timestamp.
- Effect (cache warmth, admission refusals, bus event flow) is visible via
  `/admin/cache-stats` per worker instance.

## Where things live

| Concern | Path |
|---|---|
| Admission control | `apps/api/app/core/admission.py` |
| Invalidation bus | `apps/api/app/core/invalidation_bus.py` |
| Shared publisher | `apps/api/app/core/bus_publish.py` |
| Env parsers | `apps/api/app/core/env_helpers.py` |
| Auth cache | `apps/api/app/core/auth_cache.py` |
| Auth event publishers | `apps/api/app/core/auth_events.py` |
| Effective policy cache | `apps/api/app/core/effective_policy_cache.py` |
| Policy event publishers | `apps/api/app/core/policy_events.py` |
| Budget ledger | `apps/api/app/core/budget_ledger.py` |
| Versioned cache primitive | `apps/api/app/core/versioned_cache.py` |
| Gateway auth resolver | `apps/api/app/modules/guard/gateway_helpers.py` |
| Gateway handler | `apps/api/app/modules/guard/gateway_handler.py` |
| Startup wiring | `apps/api/app/main.py` |
| Blueprint | `render.yaml` |
| Budget reservation table | `apps/api/alembic/versions/0138_budget_reservations.py` |
| Cache/bus tests | `apps/api/tests/core/test_*.py` |
| Admin endpoint test | `apps/api/tests/test_admin_cache_stats.py` |
