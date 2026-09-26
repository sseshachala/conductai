# Explain My Trial

First delivery milestone under #1787, before the scoped-exception pilot.
This does not replace that pilot or close its parent stories.

| Phase / PR | Existing ownership | Outcome |
| --- | --- | --- |
| 1 | #1913 | Authorized trial evidence contract, stable IDs, exact bounded totals, explicit coverage |
| 2 | #1913, #1981 | Usage/cost through shared accounting receipts; no duplicate ledger |
| 3 | #1883, #1981 | Evidence-backed explanations, validated citations, Flight Recorder links |
| 4 | Rewrite #1830; supports #1333 | Trial-to-Lens entry with authorized request context |
| 5 | #1484 | Full journey, failure, permission and reconnect acceptance |

Each PR carries its own tests. Phase 5 adds cross-feature release tests.
Approvals, single-action exceptions and reviewed policy changes remain later
milestones. No dashboard retirement is required for this first journey.

## Phase 1 Contract

`get_trial_evidence` is a read-only Lens registry tool. It uses authenticated
context for workspace and caller, never model-provided tenant/user identifiers.
It requires current workspace membership and `guard.activity.view_own`, or
`guard.activity.view_all` for explicitly requested workspace scope. Own scope
includes only trial identities currently bound to the caller. Other workspace
identities are excluded even if an audit row references one incorrectly.

The default window is the last 24 hours, UTC, start inclusive/end exclusive.
Explicit boundaries must include timezone offsets. Windows are bounded to 31
days. Up to 100 request IDs and 100 records can be requested. Rows are sorted
by timestamp and event ID descending. A window count supplies the exact total
matching the authorized filters in the same SQL statement as the returned rows.

Status meanings:
- `ok`: all matching recorded rows returned within the requested filters.
- `empty`: no matching authorized records; not proof no calls happened.
- `partial`: result limit reached or some requested IDs not returned.
- `denied`: no caller, no current membership, or insufficient permission.
- `unavailable`: database/session failure; counts remain null, not zero.

Missing and unauthorized request IDs are not distinguished. Coverage includes
the requested IDs, time window, scope, retrieval time, record limit, total and
`has_more`. There is no continuation cursor in Phase 1; narrow the window or
request exact IDs when truncated. Retained `conduct_trial` identities are the
source filter. Deleted/unbound identities and missing audit writes are coverage
gaps, not evidence of no activity. Expired trials remain investigable.

Returned fields are an allowlist: event/request/identity IDs, timestamp,
decision, rule ID, policy hash, provider/model, lifecycle and execution status.
Prompts, responses, routing metadata, credentials and email addresses are not
returned. Text metadata remains untrusted evidence, not instructions. Policy
hash and execution status are nullable; the reader never invents either.

Phase 1 exposes source IDs, not model-generated links or narrative. Usage and
cost belong to Phase 2. Explanation/citation validation belongs to Phase 3.
Existing Lens tools and grounding behavior are unchanged by this PR; this
contract does not certify all Lens answers as evidence-backed.

## Validation

The focused suite executes real SQL and seeded RBAC checks on SQLite, including
tenant isolation, own/all access, revoked membership, limits, time boundaries,
request filtering, unavailable storage and secret-free output. PostgreSQL RLS
and the browser journey require separate validation; SQLite does not prove
PostgreSQL deployment behavior.
