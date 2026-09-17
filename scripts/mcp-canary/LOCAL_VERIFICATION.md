# Local verification

Date: 2026-09-16. Application baseline: `c3c3ae1e`.

## After the fix

Both defects are fixed on this PR: authenticated identity reaches the writer on
both transports, and missing GuardConfig blocks checks without auto-installing
configuration. Status reports `configured: false` without caching empty rules.

| Local scenario | Agents | Requests | Matched records | p95 | Result |
| --- | --- | --- | --- | --- | --- |
| `/mcp`, configured | 2 | 30 | 22/22 | 40.20 ms | PASS |
| `/guard/mcp`, configured | 1 | 30 | 26/26 | 24.82 ms | PASS |
| `/mcp`, unconfigured | 2 | 30 | 22/22 | 98.97 ms | PASS |
| `/guard/mcp`, unconfigured | 1 | 30 | 26/26 | 27.85 ms | PASS |

All four runs had zero request errors and zero reconciliation failures.
Independent PostgreSQL inspection confirmed 96/96 attributed records. The two
unconfigured workspaces remained without GuardConfig; their 48 checks were
stored as `blocked` with rule `guard_not_configured`. Configured checks retained
the expected `audited` decisions. Credentials were revoked after each run.

Use `--unconfigured` with `local_smoke.py` to repeat the negative-path test.
The historical failures below are retained as before/after evidence.

API regression verification after the fix: 1,824 tests passed across
`tests/guard`, `tests/mcp`, and `tests/tools/test_guard_registrations.py`.

The harness was restored from the parked local work and exercised against a
separate Docker Compose project. No production traffic or existing Docker
database changes were made. The new PostgreSQL database migrated from empty to
`0137`. The application uses the existing `conduct-e2e-api` image dependencies
and the checked-out API source. Fixture users are local database records, not
externally registered Clerk accounts. Database-owner mode does not prove RLS.

## Before the fix: canonical endpoint

Command: `local_smoke.py --agents 2 --output results/local-003`.

| Measurement | Result |
| --- | --- |
| Endpoint | `/mcp` |
| Authenticated agents | 2 distinct identities |
| Duration / cap | 15 seconds / 2 requests per second |
| Total MCP requests | 30 |
| Request errors | 0 |
| Decision checks | 22 |
| Matching Flight Recorder records | 22 |
| Missing / duplicate records | 0 / 0 |
| p95 request latency | 34.47 ms |
| Recorded agent identities | 0 of 22 |
| Overall canary verdict | FAIL: 22 identity mismatches |

Direct PostgreSQL inspection independently confirmed 22 `audited` records,
two session IDs, and no populated `agent_identity_id`. All three credentials
(two agents plus observer) were deactivated after the run. The API was stopped.

This is an attribution defect in the application, not a throughput failure.
`app/modules/guard/routers/mcp.py::_record_event` does not populate agent identity.
The canary failed until authenticated attribution was implemented. It never
substitutes a client-supplied identity for the stored one.

## Before the fix: legacy endpoint

The final legacy run (`local_smoke.py --agents 1 --endpoint /guard/mcp`,
`results/local-004`) used the same provisioned-Guard fixture: 30 requests,
zero request errors, 26/26 matching records, and p95 36.15 ms. It failed only
on missing identity attribution for all 26 rows. Credentials were revoked.

## Harness corrections discovered locally

- A permitted call can be recorded as `audited` by `mcp-audit-all-tool-calls`.
  Scenarios now distinguish the wire `decision` from an explicit `audit_decision`.
  Both remain strict assertions.
- A bare seeded workspace is not an installed Guard workspace. The canonical
  `/mcp` endpoint does not auto-install Guard like `/guard/mcp` does. The fixture
  now calls the existing Guard setup helper before either endpoint is exercised.
- The first legacy smoke also persisted all 22 checks with zero request errors,
  but no agent attribution. Initial verdict mismatches were fixture expectations,
  not evidence of dropped records.

## Tests and limits

19 harness tests passed, including real localhost HTTP fixtures, a simulated
100-agent case, and negative cases for missing attribution/records and RPC errors.
These fixtures prove harness behavior, not application capacity at 100 agents.

This run used Python 3.9 in the pre-existing local harness virtualenv, which emits
an urllib3/LibreSSL warning. Use Python 3.11+ for new environments as documented.
No large-scale, fault-injection, browser rendering, SSE visibility, upstream MCP
tool execution, or production-capacity claim is made by this smoke test.
Generated reports and ledgers remain ignored local artifacts.
