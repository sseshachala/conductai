"""Prometheus metric definitions for Guard fail-open observability (#1520)."""
from prometheus_client import Counter

GUARD_ENGINE_ERRORS = Counter(
    "guard_engine_errors_total",
    "Guard policy engine failures that fell open at enforcement time.",
    ["workspace_id", "surface"],
)
