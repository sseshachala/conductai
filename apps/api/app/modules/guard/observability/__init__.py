"""Guard fail-open observability (#1520).

Exports the pieces used at every fail-open site:

- ``GUARD_ENGINE_ERRORS``            Prometheus counter
- ``record_fail_open()``             internal alert + counter (Conduct ops)
- ``notify_customer_fail_open()``    customer WARNING (workspace Slack)
- ``resolve_workspace_context()``    workspace_id -> (workspace_name, org_name), cached
"""
from app.modules.guard.observability.customer_alert import notify_customer_fail_open
from app.modules.guard.observability.fail_open_alert import record_fail_open
from app.modules.guard.observability.metrics import GUARD_ENGINE_ERRORS
from app.modules.guard.observability.name_cache import resolve_workspace_context

__all__ = [
    "GUARD_ENGINE_ERRORS",
    "record_fail_open",
    "notify_customer_fail_open",
    "resolve_workspace_context",
]
