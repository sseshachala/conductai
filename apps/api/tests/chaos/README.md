# Budget-ledger chaos suite (local)

Real Postgres + real Redis on non-standard ports so the tests never touch the
dev database. Everything runs on your laptop via docker-compose.

## One-time setup

```bash
cd apps/api/tests/chaos
docker compose up -d
```

That spins up:

- `chaos-postgres` on port `55432` (in-memory tmpfs so restart is instant)
- `chaos-redis` on port `56379`

## Running the suite

Set the two env vars (see the compose file for user + password), then from
`apps/api`:

```bash
CHAOS_DB_URL=<paste the local postgres URL> \
CHAOS_REDIS_URL=redis://localhost:56379 \
.venv/bin/python -m pytest tests/chaos -v
```

Pytest skips every chaos test when either env var is unset, so a normal
`pytest` run does not require the docker stack.

## Teardown

```bash
cd apps/api/tests/chaos
docker compose down -v
```

## What each test does (plain English)

- **`test_process_kill`** — reserve some money, kill the ledger mid-flight,
  restart it. Does the counter come back consistent, or is a hold stuck?
- **`test_reconnect`** — reserve, disconnect Redis for a moment, reconnect.
  Do subsequent reserves still work? Does the counter still match reality?
- **`test_reply_loss`** — Redis actually saved the reservation, but our reply
  gets dropped mid-flight. Do we release a real hold (bad — leaks capacity)
  or preserve it (good — reconciler resolves later)?
- **`test_streaming`** — start a request, drop the network mid-stream. Does
  the reservation get settled or stay open?
- **`test_rollover`** — clock jumps past midnight of the month. Does a new
  reservation land against the new period's counter (correct) or corrupt the
  old one (broken)?
- **`test_disable_drains`** — flip `BUDGET_LEDGER_ENABLED=false` while a
  reservation is open. Does it still get to settle cleanly?
