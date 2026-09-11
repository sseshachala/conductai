# Modernization decisions

ADR log for non-obvious choices made while working through the audit plan.
One entry per decision. Keep them short — the point is to preserve *why*, not
to write essays.

Template:

```
## <ID> — <one-line title>
Date: YYYY-MM-DD · PRs: #… · Finding(s): S0x, P0x, …

**Decision:** <what we chose>
**Alternatives considered:** <what we didn't choose>
**Reason:** <why the chosen path wins for us specifically>
```

---

## D001 — Do not commit to executing T00–T15 as a single initiative
Date: 2026-09-11 · PRs: (this ingest) · Finding(s): all

**Decision:** Ingest the audit as a source-of-truth artifact but pick findings
individually as business priority justifies each fix. Track progress in
`progress.md`.

**Alternatives considered:** Sequenced T00–T15 execution as a quarter-long
epic; hiring a dedicated implementer to work the plan end-to-end.

**Reason:** The plan is ~3–4 months of focused team work. Parallel product
demands (Lens UX, trial provisioning, demo-driven fixes) can't wait that long.
Findings that affect real exploit risk (S01/S04/S05/S12/S14) get fixed
immediately; broader refactors (T04 policy evaluator unification, T08 shared
templates, T09 vertical migrations) wait for a named business trigger.

---

## D002 — Trial provisioning: challenge/redeem over device flow
Date: 2026-09-11 · PRs: #1794 · Finding(s): S01

**Decision:** Two-step email-verification challenge for `/guard/trial/provision`
and `/guard/trial/redeem`. Redis-backed challenges, single-use via `GETDEL`,
30-minute TTL. Generic accepted response regardless of email existence.

**Alternatives considered:** OAuth device flow (RFC 8628); short-lived code
returned in the response and echoed by CLI.

**Reason:** Device flow requires the caller to poll our server; adds a new
endpoint surface and complicates the `curl | sh` install path. Email challenge
uses existing Resend integration, keeps the CLI two-step (paste verify URL
back), and prevents user enumeration by design (identical bodies for new and
existing emails).

---

## D003 — `PLATFORM_OPERATOR_CLERK_IDS` env var instead of a new role
Date: 2026-09-11 · PRs: #1794 · Finding(s): S05

**Decision:** New `require_platform_operator()` dep gated on a comma-separated
Clerk-user-id env var. `/guard/trial/ops` swapped from tenant permission
`guard.spend.view_all` to this dep.

**Alternatives considered:** New DB-backed `platform_operator` role seeded to
specific Clerk users; keep the existing tenant permission and just tenant-scope
the query.

**Reason:** Ops staff are a small closed set that changes rarely; a DB-role
row would need a UI to manage. Env var keeps the deploy pipeline as the single
source of truth for who has cross-tenant access. Tenant-scoping the query was
rejected because the endpoint's purpose is cross-tenant observability.

---

## D004 — `agent_run_tokens.expires_at` at 24h, not per-run duration
Date: 2026-09-11 · PRs: #1795 · Finding(s): S04

**Decision:** All new `agent_run_tokens` get `expires_at = created_at + 24h`.
Backfill applies the same rule.

**Alternatives considered:** Tie expiry to the run's `max_duration_ms` or
`watchdog_stale_minutes`; leave nullable and rely on `invalidated_at` only.

**Reason:** 24h is generous enough to cover legitimately long-running approval
gates (default `watchdog_approval_timeout_minutes` is 120) with headroom.
Per-run expiry would require passing run duration through the mint site, which
means changing every caller. Nullable was the pre-audit state and let
abandoned tokens authenticate indefinitely — exactly the S04 finding.

---

## D005 — Drop `WorkspaceProvider` from marketing, don't nest it selectively
Date: 2026-09-11 · PRs: #1796 · Finding(s): P06

**Decision:** Remove the provider from `(marketing)/layout.tsx` entirely. The
four marketing pages that call `useWorkspace()` (eval, benchmark) fall back to
the safe context default of `activeWorkspace: null`.

**Alternatives considered:** Nest `WorkspaceProvider` at
`(marketing)/eval/layout.tsx` and `(marketing)/benchmark/layout.tsx` so those
subtrees keep the auto-selected workspace for signed-in visitors.

**Reason:** Two more layout files for a UX affordance (auto-selecting the
first workspace when a signed-in user browses to eval/benchmark from
marketing) that almost no one uses. Ponytail rung 1: does this need to
exist? Answer: no. If a customer asks for it, add the nested provider.
