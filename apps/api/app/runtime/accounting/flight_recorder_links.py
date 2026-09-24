"""Flight Recorder deep-link contract (#2209 PR 3 follow-up).

Owned by the accounting engine; subscribed by #2069.

Publishing our side of the contract here means #2069 can implement its
route + event-emission whenever it lands, and Lens can hyperlink
answers today without waiting. When
``settings.flight_recorder_base_url`` is empty, all helpers return
None and consumers render receipts as plain text.

## URL scheme

    {base}/requests/{request_id}
    {base}/requests/{request_id}/attempts/{attempt_ordinal}

- Base URL has no trailing slash (helpers strip if present).
- request_id and attempt_ordinal come from ``LlmAttemptReceipt`` /
  ``SessionSpend``. Both are stable identifiers Flight Recorder can
  index against ``guard_audit_events.request_id``.
- Placeholder receipts (``source='reconciler'``) share the same
  request_id so the same Flight Recorder page shows the reconciled
  attempt alongside any real ones — no separate URL scheme needed.

## Consumer expectations

Lens should render:
- A "View trace" link for each session that has receipts.
- A "View this attempt" link per per-request drilldown row.
- A caveat (⚠ reconciled) when the receipt's source is 'reconciler'.

Flight Recorder should:
- Render a per-request page at ``/requests/{request_id}``.
- Render a per-attempt page at ``/requests/{request_id}/attempts/{n}``.
- Cross-link back to Lens sessions when a hook_session_id is present.

## Backward compat

Blank ``flight_recorder_base_url`` (the default) makes every helper
return None. Nothing surfaces to the API. When Flight Recorder ships
its routes, ops sets the env var, links appear automatically.
"""

from __future__ import annotations

import uuid
from typing import Optional


def _base() -> Optional[str]:
    from app.core.config import settings

    base = (getattr(settings, "flight_recorder_base_url", "") or "").strip()
    if not base:
        return None
    return base.rstrip("/")


def flight_recorder_request_url(request_id: uuid.UUID | str) -> Optional[str]:
    """Deep link to the Flight Recorder page for one request.

    Returns None when ``settings.flight_recorder_base_url`` is unset —
    consumers render plain text in that case.
    """
    base = _base()
    if base is None:
        return None
    return f"{base}/requests/{request_id}"


def flight_recorder_attempt_url(
    request_id: uuid.UUID | str, attempt_ordinal: int
) -> Optional[str]:
    """Deep link to a specific attempt within a request.

    Failed attempts + placeholders + winners all share the same
    request_id but have distinct attempt_ordinals; each has its own
    URL so Lens can point at the exact row that matched the answer.
    """
    base = _base()
    if base is None:
        return None
    return f"{base}/requests/{request_id}/attempts/{int(attempt_ordinal)}"


def flight_recorder_enabled() -> bool:
    """Convenience for callers that want to check once before rendering
    the whole UI."""
    return _base() is not None
