# Session spend

Open a reported session usage event in Activity to see its session spend.
The same read is available in the CLI:

```bash
conduct guard session-spend --event <session-usage-event-id>
```

The command uses the selected workspace and API, including on-prem deployments.
It does not change tool configuration or contact a model provider.

## Values

- Reported estimate: recorded tool usage deltas priced with their original pricing version.
- Gateway recorded cost: persisted attempt receipts, including retries and fallbacks.
- Unpriced: usage exists, but its cost is unknown. This is not zero.
- Partial: some prices or attempt receipts are missing, or the evidence limit was reached.

These two cost sources are never added together. Reported usage stays outside
the billing ledger and budgets. Gateway recorded cost is not a provider invoice.

## Matching

Gateway requests must carry the tool's actual session UUID in
`X-Conduct-Session-Id`. Matching also requires the same workspace and authenticated
actor; when the report has an agent identity, that identity must match too.
Conduct does not match by time, model, email, or token count.

A session link is not proof that every reported token went through Gateway.
Collectors currently report deltas without per-request Gateway IDs, so token
overlap remains unknown. Missing links remain unlinked. No adapter is marked
verified by this read.

The view reloads current receipts, so late settlement appears after refresh.
Reads are limited to 1,000 reported snapshots and 100 request/identity pairs.
Larger sessions are explicitly marked partial. The API requires spend access
and enforces own-activity versus workspace access.
