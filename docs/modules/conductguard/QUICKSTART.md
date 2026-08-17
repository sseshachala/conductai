# ConductGuard — Dev Quickstart

**Audience:** engineers on the Conduct codebase who want to run Guard locally, verify it works, and add their first custom rule.
**Time budget:** 15 minutes end-to-end.
**Assumes:** you've followed the top-level [`README.md`](../../../README.md) to bring up the docker-compose stack. This doc picks up from there.

Related docs:
- [`overview.md`](./overview.md) — what Guard is and why
- [`CAPABILITY_INVENTORY.md`](./CAPABILITY_INVENTORY.md) — every shipped Guard capability with file:line refs
- [`enforcement_coverage.generated.md`](./enforcement_coverage.generated.md) — auto-generated coverage matrix

---

## Set up shell variables (once)

Point `API` at your Guard API root. Local docker-compose dev uses a plain-tcp URL; staging and production use TLS.

```bash
export API="<scheme>://<host>:<port>"    # e.g. localhost:8000 in dev
export TOKEN=cond_member_xxx             # grab from UI /settings/tokens
export WS=<your-workspace-uuid>
```

---

## 1. Verify Guard is up (30 sec)

Probe the liveness endpoint:

```bash
curl -sf "$API/health" && echo "api ok"
```

Confirm the Guard router is mounted:

```bash
curl -sf "$API/openapi.json" | python3 -c "import json,sys; \
  paths = json.load(sys.stdin)['paths']; \
  print('guard routes:', sum(1 for p in paths if p.startswith('/guard/')))"
```

Expect ≥ 60 guard routes (see [routers inventory](./CAPABILITY_INVENTORY.md#3-routers-20-files-81-endpoints)).

---

## 2. Confirm the audit hash chain works (1 min)

Every Guard decision writes a row into `guard_audit_events` with a SHA-256 chain (migration `0052`). The `/guard/verify/chain` endpoint walks the chain and verifies integrity.

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
     -H "X-Conductai-Workspace-Id: $WS" \
     "$API/guard/verify/chain"
```

Expected: `{"valid": true, "entries_checked": N, ...}`. If `valid: false`, see the [RUNBOOK](./RUNBOOK.md#hash-chain-mismatch).

---

## 3. Send a proxy call end-to-end (2 min)

```bash
curl -sN -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Conductai-Workspace-Id: $WS" \
  -H "Content-Type: application/json" \
  "$API/guard/proxy/anthropic/v1/messages" \
  -d '{"model":"claude-3-5-sonnet-latest","max_tokens":32,"messages":[{"role":"user","content":"Reply with just the word: ok"}]}'
```

Then confirm the audit event landed:

```sql
SELECT ts, tool_call, decision, entry_hash IS NOT NULL AS chained
FROM guard_audit_events
ORDER BY ts DESC
LIMIT 3;
```

---

## 4. Add your first custom rule (5 min)

Guard rules live in JSON skill packs at `apps/api/app/modules/guard/skill_packs/`. To add a rule to the base pack:

1. Open `apps/api/app/modules/guard/skill_packs/conduct-base.json`
2. Add a rule to the `rules[]` array. Minimum fields:
   ```json
   {
     "id": "my-first-rule",
     "description": "Warn on writes to production config files",
     "match_tool": "write,edit",
     "match_pattern": "prod/config\\.yaml$",
     "action": "warn",
     "severity": "medium",
     "message": "You are modifying a production config file — confirm this is intentional.",
     "enforcement": {
       "version": 1,
       "proxy": "not_supported",
       "hook": "advisory",
       "mcp": "advisory",
       "runtime": "not_supported",
       "guarantee": "Records the action on advisory surfaces; does not claim prevention."
     }
   }
   ```
3. Bump the pack `version` field at the top of the JSON.
4. Trigger a resync: `POST /guard/config/resync` with your bearer token.
5. Test: try writing a file matching your pattern; check `guard_audit_events` for a row with `rule_id = 'my-first-rule'`.

For richer rule types (proxy-side prompt matching, per-workspace overrides), see the [enforcement contract reference](./enforcement_coverage.generated.md).

---

## 5. Where to find things

| I want to... | Look at |
|---|---|
| Understand what Guard already ships | [`CAPABILITY_INVENTORY.md`](./CAPABILITY_INVENTORY.md) |
| Change a proxy behavior | `apps/api/app/modules/guard/routers/proxy.py` |
| Add a new API endpoint | `apps/api/app/modules/guard/routers/` |
| Modify the rule engine | `apps/api/app/modules/guard/policy_engine.py` |
| Change the audit chain | `apps/api/app/modules/guard/models.py` (`chain_hash_for_insert`) |
| Add a database column | `apps/api/alembic/versions/` — new migration |
| Read tests for a subsystem | `apps/api/tests/test_guard_*` |
| Understand ops semantics | [`RUNBOOK.md`](./RUNBOOK.md) |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Liveness probe returns 502 | API not started or crashed on migration | `docker compose logs api` — look for alembic errors |
| Guard routes missing from openapi | Router not mounted in `main.py` | Check `apps/api/app/main.py` includes `guard_mcp` router |
| `verify/chain` returns `valid: false` | Direct DB edit or migration rerun broke the chain | See [RUNBOOK — hash chain mismatch](./RUNBOOK.md#hash-chain-mismatch) |
| Proxy call returns 503 with "circuit breaker OPEN" | Upstream provider failing repeatedly (or synthetic test) | Wait 30s for auto-recovery, or check upstream status |
| No audit rows after a proxy call | Auth failed silently; check `X-Conductai-Workspace-Id` header | `docker compose logs api` — 401 lines will show the reason |
| Skill pack change ignored | Cache not invalidated | Call `POST /guard/config/resync` after any pack edit |

---

## Next steps

- Read [`overview.md`](./overview.md) for the mental model
- Skim [`CAPABILITY_INVENTORY.md`](./CAPABILITY_INVENTORY.md) before proposing new Guard features (avoids rebuilding shipped things)
- If you're on-call, keep [`RUNBOOK.md`](./RUNBOOK.md) open
