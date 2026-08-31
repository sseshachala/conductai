"""Publish run.* events on the Lens session channel (#1480 PR 5).

Only Lens-originated runs (run.session_id is not NULL) push events —
every other run trigger (workflow UI, CLI, webhooks, scheduler) leaves
session_id NULL and this module skips silently.

Runtime call sites:
- executor.py at status → "running"  (worker picks up the run)
- executor.py at status → "failed"   (worker crash / uncaught exception)
- dag_runner.py at status → "succeeded" | "failed" (normal completion)

Block-level events (run.block_started / run.block_completed) are a
follow-up — this PR wires the coarse status transitions only, which
already unlocks live pill updates on the <RunBubble>.
"""
from __future__ import annotations

from typing import Any

from app.models.run import Run
from app.modules.glens.events import publish_session_event


def publish_run_status(run: Run, *, error: str | None = None) -> None:
    """Emit run.status_changed with the run's current status.

    No-op when the run has no session_id — nothing to route to.
    Fail-open inside publish_session_event (Redis outage never breaks
    the worker).
    """
    if not getattr(run, "session_id", None):
        return
    payload: dict[str, Any] = {
        "status": run.status,
    }
    if error:
        payload["error"] = error
    publish_session_event(
        str(run.session_id),
        "run.status_changed",
        entity={"type": "run", "id": str(run.id)},
        payload=payload,
    )
