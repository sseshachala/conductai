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
from prometheus_client import Counter, Gauge, Histogram

# SQLAlchemy QueuePool metrics intentionally carry no database URL, process,
# exception text, or connection-record labels. Those are secret-bearing or
# unbounded; each process has one primary application pool.
SQLALCHEMY_POOL_CHECKOUTS = Counter(
    "sqlalchemy_pool_checkouts_total",
    "Successful SQLAlchemy QueuePool connection checkouts.",
)

SQLALCHEMY_POOL_CHECKINS = Counter(
    "sqlalchemy_pool_checkins_total",
    "SQLAlchemy QueuePool connection checkins.",
)

SQLALCHEMY_POOL_CONNECTIONS_CURRENT = Gauge(
    "sqlalchemy_pool_connections_current",
    "Connections currently checked out from the SQLAlchemy QueuePool.",
)

SQLALCHEMY_POOL_CHECKOUT_DURATION = Histogram(
    "sqlalchemy_pool_checkout_duration_seconds",
    "Time a SQLAlchemy QueuePool connection remains checked out.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

SQLALCHEMY_POOL_INVALIDATIONS = Counter(
    "sqlalchemy_pool_invalidations_total",
    "SQLAlchemy QueuePool connection invalidations.",
)

SQLALCHEMY_POOL_TIMEOUTS = Counter(
    "sqlalchemy_pool_timeouts_total",
    "SQLAlchemy QueuePool checkout attempts that timed out.",
)

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


# Workspace-allowlist observability. Incremented every time a reserve
# call clears the allowlist gate. Ops watches this to confirm which
# workspaces are actually running through the ledger during canary.
#
# Cardinality caveat: workspace_id is a UUID label. Fine during
# canary (2-3 workspaces) but review before widening to hundreds —
# a follow-up aggregation counter without the label may be needed.
GUARD_BUDGET_ENFORCEMENT_ACTIVE = Counter(
    "guard_budget_enforcement_active_total",
    "Reserve calls admitted by the ledger for an enforcing workspace.",
    ["workspace_id"],
)


GUARD_PROJECTION_EVENTS = Counter(
    "guard_projection_events_total",
    "Audit events considered by projection policy.",
    ["result"],
)

GUARD_PROJECTION_DISPATCH = Counter(
    "guard_projection_dispatch_total",
    "Projection outbox dispatch attempts.",
    ["result"],
)

GUARD_PROJECTION_OUTCOMES = Counter(
    "guard_projection_outcomes_total",
    "Projection intent processing outcomes.",
    ["outcome"],
)

GUARD_PROJECTION_QUEUE_DEPTH = Gauge(
    "guard_projection_queue_depth",
    "Current Redis projection queue depth.",
)

GUARD_PROJECTION_OLDEST_AGE = Gauge(
    "guard_projection_oldest_pending_age_seconds",
    "Age of the oldest dispatchable projection intent.",
)

GUARD_AUDIT_RETENTION_RUNS = Counter(
    "guard_audit_retention_runs_total", "Audit archival passes by aggregate outcome and mode.",
    ["outcome", "dry_run"],
)
GUARD_AUDIT_RETENTION_EVENTS = Counter(
    "guard_audit_retention_events_total", "Audit archive candidates/compacted payloads by outcome and mode.",
    ["outcome", "dry_run"],
)
GUARD_AUDIT_RETENTION_LAST_SUCCESS = Gauge(
    "guard_audit_retention_last_success_timestamp_seconds", "Last successful audit retention cycle.",
)

GUARD_PROJECTION_RETENTION_RUNS = Counter(
    "guard_projection_retention_runs_total",
    "Projection retention daemon passes by aggregate outcome and mode.",
    ["outcome", "dry_run", "more_work"],
)

GUARD_PROJECTION_RETENTION_KNOWLEDGE_BACKFILLED = Counter(
    'guard_projection_retention_knowledge_backfilled_total',
    'Legacy projection rows assigned source-derived retention metadata.',
    ['dry_run'],
)

GUARD_PROJECTION_RETENTION_ORPHANS_DELETED = Counter(
    'guard_projection_retention_orphans_deleted_total',
    'Orphaned legacy derived projection rows deleted during expiry backfill.',
    ['dry_run'],
)

GUARD_PROJECTION_RETENTION_KNOWLEDGE_DELETED = Counter(
    "guard_projection_retention_knowledge_deleted_total",
    "Knowledge rows deleted by projection retention.",
    ["dry_run"],
)

GUARD_PROJECTION_RETENTION_INTENTS_EXPIRED = Counter(
    "guard_projection_retention_intents_expired_total",
    "Projection intents expired by projection retention.",
    ["dry_run"],
)

GUARD_PROJECTION_RETENTION_SUMMARIES_DELETED = Counter(
    'guard_projection_retention_summaries_deleted_total',
    'Allowed-event summary source rows deleted by projection retention.',
    ['dry_run'],
)

GUARD_PROJECTION_RETENTION_INTENTS_DELETED = Counter(
    'guard_projection_retention_intents_deleted_total',
    'Terminal projection intent rows deleted by projection retention.',
    ['dry_run'],
)
