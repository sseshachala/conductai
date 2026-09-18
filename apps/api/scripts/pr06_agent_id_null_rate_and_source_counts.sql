-- PR-0.6 — Diagnostic queries for the multi-scope budget arc.
--
-- Two questions we need answered against prod (or a recent snapshot) before
-- deciding how far to go with the follow-up wiring PRs:
--
--   Q1: What fraction of gateway/MCP audit rows already carry
--       agent_identity_id? Determines whether PR-0.5b's writer-side
--       invariant is safe to enforce today (near 0% null) or needs a soak
--       period first (any non-trivial %).
--
--   Q2: How many rows still have source='proxy' after PR #2092 lands?
--       Sizes the migration 0139 UPDATE — plain UPDATE is fine at <5M rows,
--       needs a batched form (LIMIT + loop) above that. Also confirms the
--       migration actually rewrote the historical rows.
--
-- Both queries are read-only. Safe to run in a session that already sees a
-- live gateway/MCP traffic load.

-- ── Q1: agent_identity_id null rate per transport, last 30 days ────────
-- Read: if pct_null on rows where source IN ('gateway', 'mcp') is > 0%,
-- there is a writer path leaking agent_identity_id and PR-0.5b's runtime
-- observability will fire on real traffic — good signal, catch it before
-- flipping the DB column to NOT NULL in a later PR.
SELECT
  source,
  COUNT(*)                                            AS total_rows,
  COUNT(agent_identity_id)                            AS with_agent_id,
  COUNT(*) - COUNT(agent_identity_id)                 AS null_agent_id,
  ROUND(100.0 * (COUNT(*) - COUNT(agent_identity_id)) / GREATEST(COUNT(*), 1), 2)
                                                      AS pct_null
FROM guard_audit_events
WHERE ts > now() - interval '30 days'
GROUP BY source
ORDER BY total_rows DESC;

-- ── Q2: source counts (all-time), sizes any batching decision ──────────
-- After PR #2092 merges + migration 0139 runs, the row count for
-- source='proxy' should be 0 — anything above zero means the migration
-- did not complete or a writer still stamps 'proxy'.
SELECT
  source,
  COUNT(*)   AS row_count,
  MIN(ts)    AS earliest,
  MAX(ts)    AS latest
FROM guard_audit_events
GROUP BY source
ORDER BY row_count DESC;
