# ConductGuard — Ops Runbook

**Audience:** on-call responders, SREs, and anyone paged on a Guard-related alert.
**Not a tutorial.** For getting-started, see [`QUICKSTART.md`](./QUICKSTART.md). For capabilities inventory, see [`CAPABILITY_INVENTORY.md`](./CAPABILITY_INVENTORY.md).

**How to use:** find the symptom in Section 2, follow the remediation. If no match, check Section 3 (rollback) or Section 6 (escalation).

---

## 1. Health check surfaces

### API liveness

```bash
curl -sf "$API/health"
```

Returns 200 with `{"status": "ok"}` when the FastAPI process is up. Does not confirm database or upstream connectivity.

### Database reachability

```sql
-- from a psql session against the api's DATABASE_URL
SELECT count(*) FROM guard_audit_events;   -- proves the table exists and is queryable
SELECT MAX(ts) FROM guard_audit_events;     -- proves inserts have happened recently
```

If the `count(*)` query hangs, the database is under lock or the pool is exhausted. See Section 2 → "database pool exhaustion".

### Redis reachability

The Guard proxy uses Redis for rate limits and spend windows.

```bash
redis-cli -u "$REDIS_URL" PING     # should return PONG
```

### Audit chain integrity

```bash
curl -sH "Authorization: Bearer $TOKEN" \
     -H "X-Conductai-Workspace-Id: $WS" \
     "$API/guard/verify/chain"
```

Response:
- `{"valid": true, "entries_checked": N}` — chain intact
- `{"valid": false, "first_broken_index": I, ...}` — chain broken at row I. See Section 2 → "hash chain mismatch"

### Circuit breaker state

Not exposed via HTTP in the current implementation. Check the API logs for `guard.circuit_breaker.transition` events. To reset a stuck breaker in emergencies:

```python
# in a python shell attached to the API process
from app.modules.guard.circuit_breaker import get_breaker
get_breaker().reset("anthropic")   # or "openai", "perplexity", "default"
```

---

## 2. Failure modes and remediation

### Circuit breaker OPEN

**Symptom:** proxy requests return 503 with a body like `Guard circuit breaker OPEN for provider=anthropic — upstream failing repeatedly; retry after ~30s`.
**Cause:** the upstream provider has returned 5xx or connection errors ≥ 5 times consecutively. The breaker sits in front of the outbound call in `routers/proxy.py::_forward`.
**Remediation:**
1. Check upstream status (Anthropic / OpenAI / Perplexity status pages).
2. Wait 30 seconds. The breaker will transition to HALF_OPEN and probe. If 3 probes succeed, it returns to CLOSED automatically.
3. If it re-opens, upstream is still failing — do not manually reset unless you have out-of-band confirmation upstream is healthy.
4. Force-reset only as a last resort (see Section 1 → "circuit breaker state").

### Hash chain mismatch

**Symptom:** `/guard/verify/chain` returns `{"valid": false, "first_broken_index": I}`.
**Cause:** somebody edited `guard_audit_events` directly in SQL, or a migration downgrade left partial state, or a bug in `chain_hash_for_insert` produced an inconsistent entry.
**Do NOT delete rows.** Deleting rows makes the chain unrecoverable.
**Remediation:**
1. Identify the broken row: `SELECT id, ts, tool_call FROM guard_audit_events WHERE id > (SELECT id FROM guard_audit_events ORDER BY ts LIMIT 1 OFFSET :I - 1) LIMIT 5;`
2. If the last N rows are corrupt, mark them with a repair note and continue the chain forward. Preserve the original rows.
3. For a full trust reset (last resort, requires compliance sign-off), rotate to a new audit-chain segment: add a marker row indicating "chain reset at TS due to incident #X" and start a fresh chain. Document in the audit log per SOC 2 requirements.

### Migration lock

**Symptom:** API startup hangs at "Running migrations". Alembic emits `waiting for advisory lock`.
**Cause:** a previous migration process crashed while holding the alembic advisory lock (postgres LOCK), or two API pods are racing.
**Remediation:**
1. Confirm no other migration is legitimately running: `SELECT pid, state, query FROM pg_stat_activity WHERE query LIKE '%alembic%';`
2. If a dead process holds the lock: `SELECT pg_advisory_unlock_all();` from a psql session on the same connection is not enough; you need to kill the holding backend: `SELECT pg_terminate_backend(:pid);`
3. Retry the migration. If it fails again, run `alembic current` to see the last committed version; run `alembic history` to identify the migration that broke.

### Notification channel silent

**Symptom:** guard notifications (Slack, email, webhook) are not firing on rule blocks or approvals.
**Cause:** channel credentials expired, endpoint returning non-2xx, or notification worker not running.
**Remediation:**
1. Check `guard_notification_channels` table for the expected channel; confirm `active = true` and `encrypted_credential` is set.
2. Test the channel end-to-end via `POST /guard/notifications/{id}/test` (see `routers/notifications.py`).
3. Grep API logs for `guard.notify` — dispatch errors are logged at WARNING level.
4. Slack: incoming-webhook URLs expire when the app is uninstalled; regenerate in Slack admin.

### Guard MCP token expired

**Symptom:** MCP clients (Claude Desktop, Cursor) hit 401 on Guard MCP endpoints.
**Cause:** `cond_agt_*` or `cond_run_*` tokens have a TTL. Long-lived agent identity tokens rotate on `conduct guard sync`.
**Remediation:**
1. From the affected client, run `conduct guard sync` (see [`developer_setup.md`](./developer_setup.md)) to refresh tokens.
2. If sync fails, the workspace's session/API key at `/settings` may have been rotated by an admin. Ask the workspace admin to re-issue.

### Advisory-mode workspace unexpectedly blocking

**Symptom:** a workspace configured for advisory / shadow mode is returning `action: block` to callers.
**Cause:** `guard_config.advisory_mode` field is false, OR a persona override on `guard_member_config` is more restrictive than the workspace default.
**Remediation:**
1. Check the workspace config: `SELECT advisory_mode, enforcement_mode, deny_on_error, fail_mode FROM guard_config WHERE workspace_id = :ws;`
2. Check per-member overrides: `SELECT user_id, persona, advisory_mode FROM guard_member_config WHERE workspace_id = :ws;`
3. Confirm the specific rule that fired is not marked `non_overridable: true` (those cannot be relaxed by advisory mode — this is by design).

### Database pool exhaustion

**Symptom:** API returns 503 with a timeout error; requests pile up.
**Cause:** long-running queries or connection leaks; hash-chain inserts under `SELECT FOR UPDATE` can serialize under high write load.
**Remediation:**
1. `SELECT count(*), state FROM pg_stat_activity GROUP BY state;` — look for long `active` or `idle in transaction` counts.
2. Identify slow queries with `pg_stat_statements`.
3. Short-term: bump pool size via env var. Long-term: audit the hash-chain insert path (`models.py:chain_hash_for_insert`) — this is the known serialization point.

### Skill pack sync stale

**Symptom:** a rule was added to a pack, migration applied, but the rule doesn't fire in production.
**Cause:** `guard_policy_cache` still holds a pre-sync snapshot.
**Remediation:** call `POST /guard/config/resync` for each affected workspace, OR invalidate globally: `TRUNCATE guard_policy_cache;` and restart the API pods.

---

## 3. Rollback procedures

### Skill pack version rollback

Guard packs are versioned in the JSON `version` field and cached in `guard_policy_cache.version_hash`. To roll back:

1. Check out the previous pack version from git: `git show HEAD~1:apps/api/app/modules/guard/skill_packs/conduct-base.json`
2. Restore, bump `version` to a new number (never decrement — always forward), commit and deploy
3. Trigger `POST /guard/config/resync` on affected workspaces

### Config rollback (per workspace)

Guard config lives in `guard_config` table. Rollback a bad config change:

```sql
-- see the last 5 config changes if audit-of-config is enabled
SELECT * FROM guard_audit_events
WHERE tool_call = 'guard.config.updated' AND user_email = :who
ORDER BY ts DESC LIMIT 5;
```

If the change is bad, revert the specific field via `PATCH /guard/config` and trigger a resync.

### Migration downgrade

**Only for the most recent migration.** Older downgrades leave gaps in the hash chain.

```bash
cd apps/api
alembic downgrade -1                # rolls back one migration
alembic current                     # confirm the new head
```

If the migration you're rolling back modified `guard_audit_events` (columns), the chain may be broken after downgrade — see Section 2 → "hash chain mismatch".

---

## 4. Common alert playbook

| Alert | Suspected cause | Verify | Remediation |
|---|---|---|---|
| Guard API 5xx rate > 1% | Upstream failure, DB issue, or breaker OPEN | Check `/health`, `SELECT count FROM guard_audit_events`, look for `guard.circuit_breaker` logs | See Section 2 matching subsection |
| Audit chain verification failing | Chain break due to direct edit, migration issue, or bug | `curl /guard/verify/chain` | Section 2 → "hash chain mismatch" |
| Notification channel deliveries dropped | Channel credential expired or endpoint down | Test channel via `POST /guard/notifications/{id}/test` | Section 2 → "notification channel silent" |
| Guard MCP endpoint 401 spike | Token TTL expiries clustering | Check `guard_member_config` last_used_at column | Section 2 → "Guard MCP token expired" |
| Skill pack rule not firing | Cache stale or pack version not bumped | Compare `guard_policy_cache.version_hash` with pack file `version` | `POST /guard/config/resync` |
| Approval requests piling up | Notification failed to fan out; approver missing | `SELECT count FROM guard_approval_requests WHERE status = 'pending' AND created_at < now() - interval '1 hour';` | Section 2 → "notification channel silent" |
| Sudden spend spike | Rule bypass, agent stuck in loop, or new integration | `SELECT SUM(cost_cents), user_email FROM guard_audit_events WHERE ts > now() - interval '1 hour' GROUP BY 2 ORDER BY 1 DESC;` | Investigate top-spender; block or throttle via `POST /guard/spend/configure` |

---

## 5. Log locations and key SQL queries

### Log sources
- API container: `docker compose logs -f api`
- Worker container: `docker compose logs -f worker`
- Postgres: `docker compose logs -f postgres`
- Redis: `docker compose logs -f redis`
- Structured logs shipped to Sentry (env: `SENTRY_DSN`)

### Useful log filters
- `guard.proxy.forward` — every upstream call the proxy made
- `guard.proxy.breaker_open` — circuit breaker rejected a call
- `guard.circuit_breaker.transition` — state changes CLOSED/OPEN/HALF_OPEN
- `guard.notify.failed` — notification dispatch errors
- `guard.audit.insert_conflict` — hash-chain contention (should be rare)

### Common SQL queries

```sql
-- Last 20 blocked requests
SELECT ts, tool_call, decision, user_email, rule_id
FROM guard_audit_events
WHERE decision = 'block'
ORDER BY ts DESC LIMIT 20;

-- Top workspaces by 24h spend
SELECT workspace_id, SUM(cost_cents) / 100.0 AS dollars_24h
FROM guard_audit_events
WHERE ts > now() - interval '24 hours'
GROUP BY workspace_id
ORDER BY 2 DESC LIMIT 10;

-- Chain health per workspace
SELECT workspace_id, count(*) AS entries, count(entry_hash) AS chained
FROM guard_audit_events
GROUP BY workspace_id
HAVING count(entry_hash) < count(*);   -- gaps = pre-migration or corruption

-- Approval requests waiting > 1 hour
SELECT id, workspace_id, created_at, rule_id
FROM guard_approval_requests
WHERE status = 'pending' AND created_at < now() - interval '1 hour'
ORDER BY created_at;
```

---

## 6. Escalation

1. **First 15 min:** on-call handles per this runbook.
2. **After 15 min without resolution:** page the Guard team owner (see internal on-call rotation doc).
3. **Data loss, chain corruption, or suspected security incident:** page security team lead immediately; open an incident channel in Slack; preserve database state (no truncations, no deletes) until root cause is understood.
4. **Compliance-impacting incident:** notify the compliance lead within 1 hour so that SOC 2 / HIPAA notification windows are met.

Related:
- [`overview.md`](./overview.md) — how Guard fits together
- [`QUICKSTART.md`](./QUICKSTART.md) — dev onboarding
- [`CAPABILITY_INVENTORY.md`](./CAPABILITY_INVENTORY.md) — every shipped capability with source refs
