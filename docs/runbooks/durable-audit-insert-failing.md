# Runbook: durable-audit insert failing

## What the alert means

The Slack alert `[PAGE] Guard durable audit — Durable audit insert is failing — Gateway is serving 503s` fires in Conduct's platform-operator Slack (the workspace configured via Render env vars `SLACK_BOT_TOKEN` + `CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL`) when the `GUARD_AUDIT_FAILED{reason="insert_accepted"}` counter delta exceeds 0 in a single scan cycle.

That channel is Conduct-operator-only. Individual customer workspaces get their own Slack notifications for Block/Warn/Audit/Approval events through the workspace's own Slack integration + Notifications settings — not this channel.

That reason label is emitted from one place: `apps/api/app/guard/audit.py::insert_accepted`, in the fail-closed branch that returns HTTP 503 when the durable write to `guard_audit_events` fails.

So when this alert fires, **customers are getting 503s**. The Gateway refused to forward their inference request because it couldn't record the audit. That's the fail-closed contract — persist before forwarding.

## Immediate triage

1. **Confirm scope.** Is this one workspace, a subset, or global? Check the alerter log line + the `guard_audit_failed_total` counter delta. If it's global, the DB itself is likely down or under extreme load.
2. **Check the database.** Postgres up? Connections available? Any long-running query blocking writes?
   - Render dashboard: `guard-audit-db` → connections, CPU, IOPS.
   - `SELECT count(*) FROM pg_stat_activity WHERE state = 'active';`
   - `SELECT * FROM pg_stat_activity WHERE state <> 'idle' AND query_start < NOW() - INTERVAL '30 seconds';`
3. **Check the app logs** for the same window. `guard.gateway.durable_audit_fail_closed` structlog events carry the underlying exception message — usually a Postgres error string.
4. **Check the reconciler.** If DB is up but Postgres is under load, the reconciler thread may be piling on. `guard.durable_audit.reconciler_error` in logs. Consider temporarily disabling the reconciler by setting `GUARD_DURABLE_AUDIT_RECONCILER_SECONDS=0` and restarting worker to reduce write load until the underlying issue clears.

## Common causes

| Symptom in logs | Likely cause | Fix |
| --- | --- | --- |
| `psycopg2.OperationalError: could not connect` | DB is down or restarting | Wait for restart / failover; nothing at app layer to do |
| `psycopg2.OperationalError: too many connections` | Connection pool saturated | Increase Postgres `max_connections` or scale worker down |
| `sqlalchemy.exc.OperationalError: SSL SYSCALL error EOF detected` | Network partition mid-write | Usually transient; investigate Render network status |
| `IntegrityError: duplicate key value violates unique constraint "guard_audit_events_pkey"` | UUID4 collision (astronomically unlikely — check for corrupted RNG) | Reproduce in isolation; likely bug |
| `sqlalchemy.exc.OperationalError: canceling statement due to statement timeout` | Slow query holding table locks | Look for the blocker in `pg_stat_activity` |

## Emergency rollback

If the durable-audit path itself is buggy (regression) and Postgres is fine:

1. Set `GUARD_DURABLE_AUDIT_ROLLOUT_PCT=0` in Render env vars.
2. Save. Render restarts the API.
3. All workspaces immediately fall back to the legacy single-phase writer. Customers stop getting 503s.
4. Investigate the regression before re-enabling.

Workspaces on `GUARD_DURABLE_AUDIT_ALLOWLIST` will still hit the durable path — remove them from the allowlist too if the regression affects everyone.

The kill-switch — `GUARD_USE_DURABLE_AUDIT=false` — turns off the durable path entirely. Only use this if the flag-level rollback above doesn't help (i.e. even the code that decides which path to use is broken).

## When it stops firing

The Slack alerter cool-down is 15 minutes per reason. So after a clean cycle, the next fresh failure will alert again. If the underlying issue is fixed but you want to silence alerts during recovery, temporarily set `GUARD_DURABLE_AUDIT_ALERTER_COOLDOWN_SECONDS=3600` and restart the worker.

## Related

- Metric definition: `apps/api/app/modules/guard/observability/metrics.py::GUARD_AUDIT_FAILED`
- Alerter source: `apps/api/app/modules/guard/durable_audit_alerter.py`
- Canary flag: [#1995](https://github.com/sseshachala/conductai/issues/1995)
- Original epic: [#1959](https://github.com/sseshachala/conductai/issues/1959)
