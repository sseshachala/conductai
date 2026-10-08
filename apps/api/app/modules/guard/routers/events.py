"""
POST /guard/events          — ingest hook event (called by guardctl binary)
GET  /guard/events          — paginated list, filterable
GET  /guard/events/stream   — SSE real-time feed

Endpoints live in ``events_ingest`` (ingest) and ``events_query`` (reads,
stream, batch); shared schemas/helpers in ``events_common``; block
notifications in ``events_notify``. This module aggregates the routers in
the original registration order and re-exports the moved names.
"""
from fastapi import APIRouter

from app.modules.guard.routers.events_common import (  # noqa: F401 — re-exports
    BatchEventIn, EventOut, HookEvent, RuleFireOut, SSE_MAX_DURATION, SSE_POLL_INTERVAL,
    SessionUsageReport, UsageOut, UsageUpdate, _client_ip_from, _end_of_day_if_bare,
    _event_to_dict, _now, _org_ws_subquery, _trusted_cidrs,
)
from app.modules.guard.routers.events_notify import (  # noqa: F401 — re-exports
    _check_spend_budget, _fanout_email, _fanout_pagerduty, _fanout_slack, _fanout_webhook,
    _pd_severity, _send_guard_slack, notify_guard_block,
)
from app.modules.guard.routers.events_ingest import (  # noqa: F401 — re-exports
    TOOL_PRICING, _authenticated_actor, _authenticated_workspace_uuid, _bg_project_event,
    _bg_slack_notify, _bg_spend_and_scan, _decoded_input_summary, _hook_authenticated_workspace,
    _tool_pricing, ingest_event, ingest_session_usage, update_usage,
)
from app.modules.guard.routers.events_query import (  # noqa: F401 — re-exports
    _SSE_NIL_UUID, _fetch_new_events, _project_rule_fire, cost_trend, ingest_batch,
    list_correlated_events, list_events, list_rule_fires,
    session_reconciliation, stream_events, verify_audit_chain,
)
from app.modules.guard.routers.events_unified import list_unified_activity  # noqa: F401 — re-export
from app.modules.guard.routers import events_ingest as _events_ingest
from app.modules.guard.routers import events_unified as _events_unified
from app.modules.guard.routers import events_query as _events_query

router = APIRouter()
router.include_router(_events_ingest.router)
router.include_router(_events_unified.router)
router.include_router(_events_query.router)
