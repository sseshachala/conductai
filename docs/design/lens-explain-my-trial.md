# Lens Platform Investigations

Lens is the primary conversational surface for Conduct: Guard, Gateway,
workflows and supported platform management. The trial is one entry point and
acceptance scenario, not the scope of Lens. Phases 1 and 2 delivered the trial
evidence slice below; Phase 3 extends investigations across the platform using
the same ToolRegistry and guarded dispatch as other Lens features.

This milestone remains under #1787, before the scoped-exception pilot. It does
not replace that pilot or close its parent stories.

| Phase / PR | Existing ownership | Outcome |
| --- | --- | --- |
| 1 | #1913 | Authorized trial evidence contract, stable IDs, exact bounded totals, explicit coverage |
| 2 | #1913, #1981 | Usage/cost through shared accounting receipts; no duplicate ledger |
| 3 | #1883, #1981 | Evidence-backed explanations, validated citations, Flight Recorder links |
| 4 | Rewrite #1830; supports #1333 | Platform-to-Lens entry with authorized resource context |
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

## Phase 3: Platform Evidence Tools And Explanations

`get_platform_evidence` is registered beside existing Lens tools, not exposed
through a separate service or execution engine. It supports all/Guard/Gateway/
workflow/trial filters, decision, run ID, request IDs and a bounded time window.
`get_trial_evidence` remains available for trial-specific requests. Existing
configuration and management tools and their confirmation flow remain in place.

Lens dispatch carries the authenticated caller, not `system:lens`. When the
model selects either evidence tool, its result ends the tool loop. Any
other tools in that batch are not executed. A deterministic renderer produces
decisions, recorded rule/policy identifiers, execution status, bounded counts,
receipt totals and pricing versions before the first answer token is emitted.
Evidence text is escaped and known secrets are masked. Returned facts are not
sent to a subsequent model turn or used to authorize a mutation.

Each Flight Recorder citation is constructed from a UUID in the returned
authorized evidence. The page now consumes `?id=` and passes an exact
`event_id` filter to the API. That path checks current membership and activity
permission, then enforces own-event/owned-agent or workspace-wide access.
Focused views do not append unrelated live events. An unavailable record or
access change is not replaced with another event.

Workspace-shared chat history stores a normalized query and a placeholder,
not the protected trial explanation. Session retrieval reruns authorization
and accounting access before rendering. Follow-up model context contains the
query, not historical protected facts. Refresh is a fresh read of the original
time window, not an immutable snapshot of the previous answer.

Guard/Gateway evidence includes non-trial identities and caller-attributed
events without an identity. Own scope matches the authenticated event caller or
an owned identity in the same workspace. Gateway includes legacy `proxy` source
rows. Workflow investigations use existing run/step metadata, require
`platform.runs.view`, and independently enforce workspace and own/all scope.
They expose the latest ten step events per returned run, with exact recorded
counts. Run selection uses creation time; step history can extend past the
selected window. Raw step payloads and workflow state are not returned.

A specific run can find its Gateway events through existing receipt run links
or the audit run ID. Tokens/cost still come only from the shared accounting
reader; workflow analytics are never summed into the same spend again. Runs
without linked audit evidence retain their run status, not invented usage.
No unrelated runs are attached to a request-ID-only lookup. Configuration,
actions, approvals and broader generic Lens answers keep their existing tools;
this PR does not claim every Lens capability is now evidence-verified.

This path distinguishes missing, partial, denied and unavailable data. Rule
IDs alone are not claimed to explain full policy rationale. A recorded allow
does not prove success. Generic Lens answers remain outside this guarantee.

Validation includes real SQLite SQL/RBAC tests, terminal read-only dispatch,
malformed/cross-workspace results, forged citations, escaped record metadata,
receipt-derived formatting, session permission revocation and focused-link
ownership. PostgreSQL RLS, live model tool selection and the authenticated
browser journey remain release gates for Phase 5.

## Phase 4: Contextual Ask Lens

Activity details (including Gateway requests), workflow run headers, recorded
workflow steps and the trial page link to the existing Lens chat. Links carry
only context kind, originating workspace UUID, resource UUID and optional block
ID. They do not copy prompts, responses, tokens, credentials or tool payloads.

The chat waits for workspace selection, rejects malformed or mismatched links,
starts a fresh conversation, and sends a typed `entry_context`. A contextual
link ignores arbitrary `q` prose. The URL is cleared after the API accepts the
handoff so refresh does not send again; failures retain it for retry/sign-in.
Workspace changes remount the chat and abort the
previous request; Strict Mode effect replay does not duplicate auto-send.

The API verifies originating workspace, membership and current resource access
before creating a session. Event resolution uses the same ownership checks as
Flight Recorder citations. Run/step resolution checks run permission, both run
and workflow workspace, own/all scope and recorded block existence. Missing or
inaccessible resources never fall back to a broader query.

The authorized query invokes `get_platform_evidence` through the existing Lens
registry dispatcher and Guard policy gate. No model is needed to select a tool
for this initial contextual read. Later conversation turns keep the existing
Lens tool loop, actions and confirmation behavior.

Exact event/run lookups can include older records outside the default time
window; `exact_resource` requires IDs and retains the existing row/step limits
and authorization. The answer declares this scope explicitly. A block filter
restricts step history, not accounting: linked usage remains run-wide and is
labelled accordingly. Trial handoff retains the default own-scope time window.

Phase 4 tests cover typed handoff, invalid/mismatched references, old records,
permissions, no-model dispatch, frontend URL validation, Strict Mode single
send, workspace switching and denied responses. Live auth/provider/browser
journey and PostgreSQL RLS acceptance remain Phase 5 work.

## Phase 5: Release Validation

`tests/glens/test_journey_postgres.py` runs against a disposable schema with
native PostgreSQL UUID/JSON types, real RBAC reads, and a non-owner database
role without RLS bypass. It applies the shipped workflow SELECT policy from
migration 0004. Other tables retain their existing explicit workspace filters;
these tests do not claim those tables have database RLS.

The eight tests cover Guard hook/MCP and Gateway event handoffs, receipt-backed
fallback totals, exact authorized Flight Recorder citations, workflow step
lookup with receipt linkage, malformed cross-workspace workflow associations,
saved-query permission revocation, trial entry, and the registered tool's own
RLS-scoped database session. CI runs the suite with LENS_TEST_DATABASE_URL.
The fixture needs role/schema creation rights on a disposable test database.

Frontend tests cover typed entry, workspace switching, split stream frames,
truncation, completed-session navigation, saved-session reload and denial, and
the admin-managed Vault selector. CI runs these alongside typecheck. An
interrupted answer is not shown as complete, and contextual entry is retained
until a complete answer supplies a saved-session link.

Lens's settings cog is shared by drawer and full-page chat. The selected Vault
ID is stored in workspace preferences and validated against workspace ownership
on save and credential resolution. No credential values are returned. Selection
does not copy all variables into model context or change tool authorization.

Still outstanding: authenticated desktop/mobile browser acceptance, live model
tool selection, and the full live policy-check-to-record-to-Lens journey. Seeded
PostgreSQL tests and mocked browser-component transport do not prove these.
Phase 5 is not a declaration that every Lens capability is release-certified.
