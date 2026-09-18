"""Prometheus metric definitions for Guard fail-open observability (#1520).

Labels are deliberately low-cardinality. ``workspace_id`` is NOT a label
here for two reasons:

1. Cardinality — one time-series per workspace × surface would blow up
   Prometheus memory past a few thousand workspaces (standard rule: never
   label with user IDs).
2. Info leakage — a public /metrics endpoint would expose the count of
   active workspaces to any scraper.

Workspace context is preserved in the Slack post and structlog line where
it belongs, not in the metric labels.
"""
from prometheus_client import Counter

GUARD_ENGINE_ERRORS = Counter(
    "guard_engine_errors_total",
    "Guard policy engine failures that fell open at enforcement time.",
    ["surface", "env"],
)

# Phase 0 of #1959 — Gateway audit write failures. The write path in
# app/guard/audit.py::record catches every exception and returns silently
# to avoid crashing the background task. Without this counter, silent
# audit drops were only visible as scattered log lines. Aggregate rate is
# now scrapable so dashboards + alerts can watch it.
#
# Label: reason is a coarse bucket, not the exception message (avoids
# unbounded cardinality). Emit "insert" for the INSERT failure branch,
# "notify" for the Slack-notify branch, "unknown" if we can't tell.
GUARD_AUDIT_FAILED = Counter(
    "guard_audit_failed_total",
    "Gateway audit writes that were dropped after the exception handler in "
    "guard.audit.record swallowed them.",
    ["reason"],
)


# PR-0.5b — writer-side invariant observability. Both writers in
# app/guard/audit.py (record + insert_accepted) hardcode source='gateway'
# (post-#2092). Auth is mandatory on /gateway/v1/* and /mcp, so every
# request reaching either writer should already carry an agent_identity_id
# resolved from the bearer token. A non-zero rate on this counter is a
# writer path that's still leaking null identities — good signal to catch
# before the DB column is flipped to NOT NULL in a follow-up.
#
# Label: writer distinguishes the two entry points so a fix can target
# the leaky one. Not labelled by workspace/agent to keep cardinality
# bounded.
GUARD_AUDIT_MISSING_AGENT_ID = Counter(
    "guard_audit_missing_agent_id_total",
    "Gateway audit writes that reached the writer without an agent_identity_id. "
    "Auth is mandatory upstream so steady-state should be zero.",
    ["writer"],
)


# R2 (reviewer P1) — budget-reconciler wiring + recovery worker.
#
# Three counters observable from Prometheus so ops can watch the
# ledger's recovery lifecycle:
#
# - GUARD_BUDGET_RECONCILE_RUNS: incremented on every startup reconcile.
#   Label `outcome` in {"success","partial","error"} so drift shows up
#   as ratio(partial+error / success).
# - GUARD_BUDGET_RECONCILE_SCOPES: incremented per scope reconciled at
#   startup. Cardinality-safe (no workspace/agent labels).
# - GUARD_BUDGET_RECOVERY_ACTIONS: incremented per stale reservation
#   the recovery worker resolves. Label `action` in
#   {"committed","released","left_open"}.

GUARD_BUDGET_RECONCILE_RUNS = Counter(
    "guard_budget_reconcile_runs_total",
    "Startup reconcile runs, labelled by aggregate outcome.",
    ["outcome"],
)

GUARD_BUDGET_RECONCILE_SCOPES = Counter(
    "guard_budget_reconcile_scopes_reconciled_total",
    "Scope tuples reconciled at process startup.",
)

GUARD_BUDGET_RECOVERY_ACTIONS = Counter(
    "guard_budget_recovery_sweep_actions_total",
    "Stale reservation actions taken by the recovery worker.",
    ["action"],
)
