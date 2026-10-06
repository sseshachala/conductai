# Accounting Fallback Cleanup

Run the read-only gate against staging and production before removing the
audit-cost branches from `AccountingReader.spend_micros_by_workspace` and
`BudgetLedger.reconcile` (#2229):

```bash
python tools/accounting_gate.py
```

The command uses `DATABASE_URL` from the deployment environment. It checks all
workspaces over the current month and the last seven days. It prints counts,
not credentials, and exits nonzero if rows remain or the query fails.
Use `--since 2026-09-01T00:00:00Z` to include older history.

The API checks on startup. The worker checks daily at 04:15 UTC. Both emit
CRITICAL logs and one platform Slack alert when rows remain or the query fails.
Slack uses `SLACK_BOT_TOKEN` and `CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL` on the
API and worker. Without those settings, the check still runs and logs.

## Production Check

Checked read-only on October 6, 2026 at 00:57 UTC:

| Unmatched source | Rows | Rows with positive cost | Request IDs |
| --- | ---: | ---: | --- |
| Codex hooks | 11 | 11 | None |
| Codex Desktop hooks | 20 | 0 | None |

The full window starts September 29. Six positive-cost rows are in October.
There are no unmatched Gateway requests in that window. The unmatched hook
estimates total approximately $0.0005225 and currently contribute to the
fallback. This is not a clean deletion gate.

## Before Deletion

- Separate reported hook estimates from receipt-backed spend without losing
  their display or budget behavior. Do not create fake provider receipts.
- Verify zero audit-only rows in both staging and production, including the
  supported seven-day reporting window.
- Remove the two fallback branches and their pre-cutover tests in the same PR.
- Keep raw audit rows and `cost_usd_after` for compliance. No data deletion is
  required for this cleanup.

Nightly CI tests the gate and existing spend/rebuild behavior against an
isolated database. A green CI database does not certify production coverage.
