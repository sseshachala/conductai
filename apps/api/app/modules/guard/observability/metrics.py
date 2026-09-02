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
