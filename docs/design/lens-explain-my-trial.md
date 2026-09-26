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

Phase 1 exposes source IDs, not model-generated links or narrative. Phase 2
adds usage and cost as described below. Explanation/citation validation belongs to Phase 3.
Existing Lens tools and grounding behavior are unchanged by this PR; this
contract does not certify all Lens answers as evidence-backed.

## Validation

The focused suite executes real SQL and seeded RBAC checks on SQLite, including
tenant isolation, own/all access, revoked membership, limits, time boundaries,
request filtering, unavailable storage and secret-free output. PostgreSQL RLS
and the browser journey require separate validation; SQLite does not prove
PostgreSQL deployment behavior.

## Phase 2: Receipt-Backed Usage And Cost

Evidence contract version 2 adds per-event `accounting`, batch
`accounting_totals`, and a separate `accounting_status`. Activity access does
not grant spend access: `guard.spend.view_own` or `guard.spend.view_all` is
checked independently. A spend denial or receipt-storage outage preserves
the authorized activity evidence without exposing amounts or inventing zero.

`AccountingReader.evidence_for_requests()` accepts at most 100 already-authorized
request/identity pairs. It queries receipt metadata once, scoped by workspace
and both identifiers. An audit coverage query retrieves only the information
needed to compare expected attempt ordinals and terminal lifecycle; raw routing
metadata is never returned to Lens. All arithmetic stays in accounting, not Lens.

- All recorded attempts contribute once, including charged failed attempts.
  Workflow references and audit estimates do not contribute a second charge.
- The receipt's actual provider, model, pricing/normalizer/contract versions,
  usage origin, completeness and execution outcome remain visible.
- Input/output are the receipt totals. Cache-read and reasoning breakdowns
  are not added again. Historical receipts are not repriced.
- Each metric has a nullable `value` and complete/partial/unavailable status.
  A partial value is a recorded subtotal. No reported values means null;
  explicitly reported zero remains zero.
- Only supported-version receipts with complete usage, priced/override pricing,
  non-null nonnegative cost and USD currency contribute to cost subtotals.
  Other receipts remain visible with their original status and provenance.
- Unknown attempt count, missing ordinals, extra ordinals, or non-finalized audit
  lifecycle prevents a complete-total claim. An absent receipt is not inferred
  to be a free call, even when an audit decision says blocked.
- Requests without usable linkage are reported as unlinked events. Missing
  receipt counts and usage/pricing provenance breakdowns accompany totals.
- Totals cover returned records only, not omitted records when Phase 1's result
  is truncated. Receipt lookup does not filter on finalization time: a receipt
  finalized after the event window still belongs to that request.

This is additive read-side work. No settlement, reservation, rate card,
ledger schema, production data or budget scope changes are part of Phase 2.
